"""Recordatorio "sube eso al Catálogo" cuando el dueño contesta "¿Tienen X?"
y X no está en su catálogo (app/services/catalog_reminder.py). BD real para el
catálogo; el central usa la sesión simulada de test_owner_questions."""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import delete, select

from app.api.v1.conversations import LearnBody, learn_from_reply
from app.api.v1.products import (
    ProductCreate,
    ProductUpdate,
    create_product,
    update_product,
)
from app.database import AsyncSessionLocal, engine
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.knowledge_base import KnowledgeBase
from app.models.message import Message
from app.models.owner_question import OwnerQuestion
from app.models.product import Product
from app.models.user import User
from app.services import copilot_business_tools as biz_tools
from app.services import owner_question_service as svc
from app.services.catalog_reminder import (
    asked_item,
    catalog_reminder,
    retire_no_answers,
)
from app.services.owner_question_service import OWNER_ANSWERS_FILENAME


class TestAskedItem:
    def test_what_the_customer_asked_for(self):
        assert asked_item("¿Tienen fundas?") == "fundas"
        assert asked_item("tiene micas?\"") == "micas"
        assert asked_item("¿Venden cargadores tipo C?") == "cargadores tipo C"
        assert asked_item("¿Hay pastel de tres leches?") == "pastel de tres leches"
        assert asked_item("¿Tienen audífonos?") == "audífonos"

    def test_not_a_product_question(self):
        for q in ("¿A qué hora abren?", "¿Dónde están?", "¿Tienen servicio a domicilio?",
                  "¿Hay estacionamiento?", "¿Tienen promociones?", "¿Aceptan tarjeta?",
                  "¿Tienen algo para regalar a mi mamá que cumple años mañana?"):
            assert asked_item(q) is None, q


async def _business(*products: tuple[str, bool]):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="CityCell")
        db.add(user)
        await db.flush()
        for name, active in products:
            db.add(Product(advertiser_id=user.id, name=name, price=100, active=active))
        await db.commit()
        return user.id


async def _cleanup(*user_ids):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        for uid in user_ids:
            for model in (KnowledgeBase, Message, Conversation, Contact, Product):
                await db.execute(delete(model).where(model.advertiser_id == uid))
            await db.execute(delete(User).where(User.id == uid))
        await db.commit()
    await engine.dispose()


async def _reminder(user_id, question, answer):
    async with AsyncSessionLocal() as db:
        return await catalog_reminder(db, user_id, question, answer)


class TestCatalogReminder:
    async def test_said_no_and_not_in_catalog_reminds_to_add_it_and_erase_the_answer(self):
        uid = await _business(("Cargador USB-C 20W", True))
        try:
            text = await _reminder(uid, "¿Tienen fundas?", "No, no tenemos fundas por ahora; las tendremos más adelante.")
            assert "fundas" in text and "Catálogo" in text and "deja de decir que no hay" in text
        finally:
            await _cleanup(uid)

    async def test_said_yes_and_not_in_catalog_reminds_to_add_it(self):
        uid = await _business()
        try:
            text = await _reminder(uid, "¿Tienen fundas?", "Sí, fundas desde $80")
            assert "Da de alta fundas en Catálogo" in text and "borra" not in text
        finally:
            await _cleanup(uid)

    async def test_already_in_catalog_no_reminder(self):
        uid = await _business(("Funda uso rudo iPhone 15", True))
        try:
            assert await _reminder(uid, "¿Tienen fundas?", "Sí, desde $120") == ""
        finally:
            await _cleanup(uid)

    async def test_turned_off_product_or_other_business_does_not_count(self):
        uid = await _business(("Funda uso rudo", False))
        other = await _business(("Funda uso rudo", True))
        try:
            assert "fundas" in await _reminder(uid, "¿Tienen fundas?", "No por ahora")
        finally:
            await _cleanup(uid, other)

    async def test_not_a_product_question_no_reminder(self):
        uid = await _business()
        try:
            assert await _reminder(uid, "¿Tienen servicio a domicilio?", "Sí, $30 en Tlaxiaco") == ""
        finally:
            await _cleanup(uid)

    async def test_failure_means_no_reminder(self):
        db = MagicMock()
        db.execute = AsyncMock(side_effect=RuntimeError("db caída"))
        assert await catalog_reminder(db, uuid.uuid4(), "¿Tienen fundas?", "No") == ""


