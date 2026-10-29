"""¿Para cuál negocio? (docs/specs/2026-10-29-para-cual-negocio.md).
Base y Redis reales; WhatsApp, la IA y el Copiloto (que llama a la IA) son falsos."""
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from sqlalchemy import delete

from app.core.redis import get_redis_optional
from app.database import AsyncSessionLocal, engine
from app.models.owner_question import OwnerQuestion
from app.models.user import User
from app.services import central_account_picker as picker
from app.services import copilot_whatsapp_service as cw
from app.services import owner_question_service as svc


def _number() -> str:
    return f"+52195{uuid.uuid4().int % 10**8:08d}"


async def _owners(number: str, *names: str) -> list[uuid.UUID]:
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        # En el orden en que se dieron de alta: así salen en los botones.
        start = datetime.now(timezone.utc) - timedelta(days=len(names))
        users = [User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name=n, whatsapp_number=number,
                      created_at=start + timedelta(days=i))
                 for i, n in enumerate(names)]
        db.add_all(users)
        await db.commit()
        return [u.id for u in users]


async def _cleanup(ids: list[uuid.UUID], number: str) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(delete(OwnerQuestion).where(OwnerQuestion.advertiser_id.in_(ids)))
        await db.execute(delete(User).where(User.id.in_(ids)))
        await db.commit()
    redis = await get_redis_optional()
    await picker.forget(redis, number)
    await picker.release(redis, number)
    await engine.dispose()


@contextmanager
def _wa():
    """WhatsApp y el Copiloto, falsos: se ve a quién y qué se le mandó."""
    with patch.object(svc, "send_platform_text", AsyncMock(return_value=("w", None))) as text, \
         patch.object(picker, "send_platform_buttons", AsyncMock(return_value=("w", None))) as buttons, \
         patch.object(picker, "send_platform_list", AsyncMock(return_value=("w", None))) as lst, \
         patch.object(cw, "handle_owner_command", AsyncMock()) as copilot, \
         patch.object(cw, "has_open_builder", AsyncMock(return_value=False)), \
         patch.object(cw, "has_pending_confirmation", AsyncMock(return_value=False)), \
         patch.object(svc, "chat_completion", AsyncMock(return_value="NO")):
        yield {"text": text, "buttons": buttons, "list": lst, "copilot": copilot}


async def _say(number: str, text: str, **kw) -> None:
    async with AsyncSessionLocal() as db:
        await svc.handle_owner_message(db, from_number=number, text=text, context_wamid=kw.pop("context_wamid", None), **kw)


def _titles(buttons) -> list[str]:
    return [t for _, t in buttons.call_args.args[2]]


async def test_two_accounts_ask_which_business_before_doing_anything():
    number = _number()
    ids = await _owners(number, "IaRadio", "CityCell")
    try:
        with _wa() as wa:
            await _say(number, "haz una campaña de 2x1 en micas este viernes")
        wa["copilot"].assert_not_awaited()
        assert wa["buttons"].call_args.args[1] == picker.ASK_TEXT
        assert _titles(wa["buttons"]) == ["IaRadio", "CityCell"]
    finally:
        await _cleanup(ids, number)


async def test_tapping_a_business_confirms_and_does_what_was_asked_there():
    number = _number()
    ids = await _owners(number, "IaRadio", "CityCell")
    try:
        with _wa() as wa:
            await _say(number, "haz una campaña de 2x1 en micas este viernes")
            await _say(number, "CityCell")  # el título del botón
        assert wa["text"].call_args.args[1] == "Listo, ahora estás en *CityCell* 🏪"
        kw = wa["copilot"].call_args.kwargs
        assert kw["owner"].id == ids[1]
        assert kw["text"] == "haz una campaña de 2x1 en micas este viernes"
        assert kw["business"] == "CityCell"
    finally:
        await _cleanup(ids, number)


async def test_choice_is_remembered_and_each_message_renews_the_12_hours():
    number = _number()
    ids = await _owners(number, "IaRadio", "CityCell")
    redis = await get_redis_optional()
    try:
        with _wa() as wa:
            await _say(number, "hola")
            await _say(number, "CityCell")
            key = picker.CHOICE_KEY.format(number=picker._number(number))
            await redis.expire(key, 60)  # como si hubieran pasado casi 12 h
            await _say(number, "¿cuántos pedidos tengo?")
        assert wa["buttons"].await_count == 1
        assert wa["copilot"].call_args.kwargs["owner"].id == ids[1]
        assert await redis.ttl(key) > picker.CHOICE_TTL_SECONDS - 60
    finally:
        await _cleanup(ids, number)


