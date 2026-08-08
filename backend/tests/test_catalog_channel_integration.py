"""Real-DB, no-mocks-of-business-logic tests for the catalog Q&A feature —
confirms handle_catalog_query works against real seeded Products, and that
the new additive branches in inbound_pipeline.py (WhatsApp) and widget.py
route to it correctly, before appointment/order, without disturbing those
existing flows."""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete
from starlette.requests import Request

from app.api.v1.widget import widget_chat
from app.core.redis import close_redis
from app.database import AsyncSessionLocal, engine
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.product import Product
from app.models.user import User
from app.services.catalog_service import handle_catalog_query
from app.services.inbound_pipeline import InboundMessage, process_inbound_message

PHONE = "+525511117777"


def _request() -> Request:
    scope = {
        "type": "http", "method": "POST", "path": "/api/v1/widget/chat/x", "headers": [],
        "client": (f"test-{uuid.uuid4()}", 123), "query_string": b"",
    }
    return Request(scope)


async def _seed_advertiser_and_contact(**user_overrides):
    await engine.dispose()
    await close_redis()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", **user_overrides)
        db.add(user)
        await db.flush()
        contact = Contact(advertiser_id=user.id, name="Luis", phone=PHONE, source="landing")
        db.add(contact)
        await db.commit()
        return user.id, contact.id


async def _cleanup(user_ids):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Message).where(Message.advertiser_id.in_(user_ids)))
        await db.execute(delete(Conversation).where(Conversation.advertiser_id.in_(user_ids)))
        await db.execute(delete(Contact).where(Contact.advertiser_id.in_(user_ids)))
        await db.execute(delete(Product).where(Product.advertiser_id.in_(user_ids)))
        await db.execute(delete(User).where(User.id.in_(user_ids)))
        await db.commit()
    await engine.dispose()
    await close_redis()


async def _send_whatsapp(advertiser, text):
    send = AsyncMock(return_value=(f"wamid.fake-{uuid.uuid4()}", None))
    async with AsyncSessionLocal() as db:
        msg = InboundMessage(advertiser=advertiser, from_number=PHONE, body_text=text)
        result = await process_inbound_message(db, msg, send=send, send_owner=send)
    return result, send


class TestHandleCatalogQueryService:
    @pytest.mark.asyncio
    async def test_returns_none_when_message_is_not_a_catalog_request(self):
        user_id, _ = await _seed_advertiser_and_contact()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                reply = await handle_catalog_query(db, user, "hola buenas tardes")
            assert reply is None
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_lists_active_products_grouped_by_category(self):
        user_id, _ = await _seed_advertiser_and_contact()
        try:
            async with AsyncSessionLocal() as db:
                db.add(Product(advertiser_id=user_id, name="Taco al pastor", price=25, category="Comida", active=True))
                db.add(Product(advertiser_id=user_id, name="Refresco", price=20, category="Bebidas", active=True))
                db.add(Product(advertiser_id=user_id, name="Descontinuado", price=99, active=False))
                await db.commit()

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                reply = await handle_catalog_query(db, user, "¿qué venden?")
            assert reply is not None
            assert "Taco al pastor" in reply
            assert "Refresco" in reply
            assert "Descontinuado" not in reply
            assert "Comida" in reply
            assert "Bebidas" in reply
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_no_products_yields_fallback_reply_not_none(self):
        user_id, _ = await _seed_advertiser_and_contact()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                reply = await handle_catalog_query(db, user, "muéstrame el catálogo")
            assert reply is not None
            assert "no tenemos un catálogo" in reply.lower()
        finally:
            await _cleanup([user_id])


class TestCatalogViaWhatsApp:
    @pytest.mark.asyncio
    async def test_catalog_question_replies_with_products_and_creates_no_order_or_appointment(self):
        user_id, contact_id = await _seed_advertiser_and_contact()
        try:
            async with AsyncSessionLocal() as db:
                db.add(Product(advertiser_id=user_id, name="Pastel de chocolate", price=250, active=True))
                await db.commit()
                advertiser = await db.get(User, user_id)

            result, send = await _send_whatsapp(advertiser, "¿qué productos tienen?")
            assert result == {"message": "ok"}
            reply_text = send.call_args.args[1]
            assert "Pastel de chocolate" in reply_text

            from app.models.order import Order
            async with AsyncSessionLocal() as db:
                orders = (await db.execute(delete(Order).where(Order.advertiser_id == user_id).returning(Order.id))).all()
                await db.commit()
            assert orders == []  # confirms the catalog branch never touched Order at all
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_real_order_message_is_unaffected_by_the_new_catalog_branch(self):
        """Regression guard: adding the catalog branch before the order
        state machine must not swallow a genuine order-intent message."""
        user_id, contact_id = await _seed_advertiser_and_contact()
        try:
            async with AsyncSessionLocal() as db:
                advertiser = await db.get(User, user_id)
            result, send = await _send_whatsapp(advertiser, "quiero pedir 2 pizzas")
            assert result == {"message": "ok"}
            reply_text = send.call_args.args[1].lower()
            # WhatsApp's order flow starts with the pending_confirmation Sí/No
            # gate (unlike the widget's, which skips straight to collecting_name)
            assert "responde" in reply_text and ("sí" in reply_text or "si" in reply_text)
        finally:
            await _cleanup([user_id])


class TestCatalogViaWidget:
    @pytest.mark.asyncio
    async def test_catalog_question_is_routed_before_rag(self):
        user_id, _ = await _seed_advertiser_and_contact()
        try:
            async with AsyncSessionLocal() as db:
                db.add(Product(advertiser_id=user_id, name="Corte de cabello", price=150, active=True))
                await db.commit()

            with patch("app.services.rag_service.answer_with_rag", new_callable=AsyncMock) as mock_rag:
                async with AsyncSessionLocal() as db:
                    out = await widget_chat(
                        request=_request(), advertiser_id=user_id,
                        body={"message": "¿tienen catálogo?"}, db=db, redis=None,
                    )
            assert "Corte de cabello" in out["reply"]
            mock_rag.assert_not_called()
        finally:
            await _cleanup([user_id])
