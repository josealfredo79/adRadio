"""Arreglos de la prueba real CityCell 2026-11-04 (WhatsApp, 11:09 pm):
1. "¿A qué horas abren?" → "¿Te gustaría agendar una cita…?" en una tienda que no da citas.
2. "Dónde están" + "??" → el bot contestaba los dos.
3. "¿Te gustaría agregarlo a tu pedido?" sin pedido."""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.config import settings
from app.core.redis import close_redis, get_redis_optional
from app.database import AsyncSessionLocal
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.user import User
from app.services import rag_service
from app.services.inbound_pipeline import _just_punctuation
from tests.test_customer_agent_whatsapp import _cleanup, _seed, _wa


def test_only_punctuation_counts_as_a_bare_follow_up():
    for t in ("??", "?", "¿?", "...", "…", "!!", " ? ? ", '"??"', "“??”", "'?'", "??\""):
        assert _just_punctuation(t), t
    for t in ("", None, "ok", "?? hola", "2", "👍", '"hola"'):
        assert not _just_punctuation(t), t


@pytest.mark.asyncio
async def test_a_bare_question_mark_right_after_a_message_gets_no_second_reply(monkeypatch):
    monkeypatch.setattr(settings, "CUSTOMER_AGENT_WHATSAPP", "")
    user_id, *_ = await _seed()
    try:
        with patch("app.services.inbound_pipeline.answer_with_rag",
                   AsyncMock(return_value="Estamos en Calle 5 de Mayo.")) as rag:
            first = await _wa(user_id, "Dónde están")
            second = await _wa(user_id, "??")
        assert first.text.await_count == 1
        assert second.text.await_count == 0 and second.buttons.await_count == 0
        assert rag.await_count == 1
    finally:
        await _cleanup(user_id)



async def _forget_recent(user_id) -> None:
    redis = await get_redis_optional()
    async with AsyncSessionLocal() as db:
        for cid in (await db.execute(select(Contact.id).where(Contact.advertiser_id == user_id))).scalars():
            await redis.delete(f"inbound_recent:{cid}")


async def _turns(user_id) -> list[dict]:
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(Conversation.messages).where(Conversation.advertiser_id == user_id))
                ).scalar_one_or_none() or []


@pytest.mark.asyncio
async def test_the_ignored_question_mark_shows_in_the_inbox(monkeypatch):
    monkeypatch.setattr(settings, "CUSTOMER_AGENT_WHATSAPP", "")
    user_id, *_ = await _seed()
    try:
        with patch("app.services.inbound_pipeline.answer_with_rag",
                   AsyncMock(return_value="Estamos en Calle 5 de Mayo.")):
            await _wa(user_id, "Dónde están")
            await _wa(user_id, "??")
        assert [(t["role"], t["content"], t.get("unanswered")) for t in await _turns(user_id)] == [
            ("user", "Dónde están", None),
            ("assistant", "Estamos en Calle 5 de Mayo.", None),
            ("user", "??", True),
        ]
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_a_question_mark_sent_while_the_bot_thinks_is_not_lost(monkeypatch):
    """El "??" llega mientras el bot arma la respuesta a "Dónde están": al
    guardar esa respuesta no se pisa el "??" (queda entre la pregunta y la respuesta)."""
    monkeypatch.setattr(settings, "CUSTOMER_AGENT_WHATSAPP", "")
    user_id, *_ = await _seed()
    seconds: list = []

    async def slow_answer(*a, **k):
        if not seconds and len(await _turns(user_id)) == 2:  # ya contestó "hola"; ahora "Dónde están"
            seconds.append(await _wa(user_id, "??"))
            return "Estamos en Calle 5 de Mayo."
        return "¡Hola! ¿En qué te ayudo?"

    try:
        with patch("app.services.inbound_pipeline.answer_with_rag", AsyncMock(side_effect=slow_answer)):
            await _wa(user_id, "hola")
            await close_redis()  # que "Dónde están" no cuente como "recién escribió"
            await _forget_recent(user_id)
            await _wa(user_id, "Dónde están")
        assert seconds[0].text.await_count == 0  # el "??" no se contestó
        assert [(t["role"], t["content"], t.get("unanswered")) for t in await _turns(user_id)] == [
            ("user", "hola", None),
            ("assistant", "¡Hola! ¿En qué te ayudo?", None),
            ("user", "Dónde están", None),
            ("user", "??", True),
            ("assistant", "Estamos en Calle 5 de Mayo.", None),
        ]
    finally:
        await _cleanup(user_id)

async def _instructions_for(user: User) -> str:
    """Las instrucciones que answer_with_rag le pasa al bot."""
    async with AsyncSessionLocal() as db:
        db.add(user)
        await db.commit()
        try:
            with patch.object(rag_service, "search_knowledge", AsyncMock(return_value="Horario 9 a 20")), \
                 patch.object(rag_service, "generate_bot_response", AsyncMock(return_value="ok")) as gen:
                await rag_service.answer_with_rag(str(user.id), "¿a qué hora abren?", [], db, business_name=user.business_name)
            return gen.await_args.kwargs["bot_instructions"] or ""
        finally:
            await db.delete(user)
            await db.commit()


@pytest.mark.asyncio
async def test_a_shop_without_appointments_is_told_not_to_offer_them():
    shop = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="CityCell",
                business_category="Tienda de celulares")
    assert rag_service.NO_APPOINTMENTS_FACT in await _instructions_for(shop)


@pytest.mark.asyncio
async def test_a_salon_keeps_offering_appointments():
    salon = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Estética Lupita",
                 business_category="Estética")
    assert rag_service.NO_APPOINTMENTS_FACT not in await _instructions_for(salon)


def test_add_to_an_order_is_rewritten_when_there_is_no_order():
    # Prod 2026-11-04 23:33 (Groq): "¿Te gustaría agregarlo a un pedido o necesitas más información?"
    from app.services.claude_service import fix_order_wording

    assert fix_order_wording("¿Te gustaría agregarlo a un pedido o necesitas más información?") == (
        "¿Te gustaría pedirlo o necesitas más información?")
    assert fix_order_wording("¿Quieres agregarla a tu pedido?") == "¿Quieres pedirla?"
    assert fix_order_wording("Agregarlos a tu pedido es fácil") == "Pedirlos es fácil"
    assert fix_order_wording("Tu pedido #3 va en camino") == "Tu pedido #3 va en camino"


@pytest.mark.asyncio
async def test_the_bot_reply_goes_through_the_fix():
    from app.services import claude_service

    with patch.object(claude_service, "chat_completion",
                      AsyncMock(return_value="El Poco 65 cuesta $3,000. ¿Te gustaría agregarlo a un pedido?")):
        out = await claude_service.generate_bot_response("ctx", [], "¿cuánto el poco?", "CityCell")
    assert out == "El Poco 65 cuesta $3,000. ¿Te gustaría pedirlo?"