async def test_after_12_hours_without_writing_it_asks_again():
    number = _number()
    ids = await _owners(number, "IaRadio", "CityCell")
    redis = await get_redis_optional()
    try:
        with _wa() as wa:
            await _say(number, "hola")
            await _say(number, "CityCell")
            assert await redis.ttl(picker.CHOICE_KEY.format(number=picker._number(number))) <= picker.CHOICE_TTL_SECONDS
            await redis.delete(picker.CHOICE_KEY.format(number=picker._number(number)))  # caducó
            await _say(number, "¿cuántos pedidos tengo?")
        assert wa["buttons"].await_count == 2
        assert wa["copilot"].await_count == 1  # solo el "hola" de la primera vez
    finally:
        await _cleanup(ids, number)


async def test_change_business_asks_again_and_the_new_choice_sticks():
    number = _number()
    ids = await _owners(number, "IaRadio", "CityCell")
    try:
        with _wa() as wa:
            await _say(number, "hola")
            await _say(number, "CityCell")
            await _say(number, "Cambiar negocio")
            assert wa["buttons"].await_count == 2
            await _say(number, "IaRadio")
            await _say(number, "¿cuántos pedidos tengo?")
        assert wa["text"].call_args.args[1] == "Listo, ahora estás en *IaRadio* 🏪"
        assert wa["copilot"].call_args.kwargs["owner"].id == ids[0]
        assert wa["copilot"].await_count == 2  # "hola" y la pregunta; "IaRadio" solo escoge
    finally:
        await _cleanup(ids, number)


async def test_before_sending_a_campaign_it_says_which_business():
    with patch.object(cw, "send_platform_buttons", AsyncMock(return_value=("w", None))) as sb:
        step = {"step": "send", "text": "Le llega: 1 por web.", "choices": [{"id": "web", "label": "Mandar gratis por web"}]}
        await cw._send_question("+5215512345678", step, "CityCell")
        assert "Se manda a los clientes de *CityCell*" in sb.call_args.args[1]
        await cw._send_question("+5215512345678", step)  # una sola cuenta: no se dice
        assert "Se manda" not in sb.call_args.args[1]


async def test_quick_promo_confirmation_says_which_business():
    owner = User(id=uuid.uuid4(), business_name="CityCell")
    chat = AsyncMock(return_value={"reply": "Voy a mandar *2x1 en micas*.",
                                   "pending_confirmation": {"confirmation_id": "t", "tool": "send_promo"}})

    class Redis(dict):
        async def get(self, k):
            return dict.get(self, k)

        async def set(self, k, v, ex=None):
            self[k] = v

    with patch.object(cw, "get_redis_optional", AsyncMock(return_value=Redis())), \
         patch.object(cw, "handle_chat", chat), \
         patch.object(cw, "send_platform_buttons", AsyncMock(return_value=("w", None))) as sb:
        await cw.handle_owner_command(None, owner=owner, from_number="+52155", text="manda 2x1", business="CityCell")
    assert sb.call_args.args[1].endswith("🏪 Se manda a los clientes de *CityCell*.")


async def test_more_than_three_businesses_get_a_list():
    number = _number()
    ids = await _owners(number, "IaRadio", "CityCell", "Fonda Mary", "Barbería")
    try:
        with _wa() as wa:
            await _say(number, "hola")
            wa["buttons"].assert_not_awaited()
            assert [t for _, t in wa["list"].call_args.args[2]] == ["IaRadio", "CityCell", "Fonda Mary", "Barbería"]
            await _say(number, "Fonda Mary")
        assert wa["copilot"].call_args.kwargs["owner"].id == ids[2]
    finally:
        await _cleanup(ids, number)


