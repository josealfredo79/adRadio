"""Tests for the list/segment-level relaunch cooldown (Propuesta 4 anti-baneo)
— closes the gap where the per-contact 48h cooldown doesn't stop the *same
list* from being blasted wholesale every couple of days."""
import uuid

import pytest
from unittest.mock import AsyncMock, patch

from app.workers.task_helpers.campaign_ops import (
    is_segment_on_cooldown,
    record_segment_send,
    segment_fingerprint,
)


class TestSegmentFingerprint:
    def test_same_tags_different_order_same_fingerprint(self):
        a = segment_fingerprint({"tags": ["vip", "tlaxiaco"]})
        b = segment_fingerprint({"tags": ["tlaxiaco", "vip"]})
        assert a == b

    def test_different_tags_different_fingerprint(self):
        a = segment_fingerprint({"tags": ["vip"]})
        b = segment_fingerprint({"tags": ["frio"]})
        assert a != b

    def test_specific_contacts_vs_tags_different_fingerprint(self):
        a = segment_fingerprint({"specific_contacts": ["c1", "c2"]})
        b = segment_fingerprint({"tags": ["c1", "c2"]})
        assert a != b

    def test_empty_segment_is_stable(self):
        assert segment_fingerprint({}) == segment_fingerprint({})


class TestIsSegmentOnCooldownAndRecord:
    @pytest.mark.asyncio
    async def test_no_prior_send_is_not_on_cooldown(self):
        from app.database import AsyncSessionLocal, engine
        await engine.dispose()

        advertiser_id = uuid.uuid4()
        fingerprint = segment_fingerprint({"tags": ["nunca-antes"]})
        async with AsyncSessionLocal() as db:
            on_cooldown = await is_segment_on_cooldown(db, advertiser_id, fingerprint)
        assert on_cooldown is False

    @pytest.mark.asyncio
    async def test_record_then_check_is_on_cooldown(self):
        from app.database import AsyncSessionLocal, engine
        from app.models.user import User
        await engine.dispose()

        fingerprint = segment_fingerprint({"tags": ["recien-lanzada"]})
        async with AsyncSessionLocal() as db:
            advertiser = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Test")
            db.add(advertiser)
            await db.flush()
            advertiser_id = advertiser.id
            await record_segment_send(db, advertiser_id, fingerprint)
            await db.commit()

        async with AsyncSessionLocal() as db:
            on_cooldown = await is_segment_on_cooldown(db, advertiser_id, fingerprint)
        assert on_cooldown is True

    @pytest.mark.asyncio
    async def test_record_is_idempotent_upsert_not_duplicate_rows(self):
        from sqlalchemy import select

        from app.database import AsyncSessionLocal, engine
        from app.models.campaign_segment_send import CampaignSegmentSend
        from app.models.user import User
        await engine.dispose()

        fingerprint = segment_fingerprint({"tags": ["relanzada-dos-veces"]})
        async with AsyncSessionLocal() as db:
            advertiser = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Test")
            db.add(advertiser)
            await db.flush()
            advertiser_id = advertiser.id
            await record_segment_send(db, advertiser_id, fingerprint)
            await record_segment_send(db, advertiser_id, fingerprint)
            await db.commit()

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(CampaignSegmentSend).where(
                    CampaignSegmentSend.advertiser_id == advertiser_id,
                    CampaignSegmentSend.segment_fingerprint == fingerprint,
                )
            )
            rows = result.scalars().all()
        assert len(rows) == 1


class TestScheduleCampaignRespectsSegmentCooldown:
    def test_relaunching_same_list_within_cooldown_gets_paused_without_sending(self):
        """Real DB end-to-end: first campaign to a list sends (mocked send
        function) and records the list as sent; a second campaign to the
        exact same list gets auto-paused and never reaches the send
        function. schedule_campaign is a Celery task that runs its own
        asyncio.run() internally, so this test (and its DB seed/check
        phases) must stay synchronous rather than `async def` — nesting
        asyncio.run() inside a running pytest-asyncio loop would crash."""
        import asyncio

        from app.database import AsyncSessionLocal, engine
        from app.models.campaign import Campaign
        from app.models.contact import Contact
        from app.models.user import User
        from app.workers.tasks import schedule_campaign

        async def _seed():
            await engine.dispose()
            async with AsyncSessionLocal() as db:
                advertiser = User(
                    email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Test",
                    messages_remaining=1000,
                )
                db.add(advertiser)
                await db.flush()
                contact = Contact(advertiser_id=advertiser.id, phone="+5215500000000", name="Cliente", status="active")
                db.add(contact)
                segment = {"tags": ["tlaxiaco"]}
                campaign_1 = Campaign(
                    advertiser_id=advertiser.id, name="Promo 1", type="promo",
                    message_text="hola", status="scheduled", segment=segment,
                )
                campaign_2 = Campaign(
                    advertiser_id=advertiser.id, name="Promo 2 (relanzada)", type="promo",
                    message_text="hola de nuevo", status="scheduled", segment=segment,
                )
                db.add_all([campaign_1, campaign_2])
                await db.commit()
                return campaign_1.id, campaign_2.id

        campaign_1_id, campaign_2_id = asyncio.run(_seed())

        with patch("app.services.messaging_throttle.is_human_hour", return_value=True), \
             patch("app.workers.tasks.send_regular_messages", new=AsyncMock()) as mock_send:
            schedule_campaign(str(campaign_1_id))
            assert mock_send.await_count == 1

            schedule_campaign(str(campaign_2_id))
            assert mock_send.await_count == 1  # not called again for campaign 2

        async def _check():
            await engine.dispose()
            async with AsyncSessionLocal() as db:
                c2 = await db.get(Campaign, campaign_2_id)
                return c2.status

        assert asyncio.run(_check()) == "paused"
