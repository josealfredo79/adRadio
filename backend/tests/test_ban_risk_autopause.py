"""Integration test for Capa 13 (reacting to ban-risk Meta error codes) —
verifies that send_whatsapp_message actually pauses the advertiser's active
campaigns end-to-end when Meta returns a ban-risk error, not just that
is_ban_risk_error() classifies the string correctly in isolation (see
test_meta_quality_service.py for that unit coverage). Same real-DB pattern
as TestScheduleCampaignRespectsRecipientCap in test_recipient_cap.py: the
Celery task runs its own asyncio.run() internally, so seed/check must stay
outside pytest-asyncio's own event loop."""
import asyncio
import uuid
from unittest.mock import patch

from app.database import AsyncSessionLocal, engine
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.message import Message
from app.models.user import User
from app.workers.tasks import send_whatsapp_message


class TestBanRiskErrorAutoPauses:
    def test_healthy_ecosystem_error_pauses_active_campaigns(self):
        async def _seed():
            await engine.dispose()
            async with AsyncSessionLocal() as db:
                advertiser = User(
                    email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Test",
                    messages_remaining=1000,
                )
                db.add(advertiser)
                await db.flush()

                campaign = Campaign(
                    advertiser_id=advertiser.id, name="Promo en riesgo", type="promo",
                    message_text="hola", status="running",
                )
                db.add(campaign)

                contact = Contact(advertiser_id=advertiser.id, phone="+521234567890", name="Cliente", status="active")
                db.add(contact)
                await db.flush()

                msg = Message(
                    advertiser_id=advertiser.id, contact_id=contact.id, direction="outbound",
                    content="hola", status="queued",
                )
                db.add(msg)
                await db.commit()
                return advertiser.id, campaign.id, msg.id

        advertiser_id, campaign_id, message_id = asyncio.run(_seed())

        ban_error = "(#131049) This message was not delivered to maintain healthy ecosystem engagement"
        with patch(
            "app.services.meta_service.send_whatsapp",
            return_value=(None, ban_error),
        ):
            send_whatsapp_message(str(message_id), "+521234567890", "hola")

        async def _check():
            await engine.dispose()
            async with AsyncSessionLocal() as db:
                campaign = await db.get(Campaign, campaign_id)
                msg = await db.get(Message, message_id)
                result = campaign.status, msg.status, msg.error_code
            # Leave no pooled connection tied to this loop for the next
            # test (this loop is about to be torn down by asyncio.run()).
            await engine.dispose()
            return result

        campaign_status, msg_status, msg_error = asyncio.run(_check())
        assert campaign_status == "paused"
        assert msg_status == "failed"
        assert msg_error == ban_error

    def test_ordinary_delivery_error_does_not_pause_campaigns(self):
        """Regression guard: an unrelated failure (e.g. undeliverable to a
        single recipient) must not nuke every other active campaign."""
        async def _seed():
            await engine.dispose()
            async with AsyncSessionLocal() as db:
                advertiser = User(
                    email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Test",
                    messages_remaining=1000,
                )
                db.add(advertiser)
                await db.flush()

                campaign = Campaign(
                    advertiser_id=advertiser.id, name="Promo normal", type="promo",
                    message_text="hola", status="running",
                )
                db.add(campaign)

                contact = Contact(advertiser_id=advertiser.id, phone="+521234567890", name="Cliente", status="active")
                db.add(contact)
                await db.flush()

                msg = Message(
                    advertiser_id=advertiser.id, contact_id=contact.id, direction="outbound",
                    content="hola", status="queued",
                )
                db.add(msg)
                await db.commit()
                return campaign.id, msg.id

        campaign_id, message_id = asyncio.run(_seed())

        with patch(
            "app.services.meta_service.send_whatsapp",
            return_value=(None, "(#131026) Message undeliverable"),
        ):
            send_whatsapp_message(str(message_id), "+521234567890", "hola")

        async def _check():
            await engine.dispose()
            async with AsyncSessionLocal() as db:
                status = (await db.get(Campaign, campaign_id)).status
            await engine.dispose()
            return status

        assert asyncio.run(_check()) == "running"
