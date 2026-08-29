"""Voces del Barrio — el bucle emocional en el inbound pipeline.

Cuando llega una nota de voz y hay una campaña `type="voces"` activa:
guarda la `CustomerStory` (con consentimiento), emite UN cupón VIP por
contacto, le avisa al dueño, acusa recibo al cliente con el bloque de cupón
y NO pasa el audio por el bot RAG.

Real DB (no mocks), mismo patrón que test_radio_audio_optin_inbound.py.
"""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete, select

from app.database import AsyncSessionLocal, engine
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.coupon import Coupon
from app.models.customer_story import CustomerStory
from app.models.message import Message
from app.models.user import User
from app.services.inbound_pipeline import InboundMessage, process_inbound_message

_RAG_PATCH = "app.services.inbound_pipeline.answer_with_rag"
_SENTIMENT_TASK = "app.workers.tasks.classify_story_sentiment.apply_async"


async def _seed(reward_coupon: bool = True, campaign_status: str = "running"):
    await engine.dispose()
    phone = f"+52155{uuid.uuid4().hex[:7]}"
    async with AsyncSessionLocal() as db:
        advertiser = User(
            email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="El Fogón",
            whatsapp_number="+525599990000", messages_remaining=50, slug=f"el-fogon-{uuid.uuid4().hex[:6]}",
        )
        db.add(advertiser)
        await db.flush()

        contact = Contact(advertiser_id=advertiser.id, phone=phone, name="Carmen Ruiz", status="active")
        db.add(contact)

        campaign = Campaign(
            advertiser_id=advertiser.id, name="Voces", type="voces",
            message_text="Mándanos tu historia", status=campaign_status,
            ab_test={
                "campaign_mode": "voces",
                "consent_line": "Al enviar autorizas publicarla en {negocio}.",
                "reward_coupon": reward_coupon,
                "reward_coupon_desc": "Cupón Cliente VIP",
                "reward_coupon_hours": 48,
                "reward_discount_type": "percentage",
                "reward_discount_value": 20,
            },
        )
        db.add(campaign)
        await db.commit()
        return advertiser.id, contact.id, campaign.id, phone


async def _stories(advertiser_id):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        rows = await db.execute(select(CustomerStory).where(CustomerStory.advertiser_id == advertiser_id))
        return rows.scalars().all()


async def _coupons(advertiser_id):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        rows = await db.execute(select(Coupon).where(Coupon.advertiser_id == advertiser_id))
        return rows.scalars().all()


async def _cleanup(advertiser_id):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(CustomerStory).where(CustomerStory.advertiser_id == advertiser_id))
        await db.execute(delete(Coupon).where(Coupon.advertiser_id == advertiser_id))
        await db.execute(delete(Message).where(Message.advertiser_id == advertiser_id))
        await db.execute(delete(Conversation).where(Conversation.advertiser_id == advertiser_id))
        await db.execute(delete(Campaign).where(Campaign.advertiser_id == advertiser_id))
        await db.execute(delete(Contact).where(Contact.advertiser_id == advertiser_id))
        await db.execute(delete(User).where(User.id == advertiser_id))
        await db.commit()
    await engine.dispose()


def _voice_msg(advertiser, phone, run_id, transcription="Cada viernes vengo por enchiladas con mi nieto"):
    return InboundMessage(
        advertiser=advertiser, from_number=phone, body_text=transcription,
        audio_transcription=transcription, media_url="https://cdn/x/wa_media/story.ogg",
        external_message_id=f"wamid.{run_id}",
    )


