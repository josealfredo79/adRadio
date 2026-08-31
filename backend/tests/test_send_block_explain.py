"""Tests for app.services.send_block_explain — the layer that turns a
silent anti-ban pause into a sentence the advertiser can read, and the
synchronous pre-flight the resume endpoint uses so it can 409 instead of
flipping a campaign to running and letting it re-pause itself."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete

from app.database import AsyncSessionLocal, engine
from app.models.campaign import Campaign
from app.models.campaign_segment_send import CampaignSegmentSend
from app.models.contact import Contact
from app.models.send_block_log import SendBlockLog
from app.models.user import User
from app.services.send_block_explain import explain_campaign_pause, preflight_campaign_send
from app.workers.task_helpers.campaign_ops import segment_fingerprint


async def _seed_user(messages_remaining: int = 100):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", messages_remaining=messages_remaining)
        db.add(user)
        await db.commit()
        return user.id


async def _cleanup(user_ids):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(SendBlockLog).where(SendBlockLog.advertiser_id.in_(user_ids)))
        await db.execute(delete(CampaignSegmentSend).where(CampaignSegmentSend.advertiser_id.in_(user_ids)))
        await db.execute(delete(Campaign).where(Campaign.advertiser_id.in_(user_ids)))
        await db.execute(delete(Contact).where(Contact.advertiser_id.in_(user_ids)))
        await db.execute(delete(User).where(User.id.in_(user_ids)))
        await db.commit()
    await engine.dispose()


class TestExplainCampaignPause:
    @pytest.mark.asyncio
    async def test_running_campaign_has_no_reason(self):
        uid = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                c = Campaign(advertiser_id=uid, name="R", type="promo", message_text="h", status="running")
                db.add(c)
                await db.commit()
                assert await explain_campaign_pause(db, c) is None
        finally:
            await _cleanup([uid])

    @pytest.mark.asyncio
    async def test_hand_paused_campaign_with_no_log_returns_none(self):
        uid = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                c = Campaign(advertiser_id=uid, name="P", type="promo", message_text="h", status="paused")
                db.add(c)
                await db.commit()
                assert await explain_campaign_pause(db, c) is None
        finally:
            await _cleanup([uid])

    @pytest.mark.asyncio
    async def test_segment_cooldown_pause_reports_retry_date(self):
        uid = await _seed_user()
        try:
            sent_at = datetime.now(timezone.utc) - timedelta(days=2)
            async with AsyncSessionLocal() as db:
                c = Campaign(advertiser_id=uid, name="P", type="promo", message_text="h",
                             status="paused", segment={})
                db.add(c)
                db.add(CampaignSegmentSend(advertiser_id=uid,
                                           segment_fingerprint=segment_fingerprint({}),
                                           last_sent_at=sent_at))
                await db.commit()
                db.add(SendBlockLog(advertiser_id=uid, campaign_id=c.id, reason="segment_cooldown"))
                await db.commit()

                out = await explain_campaign_pause(db, c)
            assert out["reason"] == "segment_cooldown"
            assert "bloquee tu número" in out["message"]  # plain-language copy, no jargon
            # 2 days elapsed of a 7-day window -> retry ~5 days out
            assert out["retry_after"] is not None
            assert "Podrás enviarla el" in out["message"]
        finally:
            await _cleanup([uid])


class TestPreflightCampaignSend:
    @pytest.mark.asyncio
    async def test_clean_campaign_passes(self):
        uid = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                c = Campaign(advertiser_id=uid, name="P", type="promo", message_text="h",
                             status="paused", segment={})
                db.add(c)
                await db.commit()
                adv = await db.get(User, uid)
                assert await preflight_campaign_send(db, c, adv) is None
        finally:
            await _cleanup([uid])

    @pytest.mark.asyncio
    async def test_blocks_on_active_segment_cooldown(self):
        uid = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                c = Campaign(advertiser_id=uid, name="P", type="promo", message_text="h",
                             status="paused", segment={})
                db.add(c)
                db.add(CampaignSegmentSend(advertiser_id=uid,
                                           segment_fingerprint=segment_fingerprint({}),
                                           last_sent_at=datetime.now(timezone.utc)))
                await db.commit()
                adv = await db.get(User, uid)
                msg = await preflight_campaign_send(db, c, adv)
            assert msg is not None and "bloquee tu número" in msg
        finally:
            await _cleanup([uid])

    @pytest.mark.asyncio
    async def test_blocks_on_exhausted_quota(self):
        uid = await _seed_user(messages_remaining=0)
        try:
            async with AsyncSessionLocal() as db:
                c = Campaign(advertiser_id=uid, name="P", type="promo", message_text="h",
                             status="paused", segment={})
                db.add(c)
                await db.commit()
                adv = await db.get(User, uid)
                msg = await preflight_campaign_send(db, c, adv)
            assert msg is not None and "plan" in msg
        finally:
            await _cleanup([uid])
