"""Real-DB tests for app.services.campaign_stats_service.compute_campaign_stats.

Regression cover for the "800% delivery rate" bug: send_whatsapp_message
never bumped Campaign.stats["sent"] while every WhatsApp delivery-status
webhook did stats[x] += 1 with no dedupe, so delivered/read/failed drifted
above sent. Stats are now recomputed from messages.status on read using a
monotonic funnel (read implies delivered implies sent).
"""
import uuid

import pytest
from sqlalchemy import delete

from app.database import AsyncSessionLocal, engine
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.coupon import Coupon
from app.models.message import Message
from app.models.user import User
from app.services.campaign_stats_service import compute_campaign_stats, merge_stats


async def _seed_user():
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x")
        db.add(user)
        await db.commit()
        return user.id


async def _cleanup(user_ids):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Coupon).where(Coupon.advertiser_id.in_(user_ids)))
        await db.execute(delete(Message).where(Message.advertiser_id.in_(user_ids)))
        await db.execute(delete(Campaign).where(Campaign.advertiser_id.in_(user_ids)))
        await db.execute(delete(Contact).where(Contact.advertiser_id.in_(user_ids)))
        await db.execute(delete(User).where(User.id.in_(user_ids)))
        await db.commit()
    await engine.dispose()


class TestComputeCampaignStats:
    @pytest.mark.asyncio
    async def test_empty_ids_returns_empty(self):
        async with AsyncSessionLocal() as db:
            assert await compute_campaign_stats(db, []) == {}

    @pytest.mark.asyncio
    async def test_funnel_is_monotonic_and_rate_never_exceeds_100(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                contact = Contact(advertiser_id=user_id, name="C", phone="+521000000009", status="active")
                camp = Campaign(advertiser_id=user_id, name="P", type="promo", message_text="h", status="completed")
                db.add_all([contact, camp])
                await db.commit()
                cid = camp.id
                # 1 queued, 1 sent, 6 read, 2 failed — the exact shape of the
                # production campaign that rendered "800% Entrega".
                rows = [("queued", 1), ("sent", 1), ("read", 6), ("failed", 2)]
                db.add_all([
                    Message(advertiser_id=user_id, contact_id=contact.id, campaign_id=cid,
                            direction="outbound", content="x", status=st)
                    for st, n in rows for _ in range(n)
                ])
                # an inbound row must be ignored
                db.add(Message(advertiser_id=user_id, contact_id=contact.id, campaign_id=cid,
                               direction="inbound", content="hi", status="delivered"))
                await db.commit()

            async with AsyncSessionLocal() as db:
                stats = (await compute_campaign_stats(db, [cid]))[cid]

            assert stats["queued"] == 1
            assert stats["read"] == 6
            assert stats["delivered"] == 6      # delivered(0) + read(6)
            assert stats["sent"] == 7           # sent(1) + delivered(0) + read(6)
            assert stats["failed"] == 2
            assert stats["delivered"] <= stats["sent"]
            assert round(stats["delivered"] / stats["sent"] * 100) <= 100
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_counts_only_redeemed_coupons(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                contact = Contact(advertiser_id=user_id, name="C", phone="+521000000010", status="active")
                camp = Campaign(advertiser_id=user_id, name="P", type="promo", message_text="h", status="completed")
                db.add_all([contact, camp])
                await db.commit()
                cid = camp.id
                from datetime import datetime, timedelta, timezone
                now = datetime.now(timezone.utc)
                expiry = now + timedelta(days=7)
                db.add_all([
                    Coupon(advertiser_id=user_id, contact_id=contact.id, campaign_id=cid,
                           code=f"A-{uuid.uuid4().hex[:8]}", expires_at=expiry, redeemed_at=now),
                    Coupon(advertiser_id=user_id, contact_id=contact.id, campaign_id=cid,
                           code=f"B-{uuid.uuid4().hex[:8]}", expires_at=expiry),
                ])
                await db.commit()

            async with AsyncSessionLocal() as db:
                stats = (await compute_campaign_stats(db, [cid]))[cid]

            assert stats["coupons_redeemed"] == 1
        finally:
            await _cleanup([user_id])

    def test_merge_stats_keeps_replied_from_stored_json(self):
        merged = merge_stats({"replied": 3, "sent": 999}, {"sent": 7, "delivered": 5})
        assert merged["replied"] == 3
        assert merged["sent"] == 7
        assert merged["delivered"] == 5