async def test_typing_something_else_shows_the_buttons_again_and_keeps_the_first_request():
    number = _number()
    ids = await _owners(number, "IaRadio", "CityCell")
    try:
        with _wa() as wa:
            await _say(number, "haz una campaña de 2x1 en micas")
            await _say(number, "eh?")
            assert wa["buttons"].await_count == 2
            await _say(number, "citycell")
        assert wa["copilot"].await_count == 1
        assert wa["copilot"].call_args.kwargs["text"] == "haz una campaña de 2x1 en micas"
    finally:
        await _cleanup(ids, number)


async def test_photo_before_choosing_asks_and_then_asks_for_the_photo_again():
    number = _number()
    ids = await _owners(number, "IaRadio", "CityCell")
    try:
        with _wa() as wa, patch.object(cw, "save_owner_photo", AsyncMock(return_value="https://cdn/x.jpg")) as save:
            await _say(number, "", photo=(b"jpg", "image/jpeg"))
            save.assert_not_awaited()
            await _say(number, "CityCell")
        assert wa["text"].call_args.args[1] == "Mándame otra vez la foto 📷"
        wa["copilot"].assert_not_awaited()
    finally:
        await _cleanup(ids, number)


async def test_answer_to_a_customer_never_asks_for_the_business():
    number = _number()
    ids = await _owners(number, "IaRadio", "CityCell")
    async with AsyncSessionLocal() as db:
        db.add(OwnerQuestion(advertiser_id=ids[1], customer_phone="+5215599999999", question="¿Tienen envío?",
                             status="pending", owner_wamid="wamid.aviso"))
        await db.commit()
    try:
        with _wa() as wa, \
             patch.object(svc, "send_whatsapp", AsyncMock(return_value=("wamid.c", None))) as sw, \
             patch.object(svc, "learn_answer", AsyncMock()), \
             patch.object(svc, "chat_completion", AsyncMock(return_value="¡Sí! Enviamos por $30 😊")):
            await _say(number, "si, 30 pesos", context_wamid="wamid.aviso")
        wa["buttons"].assert_not_awaited()
        assert sw.call_args.kwargs["advertiser"].id == ids[1]
    finally:
        await _cleanup(ids, number)


async def test_one_account_never_asks():
    number = _number()
    ids = await _owners(number, "CityCell")
    try:
        with _wa() as wa:
            await _say(number, "haz una campaña de 2x1 en micas")
        wa["buttons"].assert_not_awaited()
        assert wa["copilot"].call_args.kwargs["owner"].id == ids[0]
        assert wa["copilot"].call_args.kwargs["business"] is None
    finally:
        await _cleanup(ids, number)


def test_same_name_twice_gets_numbered_and_numbers_also_pick():
    owners = [User(id=uuid.uuid4(), business_name="CityCell"), User(id=uuid.uuid4(), business_name="CityCell")]
    assert picker.labels(owners) == ["CityCell", "CityCell (2)"]
    assert picker.match(owners, "CityCell (2)") is owners[1]
    assert picker.match(owners, "1", asking=True) is owners[0]
    assert picker.match(owners, "1") is None


async def test_unquoted_answer_to_the_only_pending_question_never_asks_for_the_business():
    number = _number()
    ids = await _owners(number, "IaRadio", "CityCell")
    async with AsyncSessionLocal() as db:
        db.add(OwnerQuestion(advertiser_id=ids[1], customer_phone="+5215599999999", question="¿Tienen envío?",
                             status="pending", owner_wamid="wamid.aviso"))
        await db.commit()
    try:
        with _wa() as wa, \
             patch.object(svc, "send_whatsapp", AsyncMock(return_value=("wamid.c", None))) as sw, \
             patch.object(svc, "learn_answer", AsyncMock()), \
             patch.object(svc, "chat_completion", AsyncMock(return_value="¡Sí! Enviamos por $30 😊")):
            await _say(number, "si, 30 pesos")
        wa["buttons"].assert_not_awaited()
        wa["copilot"].assert_not_awaited()
        assert sw.call_args.kwargs["advertiser"].id == ids[1]
    finally:
        await _cleanup(ids, number)


