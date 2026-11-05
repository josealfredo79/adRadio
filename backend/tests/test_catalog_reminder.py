"""Recordatorio "sube eso al Catálogo" cuando el dueño contesta "¿Tienen X?"
y X no está en su catálogo (app/services/catalog_reminder.py). BD real para el
catálogo; el central usa la sesión simulada de test_owner_questions."""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import delete

from app.api.v1.conversations import LearnBody, learn_from_reply
from app.database import AsyncSessionLocal, engine
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.knowledge_base import KnowledgeBase
from app.models.message import Message
from app.models.owner_question import OwnerQuestion
from app.models.product import Product
from app.models.user import User
from app.services import owner_question_service as svc
from app.services.catalog_reminder import asked_item, catalog_reminder


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
            assert "fundas" in text and "Catálogo" in text and "borra esta respuesta" in text
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
            assert out["saved"] is True and "borra esta respuesta" in out["reminder"]
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
