"""Bot Closer en el pipeline: cuando el lead es "hot" y el anunciante activó
el Closer, la respuesta del bot termina con una oferta de caducidad real."""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete, select

from app.core.redis import close_redis
from app.database import AsyncSessionLocal, engine
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.coupon import Coupon
from app.models.message import Message
from app.models.user import User
from app.services.inbound_pipeline import InboundMessage, process_inbound_message

_RAG = "app.services.inbound_pipeline.answer_with_rag"
_RAG_REPLY = "El paquete cuesta $500."


async def _seed(closer_config):
    await engine.dispose()
    await close_redis()
    phone = f"+52155{uuid.uuid4().hex[:7]}"
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x",
                    business_name="Paquetes MX", closer_config=closer_config)
        db.add(user)
        await db.flush()
        contact = Contact(advertiser_id=user.id, name="Luis Soto", phone=phone, source="landing")
        db.add(contact)
        await db.flush()
        db.add(Conversation(advertiser_id=user.id, contact_id=contact.id, messages=[
            {"role": "user", "content": "hola"}, {"role": "assistant", "content": "¡hola!"},
        ]))
        await db.commit()
        return user.id, contact.id, phone


async def _cleanup(user_id):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Coupon).where(Coupon.advertiser_id == user_id))
        await db.execute(delete(Message).where(Message.advertiser_id == user_id))
        await db.execute(delete(Conversation).where(Conversation.advertiser_id == user_id))
        await db.execute(delete(Contact).where(Contact.advertiser_id == user_id))
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()


async def _run(user_id, phone, body):
    async with AsyncSessionLocal() as db:
        user = await db.get(User, user_id)
        send = AsyncMock(side_effect=lambda *a, **k: (f"wamid.{uuid.uuid4().hex[:10]}", None))
        with patch(_RAG, new=AsyncMock(return_value=_RAG_REPLY)), \
                patch("app.workers.tasks.update_contact_engagement_score.apply_async"), \
                patch("app.workers.tasks.auto_tag_contact_from_conversation.apply_async"), \
                patch("app.workers.tasks.trigger_automation_for_contact.apply_async"):
            await process_inbound_message(
                db,
                InboundMessage(advertiser=user, from_number=phone, body_text=body,
                               external_message_id=f"wamid.{uuid.uuid4().hex[:8]}"),
                send=send, send_owner=AsyncMock(return_value=("o", None)),
            )
    return send


async def _coupons(user_id):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(Coupon).where(Coupon.advertiser_id == user_id))).scalars().all()


class TestCloserInbound:
    @pytest.mark.asyncio
    async def test_hot_lead_gets_offer_appended(self):
        user_id, contact_id, phone = await _seed({"enabled": True, "hold_hours": 2})
        try:
            send = await _run(user_id, phone, "necesito saber el precio del paquete ya, es urgente")
            reply = send.await_args.args[1]
            assert _RAG_REPLY in reply
            assert "🎫 Tu cupón" in reply
            coupons = await _coupons(user_id)
            assert len(coupons) == 1 and coupons[0].source == "closer"
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_warm_lead_gets_no_offer(self):
        user_id, contact_id, phone = await _seed({"enabled": True})
        try:
            send = await _run(user_id, phone, "gracias, lo voy a pensar")
            assert "🎫 Tu cupón" not in send.await_args.args[1]
            assert await _coupons(user_id) == []
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_disabled_closer_gets_no_offer(self):
        user_id, contact_id, phone = await _seed({"enabled": False})
        try:
            send = await _run(user_id, phone, "necesito el precio ahora, es urgente")
            assert "🎫 Tu cupón" not in send.await_args.args[1]
            assert await _coupons(user_id) == []
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_redeem_reply_closes_the_offer(self):
        user_id, contact_id, phone = await _seed({"enabled": True})
        try:
            await _run(user_id, phone, "necesito el precio ya, urgente")
            await _run(user_id, phone, "CANJEAR")
            coupons = await _coupons(user_id)
            assert len(coupons) == 1
            assert coupons[0].redeemed_at is not None
        finally:
            await _cleanup(user_id)