class TestVocesLoop:
    @pytest.mark.asyncio
    async def test_voice_note_creates_story_coupon_ack_and_owner_notice(self):
        run_id = uuid.uuid4().hex[:8]
        advertiser_id, contact_id, campaign_id, phone = await _seed(reward_coupon=True)

        async with AsyncSessionLocal() as db:
            advertiser = await db.get(User, advertiser_id)
            send = AsyncMock(return_value=("sid.out", None))
            send_owner = AsyncMock(return_value=("sid.owner", None))
            with patch(_RAG_PATCH, new=AsyncMock(return_value="bot reply")) as mock_rag, \
                    patch(_SENTIMENT_TASK) as mock_sentiment:
                result = await process_inbound_message(
                    db, _voice_msg(advertiser, phone, run_id), send=send, send_owner=send_owner,
                )

        try:
            assert result == {"message": "ok"}

            stories = await _stories(advertiser_id)
            assert len(stories) == 1
            assert stories[0].campaign_id == campaign_id
            assert stories[0].status == "pending"
            assert stories[0].consent_at is not None
            assert "El Fogón" in stories[0].consent_text

            coupons = await _coupons(advertiser_id)
            assert len(coupons) == 1
            assert coupons[0].contact_id == contact_id
            assert stories[0].coupon_id == coupons[0].id

            # El acuse al cliente lleva el nombre y el bloque de cupón.
            assert send.await_count == 1
            ack = send.await_args.args[1]
            assert "Carmen" in ack
            assert coupons[0].code in ack

            send_owner.assert_awaited_once()
            assert "revisar" in send_owner.await_args.args[1].lower()

            mock_rag.assert_not_awaited()
            mock_sentiment.assert_called_once()
            assert mock_sentiment.call_args.kwargs["args"] == [str(stories[0].id)]
        finally:
            await _cleanup(advertiser_id)

    @pytest.mark.asyncio
    async def test_second_voice_note_adds_story_but_not_a_second_coupon(self):
        advertiser_id, contact_id, campaign_id, phone = await _seed(reward_coupon=True)
        try:
            for i in range(2):
                async with AsyncSessionLocal() as db:
                    advertiser = await db.get(User, advertiser_id)
                    with patch(_RAG_PATCH, new=AsyncMock(return_value="x")), patch(_SENTIMENT_TASK):
                        await process_inbound_message(
                            db, _voice_msg(advertiser, phone, f"{uuid.uuid4().hex[:8]}-{i}"),
                            send=AsyncMock(return_value=(f"sid.out.{i}", None)),
                            send_owner=AsyncMock(return_value=(f"sid.owner.{i}", None)),
                        )

            assert len(await _stories(advertiser_id)) == 2
            assert len(await _coupons(advertiser_id)) == 1
        finally:
            await _cleanup(advertiser_id)

    @pytest.mark.asyncio
    async def test_no_reward_coupon_still_stores_story_and_acks(self):
        run_id = uuid.uuid4().hex[:8]
        advertiser_id, contact_id, campaign_id, phone = await _seed(reward_coupon=False)

        async with AsyncSessionLocal() as db:
            advertiser = await db.get(User, advertiser_id)
            send = AsyncMock(return_value=("sid.out", None))
            with patch(_RAG_PATCH, new=AsyncMock(return_value="x")), patch(_SENTIMENT_TASK):
                await process_inbound_message(
                    db, _voice_msg(advertiser, phone, run_id), send=send,
                    send_owner=AsyncMock(return_value=("s", None)),
                )
        try:
            assert len(await _stories(advertiser_id)) == 1
            assert await _coupons(advertiser_id) == []
            assert send.await_count == 1
            assert "🎫" not in send.await_args.args[1]  # sin bloque de cupón
        finally:
            await _cleanup(advertiser_id)

    @pytest.mark.asyncio
    async def test_voice_note_without_active_voces_campaign_goes_to_bot(self):
        run_id = uuid.uuid4().hex[:8]
        advertiser_id, contact_id, campaign_id, phone = await _seed(campaign_status="completed")

        async with AsyncSessionLocal() as db:
            advertiser = await db.get(User, advertiser_id)
            send = AsyncMock(return_value=("sid.out", None))
            with patch(_RAG_PATCH, new=AsyncMock(return_value="respuesta del bot")) as mock_rag, patch(_SENTIMENT_TASK):
                await process_inbound_message(
                    db, _voice_msg(advertiser, phone, run_id), send=send,
                    send_owner=AsyncMock(return_value=("s", None)),
                )
        try:
            assert await _stories(advertiser_id) == []
            mock_rag.assert_awaited_once()
            assert any("respuesta del bot" in c.args[1] for c in send.call_args_list)
        finally:
            await _cleanup(advertiser_id)
