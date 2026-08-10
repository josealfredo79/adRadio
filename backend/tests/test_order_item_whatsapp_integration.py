"""Real-DB, no-mocks-of-business-logic tests confirming inbound_pipeline.py
(WhatsApp channel) creates the right OrderItem rows for a genuine order, and
that the detected_plan pseudo-order (IaRadio plan purchase) never creates any
OrderItem — mirrors test_catalog_channel_integration.py's pattern."""
import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import delete, select

from app.core.redis import close_redis
from app.database import AsyncSessionLocal, engine
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.user import User
from app.services.inbound_pipeline import InboundMessage, process_inbound_message

PHONE = "+525511118888"


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


async def _seed_product(advertiser_id, **overrides):
    overrides.setdefault("name", "Pizza Pepperoni")
    overrides.setdefault("active", True)
    async with AsyncSessionLocal() as db:
        product = Product(advertiser_id=advertiser_id, **overrides)
        db.add(product)
        await db.commit()
        return product.id


async def _cleanup(user_ids):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        order_ids = (
            await db.execute(select(Order.id).where(Order.advertiser_id.in_(user_ids)))
        ).scalars().all()
        if order_ids:
            await db.execute(delete(OrderItem).where(OrderItem.order_id.in_(order_ids)))
        await db.execute(delete(Order).where(Order.advertiser_id.in_(user_ids)))
        await db.execute(delete(Product).where(Product.advertiser_id.in_(user_ids)))
        await db.execute(delete(Message).where(Message.advertiser_id.in_(user_ids)))
        await db.execute(delete(Conversation).where(Conversation.advertiser_id.in_(user_ids)))
        await db.execute(delete(Contact).where(Contact.advertiser_id.in_(user_ids)))
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


class TestOrderItemViaWhatsApp:
    @pytest.mark.asyncio
    async def test_real_order_creates_order_items_for_matched_products(self):
        user_id, contact_id = await _seed_advertiser_and_contact()
        product_id = await _seed_product(user_id, name="Pizza Pepperoni")
        try:
            async with AsyncSessionLocal() as db:
                advertiser = await db.get(User, user_id)
            # turn 1: order intent -> pending_confirmation, OrderItem already
            # created here (matching happens at order-creation time, not at
            # confirmation)
            await _send_whatsapp(advertiser, "quiero pedir 2 pizzas de pepperoni")

            async with AsyncSessionLocal() as db:
                order = (
                    (await db.execute(select(Order).where(Order.advertiser_id == user_id))).scalars().first()
                )
            assert order.state == "pending_confirmation"
            async with AsyncSessionLocal() as db:
                items = (
                    (await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))).scalars().all()
                )
            assert len(items) == 1
            assert items[0].product_id == product_id
            assert items[0].product_name_snapshot == "Pizza Pepperoni"
            assert items[0].quantity == 2

            # walk the rest of the state machine to confirmed, confirming the
            # OrderItem rows survive untouched through to confirmation
            async with AsyncSessionLocal() as db:
                advertiser = await db.get(User, user_id)
            await _send_whatsapp(advertiser, "Sí")
            await _send_whatsapp(advertiser, "Luis Perez")
            await _send_whatsapp(advertiser, "Calle Falsa 123")
            result, send = await _send_whatsapp(advertiser, "Efectivo")
            assert result == {"message": "ok"}
            reply_text = send.call_args.args[1].lower()
            assert "confirmado" in reply_text

            async with AsyncSessionLocal() as db:
                order = await db.get(Order, order.id)
                items = (
                    (await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))).scalars().all()
                )
            assert order.state == "confirmed"
            assert len(items) == 1
            assert items[0].product_id == product_id
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_real_order_with_no_product_match_creates_no_order_items(self):
        user_id, contact_id = await _seed_advertiser_and_contact()
        await _seed_product(user_id, name="Pizza Pepperoni")
        try:
            async with AsyncSessionLocal() as db:
                advertiser = await db.get(User, user_id)
            await _send_whatsapp(advertiser, "quiero pedir un corte de cabello")

            async with AsyncSessionLocal() as db:
                order = (
                    (await db.execute(select(Order).where(Order.advertiser_id == user_id))).scalars().first()
                )
                items = (
                    (await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))).scalars().all()
                )
            assert items == []
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_plan_purchase_pseudo_order_never_creates_order_items(self):
        """The detected_plan branch (IaRadio plan purchase, reuses Order
        with items_raw='Plan X') is structurally outside the product-matching
        block — confirms it stays that way."""
        user_id, contact_id = await _seed_advertiser_and_contact()
        await _seed_product(user_id, name="Plan Starter")  # deliberately named to tempt a false match
        try:
            async with AsyncSessionLocal() as db:
                advertiser = await db.get(User, user_id)
            await _send_whatsapp(advertiser, "quiero contratar el plan starter de iaradio")

            async with AsyncSessionLocal() as db:
                order = (
                    (await db.execute(select(Order).where(Order.advertiser_id == user_id))).scalars().first()
                )
            assert order is not None
            assert order.state == "plan_pending_confirmation"
            assert order.items_raw.startswith("Plan")

            async with AsyncSessionLocal() as db:
                items = (
                    (await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))).scalars().all()
                )
            assert items == []
        finally:
            await _cleanup([user_id])