async def test_old_campaign_button_without_a_business_never_reaches_a_customer_nor_sends():
    # Revisor: con la elección vencida, "Mandar gratis por web" de un armador abierto
    # se tomaba como respuesta a la pregunta de un cliente.
    number = _number()
    ids = await _owners(number, "IaRadio", "CityCell")
    async with AsyncSessionLocal() as db:
        db.add(OwnerQuestion(advertiser_id=ids[0], customer_phone="+5215599999999", question="¿Tienen envío?",
                             status="pending", owner_wamid="wamid.aviso"))
        await db.commit()
    try:
        with _wa() as wa, \
             patch.object(cw, "has_open_builder", AsyncMock(side_effect=lambda o: o.id == ids[1])), \
             patch.object(svc, "send_whatsapp", AsyncMock(return_value=("wamid.c", None))) as sw, \
             patch.object(svc, "chat_completion", AsyncMock(side_effect=RuntimeError("IA caída"))):
            await _say(number, "Mandar gratis por web")
            assert wa["buttons"].await_count == 1
            await _say(number, f"pick:{ids[1]}")
        sw.assert_not_awaited()
        kw = wa["copilot"].call_args.kwargs
        assert wa["copilot"].await_count == 1
        assert kw["owner"].id == ids[1] and kw["text"] == ""  # vuelve a mostrar el paso, no lo manda
    finally:
        await _cleanup(ids, number)


async def test_names_that_look_the_same_on_a_button_pick_by_id():
    number = _number()
    ids = await _owners(number, "Papelería La Estrella Centro", "Papelería La Estrella Norte")
    try:
        with _wa() as wa:
            await _say(number, "hola")
            titles = _titles(wa["buttons"])
            assert len(set(titles)) == 2
            await _say(number, wa["buttons"].call_args.args[2][1][0])  # el id del segundo botón
        assert wa["copilot"].call_args.kwargs["owner"].id == ids[1]
    finally:
        await _cleanup(ids, number)


async def test_a_number_only_picks_while_being_asked():
    number = _number()
    ids = await _owners(number, "IaRadio", "CityCell")
    try:
        with _wa() as wa:
            await _say(number, "1")  # nadie le preguntó: no escoge en silencio
            assert wa["buttons"].await_count == 1
            await _say(number, "2")
        assert wa["text"].call_args.args[1] == "Listo, ahora estás en *CityCell* 🏪"
    finally:
        await _cleanup(ids, number)


def test_webhook_passes_the_pick_id_instead_of_the_cut_title():
    from app.api.v1.webhooks_pkg.meta_incoming import _extract_body_text
    tap = {"type": "interactive", "interactive": {"type": "button_reply",
                                                  "button_reply": {"id": "pick:abc", "title": "Papelería La Estrell"}}}
    assert _extract_body_text(tap) == ("pick:abc", None)
    other = {"type": "interactive", "interactive": {"type": "button_reply",
                                                    "button_reply": {"id": "copilot_yes", "title": "✅ Sí, hazlo"}}}
    assert _extract_body_text(other) == ("✅ Sí, hazlo", None)


async def test_old_pick_button_switches_business_even_with_one_already_chosen():
    number = _number()
    ids = await _owners(number, "IaRadio", "CityCell")
    try:
        with _wa() as wa:
            await _say(number, "hola")
            await _say(number, f"pick:{ids[0]}")
            await _say(number, f"pick:{ids[1]}")  # botón viejo, ya estaba en IaRadio
            await _say(number, "¿cuántos pedidos tengo?")
        assert wa["text"].call_args.args[1] == "Listo, ahora estás en *CityCell* 🏪"
        assert wa["copilot"].call_args.kwargs["owner"].id == ids[1]
        assert wa["copilot"].await_count == 2  # "hola" y la pregunta; los botones solo escogen
    finally:
        await _cleanup(ids, number)


async def test_a_yes_before_choosing_is_never_applied_on_its_own():
    number = _number()
    ids = await _owners(number, "IaRadio", "CityCell")
    try:
        with _wa() as wa, \
             patch.object(cw, "has_pending_confirmation", AsyncMock(side_effect=lambda o: o.id == ids[1])):
            await _say(number, "✅ Sí, mándala")
            assert wa["buttons"].await_count == 1
            await _say(number, f"pick:{ids[1]}")
        wa["copilot"].assert_not_awaited()
        assert "toca otra vez *Sí*" in wa["text"].call_args.args[1]
    finally:
        await _cleanup(ids, number)