class TestInboxSaveShowsReminder:
    async def test_guardar_returns_the_reminder(self):
        uid = await _business()
        try:
            async with AsyncSessionLocal() as db:
                contact = Contact(advertiser_id=uid, name="Ana", phone=f"+52155{uuid.uuid4().int % 10**8:08d}")
                db.add(contact)
                await db.flush()
                conv = Conversation(advertiser_id=uid, contact_id=contact.id, messages=[])
                db.add(conv)
                db.add(Message(advertiser_id=uid, contact_id=contact.id, direction="inbound", content="¿tienen fundas?",
                               status="delivered", created_at=datetime.now(timezone.utc) - timedelta(minutes=1)))
                await db.commit()
                conv_id = conv.id
            with patch("app.services.owner_question_service.get_embedding", AsyncMock(return_value=[0.0] * 1024)):
                async with AsyncSessionLocal() as db:
                    user = await db.get(User, uid)
                    out = await learn_from_reply(conv_id, LearnBody(question="¿Tienen fundas?",
                                                                    answer="No, no tenemos fundas por ahora."),
                                                 db=db, current_user=user)
            assert out["saved"] is True and "deja de decir que no hay" in out["reminder"]
        finally:
            await _cleanup(uid)


class TestCentralAnswerShowsReminder:
    async def test_confirmation_to_the_owner_carries_the_reminder(self):
        owner = User(id=uuid.uuid4(), business_name="CityCell", bot_name="Bot", whatsapp_number="+5215512345678")
        oq = OwnerQuestion(id=uuid.uuid4(), advertiser_id=owner.id, contact_id=uuid.uuid4(),
                           customer_phone="+5215599999999", question="¿Tienen fundas?", status="pending")
        db = MagicMock()
        db.commit = AsyncMock()
        results = []
        for r in ([owner], oq):
            res = MagicMock()
            res.scalars.return_value.all.return_value = r if isinstance(r, list) else [r]
            res.scalar_one_or_none.return_value = r if not isinstance(r, list) else None
            results.append(res)
        db.execute = AsyncMock(side_effect=results)
        with (
            patch.object(svc, "send_platform_text", AsyncMock(return_value=("w", None))) as sp,
            patch.object(svc, "send_whatsapp", AsyncMock(return_value=("wamid.c", None))),
            patch.object(svc, "chat_completion", AsyncMock(return_value="Por ahora no tenemos fundas 🙏")),
            patch.object(svc, "get_embedding", AsyncMock(return_value=[0.0] * 1024)),
            patch.object(svc, "publish_conversation_event", AsyncMock()),
            patch("app.services.catalog_reminder.catalog_reminder",
                  AsyncMock(return_value="📌 Cuando ya tengas fundas, da de alta el producto")) as cr,
        ):
            await svc.handle_owner_message(db, from_number="+5215512345678", text="no tenemos por ahora",
                                           context_wamid="wamid.owner")
        assert cr.await_args.args[2:] == ("¿Tienen fundas?", "no tenemos por ahora")
        sent = sp.call_args.args[1]
        assert sent.startswith("✅ Listo") and "📌 Cuando ya tengas fundas" in sent


async def _answer(user_id, question, answer):
    async with AsyncSessionLocal() as db:
        chunk = f"Pregunta: {question}\nRespuesta: {answer}"
        kb = KnowledgeBase(advertiser_id=user_id, filename=OWNER_ANSWERS_FILENAME, file_type="txt", raw_text=chunk,
                           chunk_text=chunk, embedding=[0.0] * 1024, processing_status="done", is_active=True)
        db.add(kb)
        await db.commit()
        return kb.id


async def _active(kb_id) -> bool:
    async with AsyncSessionLocal() as db:
        return (await db.get(KnowledgeBase, kb_id)).is_active


