"""Real-DB tests for widget_order_service.py — the widget's own order state
machine (collecting_name → collecting_address → collecting_payment →
confirmed), independent of WhatsApp's inbound_pipeline.py state machine."""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete, select

from app.database import AsyncSessionLocal, engine
from app.models.contact import Contact
from app.models.order import Order
from app.models.user import User
from app.services.widget_order_service import NEEDS_CONTACT_REPLY, handle_widget_order


async def _seed_user(**overrides):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", **overrides)
        db.add(user)
        await db.commit()
        return user.id


async def _seed_contact(advertiser_id, **overrides):
    async with AsyncSessionLocal() as db:
        contact = Contact(
            advertiser_id=advertiser_id, name="Ana Torres", phone="+525511112222", **overrides
        )
        db.add(contact)
        await db.commit()
        return contact.id


async def _cleanup(user_ids):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Order).where(Order.advertiser_id.in_(user_ids)))
        await db.execute(delete(Contact).where(Contact.advertiser_id.in_(user_ids)))
        await db.execute(delete(User).where(User.id.in_(user_ids)))
        await db.commit()
    await engine.dispose()


class TestHandleWidgetOrder:
    @pytest.mark.asyncio
    async def test_no_order_intent_returns_none(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                reply = await handle_widget_order(db, user, None, "¿cuál es su horario?")
            assert reply is None
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_order_intent_without_contact_invites_to_leave_data(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                reply = await handle_widget_order(db, user, None, "quiero pedir 2 pizzas")
            assert reply == NEEDS_CONTACT_REPLY
            async with AsyncSessionLocal() as db:
                count = (await db.execute(select(Order).where(Order.advertiser_id == user_id))).scalars().all()
            assert count == []  # no Order created without a contact to attach it to
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_order_intent_with_contact_starts_order(self):
        user_id = await _seed_user()
        contact_id = await _seed_contact(user_id)
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                contact = await db.get(Contact, contact_id)
                reply = await handle_widget_order(db, user, contact, "quiero pedir 2 pizzas de pepperoni")
            assert "nombre" in reply.lower()

            async with AsyncSessionLocal() as db:
                order = (
                    (await db.execute(select(Order).where(Order.advertiser_id == user_id))).scalars().first()
                )
            assert order.state == "collecting_name"
            assert order.items_raw == "quiero pedir 2 pizzas de pepperoni"
            assert order.contact_id == contact_id
            assert order.order_number == 1
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_full_state_progression_to_confirmed(self):
        user_id = await _seed_user(business_name="Tacos El Primo")
        contact_id = await _seed_contact(user_id)
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                contact = await db.get(Contact, contact_id)
                await handle_widget_order(db, user, contact, "quiero pedir 2 pizzas")

            with patch("app.core.email.send_new_order_email", new_callable=AsyncMock) as mock_email:
                async with AsyncSessionLocal() as db:
                    user = await db.get(User, user_id)
                    contact = await db.get(Contact, contact_id)
                    reply1 = await handle_widget_order(db, user, contact, "Ana Torres")
                assert "dirección" in reply1.lower()

                async with AsyncSessionLocal() as db:
                    user = await db.get(User, user_id)
                    contact = await db.get(Contact, contact_id)
                    reply2 = await handle_widget_order(db, user, contact, "Calle Falsa 123")
                assert "pagar" in reply2.lower()

                async with AsyncSessionLocal() as db:
                    user = await db.get(User, user_id)
                    contact = await db.get(Contact, contact_id)
                    reply3 = await handle_widget_order(db, user, contact, "Efectivo")
                assert "confirmado" in reply3.lower()
                assert "#0001" in reply3

                # asyncio.create_task fires the email in the background — give it a tick
                import asyncio
                await asyncio.sleep(0.05)
                assert mock_email.called
                assert mock_email.call_args.kwargs["customer_phone"] == "+525511112222"
                assert mock_email.call_args.kwargs["payment_method"] == "Efectivo"

            async with AsyncSessionLocal() as db:
                order = (
                    (await db.execute(select(Order).where(Order.advertiser_id == user_id))).scalars().first()
                )
            assert order.state == "confirmed"
            assert order.customer_name == "Ana Torres"
            assert order.delivery_address == "Calle Falsa 123"
            assert order.payment_method == "Efectivo"
            assert order.confirmed_at is not None
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_pending_order_takes_priority_over_new_intent_detection(self):
        """Once an order is in progress, every message advances the state
        machine regardless of its content — 'quiero pedir X' as an address
        should be taken literally as the address, not re-trigger detection."""
        user_id = await _seed_user()
        contact_id = await _seed_contact(user_id)
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                contact = await db.get(Contact, contact_id)
                await handle_widget_order(db, user, contact, "quiero ordenar tacos")
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                contact = await db.get(Contact, contact_id)
                reply = await handle_widget_order(db, user, contact, "quiero pedir que me lo lleven a mi casa")
            assert "dirección" in reply.lower()

            async with AsyncSessionLocal() as db:
                order = (
                    (await db.execute(select(Order).where(Order.advertiser_id == user_id))).scalars().first()
                )
            assert order.customer_name == "quiero pedir que me lo lleven a mi casa"
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_notifies_owner_via_whatsapp_only_when_connected(self):
        user_id = await _seed_user(whatsapp_number="+525500001111")
        contact_id = await _seed_contact(user_id)
        try:
            with patch("app.core.email.send_new_order_email", new_callable=AsyncMock), \
                 patch("app.services.meta_service.send_whatsapp", new_callable=AsyncMock) as mock_wa:
                mock_wa.return_value = ("wamid.x", None)
                async with AsyncSessionLocal() as db:
                    user = await db.get(User, user_id)
                    contact = await db.get(Contact, contact_id)
                    await handle_widget_order(db, user, contact, "quiero pedir 1 pizza")
                async with AsyncSessionLocal() as db:
                    user = await db.get(User, user_id)
                    contact = await db.get(Contact, contact_id)
                    await handle_widget_order(db, user, contact, "Ana")
                async with AsyncSessionLocal() as db:
                    user = await db.get(User, user_id)
                    contact = await db.get(Contact, contact_id)
                    await handle_widget_order(db, user, contact, "Calle Falsa 123")
                async with AsyncSessionLocal() as db:
                    user = await db.get(User, user_id)
                    contact = await db.get(Contact, contact_id)
                    await handle_widget_order(db, user, contact, "Efectivo")

                import asyncio
                await asyncio.sleep(0.05)
                mock_wa.assert_called_once()
                assert mock_wa.call_args.args[0] == "+525500001111"
        finally:
            await _cleanup([user_id])