class TestAddingProductRetiresNoAnswer:
    async def test_panel_create_retires_the_no_answer_and_tells_the_owner(self):
        uid = await _business()
        try:
            no = await _answer(uid, "¿Tienen fundas?", "No, no tenemos fundas por ahora; las tendremos más adelante.")
            async with AsyncSessionLocal() as db:
                user = await db.get(User, uid)
                out = await create_product(ProductCreate(name="Funda uso rudo iPhone 15", price=120),
                                           db=db, current_user=user)
            assert not await _active(no)
            assert out.retired_answers == ["No, no tenemos fundas por ahora; las tendremos más adelante."]
        finally:
            await _cleanup(uid)

    async def test_unrelated_product_yes_answers_and_documents_are_kept(self):
        uid = await _business()
        try:
            no_fundas = await _answer(uid, "¿Tienen fundas?", "Por ahora no tenemos")
            yes_fundas = await _answer(uid, "¿Tienen fundas de silicón?", "Sí, desde $80")
            no_mica = await _answer(uid, "¿Tienen micas?", "No")
            async with AsyncSessionLocal() as db:
                user = await db.get(User, uid)
                out = await create_product(ProductCreate(name="Cargador USB-C"), db=db, current_user=user)
            assert out.retired_answers == []
            assert await _active(no_fundas) and await _active(yes_fundas) and await _active(no_mica)
        finally:
            await _cleanup(uid)

    async def test_more_specific_no_answer_is_kept(self):
        """"¿Tienen fundas de silicón? No" no se quita al dar de alta "Funda uso rudo"."""
        uid = await _business()
        try:
            kept = await _answer(uid, "¿Tienen fundas de silicón?", "No, solo de uso rudo")
            async with AsyncSessionLocal() as db:
                assert await retire_no_answers(db, uid, "Funda uso rudo") == []
                await db.commit()
            assert await _active(kept)
        finally:
            await _cleanup(uid)

    async def test_turning_a_product_back_on_retires_too(self):
        uid = await _business(("Funda uso rudo", False))
        try:
            no = await _answer(uid, "¿Tienen fundas?", "Todavía no tenemos")
            async with AsyncSessionLocal() as db:
                user = await db.get(User, uid)
                prod = (await db.execute(select(Product).where(Product.advertiser_id == uid))).scalar_one()
                out = await update_product(prod.id, ProductUpdate(active=True), db=db, current_user=user)
            assert out.retired_answers == ["Todavía no tenemos"] and not await _active(no)
        finally:
            await _cleanup(uid)

    async def test_price_change_does_not_touch_answers(self):
        uid = await _business(("Funda uso rudo", True))
        try:
            no = await _answer(uid, "¿Tienen fundas?", "No")
            async with AsyncSessionLocal() as db:
                user = await db.get(User, uid)
                prod = (await db.execute(select(Product).where(Product.advertiser_id == uid))).scalar_one()
                out = await update_product(prod.id, ProductUpdate(price=150), db=db, current_user=user)
            assert out.retired_answers == [] and await _active(no)
        finally:
            await _cleanup(uid)

    async def test_other_business_answers_are_never_touched(self):
        uid, other = await _business(), await _business()
        try:
            theirs = await _answer(other, "¿Tienen fundas?", "No")
            async with AsyncSessionLocal() as db:
                user = await db.get(User, uid)
                await create_product(ProductCreate(name="Funda"), db=db, current_user=user)
            assert await _active(theirs)
        finally:
            await _cleanup(uid, other)

    async def test_copilot_create_retires_and_says_so(self):
        uid = await _business()
        try:
            no = await _answer(uid, "¿Tienen fundas?", "No, por ahora no")
            async with AsyncSessionLocal() as db:
                user = await db.get(User, uid)
                out, err = await biz_tools.execute_change(db, user, "create_product", {"name": "Fundas", "price": 120})
            assert err is None and not await _active(no)
            assert "Quité la respuesta vieja" in out[biz_tools.OWNER_NOTICE]
        finally:
            await _cleanup(uid)
