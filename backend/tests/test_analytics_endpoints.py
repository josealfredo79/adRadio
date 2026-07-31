"""Real-DB integration tests for analytics.py — zero coverage existed
before this file. Covers optimal-send-time's hourly bucketing (inbound
only), summary's rate math (delivery/read/response %), campaign
performance's per-status breakdown, trends' daily bucketing, and
top-contacts' ranking + name/phone lookup. Like `Message.contact_id`
(see test_profile_endpoints.py), `Conversation.contact_id` is also
typed `UUID | None` in the ORM but is NOT NULL in the real DB schema
(migration 0001) — always supplied here to match live behavior."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete

from app.api.v1.analytics import (
    analytics_summary,
    analytics_trends,
    campaign_performance,
    optimal_send_time,
    top_contacts,
)
from app.database import AsyncSessionLocal, engine
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.order import Order
from app.models.user import User


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
        await db.execute(delete(Message).where(Message.advertiser_id.in_(user_ids)))
        await db.execute(delete(Conversation).where(Conversation.advertiser_id.in_(user_ids)))
        await db.execute(delete(Order).where(Order.advertiser_id.in_(user_ids)))
        await db.execute(delete(Campaign).where(Campaign.advertiser_id.in_(user_ids)))
        await db.execute(delete(Contact).where(Contact.advertiser_id.in_(user_ids)))
        await db.execute(delete(User).where(User.id.in_(user_ids)))
        await db.commit()
    await engine.dispose()


class TestOptimalSendTime:
    @pytest.mark.asyncio
    async def test_buckets_inbound_only_by_hour(self):
        user_id = await _seed_user()
        try:
            now = datetime.now(timezone.utc)
            async with AsyncSessionLocal() as db:
                contact = Contact(advertiser_id=user_id, name="C", phone="+521000000001", status="active")
                db.add(contact)
                await db.commit()
                db.add_all([
                    Message(advertiser_id=user_id, contact_id=contact.id, direction="inbound", content="a", created_at=now),
                    Message(advertiser_id=user_id, contact_id=contact.id, direction="inbound", content="b", created_at=now),
                    Message(advertiser_id=user_id, contact_id=contact.id, direction="inbound", content="c", created_at=now - timedelta(hours=12)),
                    Message(advertiser_id=user_id, contact_id=contact.id, direction="outbound", content="d", created_at=now),
                ])
                await db.commit()

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                data = await optimal_send_time(current_user=user, db=db)

            assert len(data["hours"]) == 24
            assert sum(h["count"] for h in data["hours"]) == 3  # outbound excluded
            assert any(h["count"] == 2 for h in data["hours"])
            assert any(h["count"] == 1 for h in data["hours"])
            assert 0 <= data["best_hour"] <= 22
            assert "–" in data["best_window"]
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_no_data_returns_all_zero_buckets(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                data = await optimal_send_time(current_user=user, db=db)
            assert all(h["count"] == 0 for h in data["hours"])
        finally:
            await _cleanup([user_id])


class TestAnalyticsSummary:
    @pytest.mark.asyncio
    async def test_computes_rates_from_seeded_data(self):
        user_id = await _seed_user()
        try:
            now = datetime.now(timezone.utc)
            async with AsyncSessionLocal() as db:
                contact_active = Contact(advertiser_id=user_id, name="A", phone="+521000000001", status="active")
                contact_active2 = Contact(advertiser_id=user_id, name="B", phone="+521000000002", status="active")
                contact_unsub = Contact(advertiser_id=user_id, name="C", phone="+521000000003", status="unsubscribed")
                db.add_all([contact_active, contact_active2, contact_unsub])
                await db.commit()

                db.add_all([
                    # 2 "sent" (non-queued) outbound: 1 delivered+read, 1 delivered only
                    Message(advertiser_id=user_id, contact_id=contact_active.id, direction="outbound",
                            content="x", status="delivered", delivered_at=now, read_at=now, created_at=now),
                    Message(advertiser_id=user_id, contact_id=contact_active.id, direction="outbound",
                            content="x", status="delivered", delivered_at=now, created_at=now),
                    # 1 still queued (excluded from "sent")
                    Message(advertiser_id=user_id, contact_id=contact_active.id, direction="outbound",
                            content="x", status="queued", created_at=now),
                    # 1 failed
                    Message(advertiser_id=user_id, contact_id=contact_active.id, direction="outbound",
                            content="x", status="failed", created_at=now),
                    # 2 inbound (replies)
                    Message(advertiser_id=user_id, contact_id=contact_active.id, direction="inbound", content="y", created_at=now),
                    Message(advertiser_id=user_id, contact_id=contact_active2.id, direction="inbound", content="y", created_at=now),
                ])
                db.add_all([
                    Campaign(advertiser_id=user_id, name="Activa", type="promo", message_text="hola", status="running"),
                    Campaign(advertiser_id=user_id, name="Vieja", type="promo", message_text="hola", status="completed"),
                ])
                db.add(Order(advertiser_id=user_id, state="confirmed"))
                db.add(Conversation(advertiser_id=user_id, contact_id=contact_active.id, status="active"))
                await db.commit()

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                data = await analytics_summary(current_user=user, db=db)

            assert data["totals"]["messages_outbound"] == 4
            assert data["totals"]["messages_inbound"] == 2
            assert data["totals"]["sent"] == 3  # non-queued: delivered, delivered, failed
            assert data["totals"]["delivered"] == 2
            assert data["totals"]["read"] == 1
            assert data["totals"]["replied"] == 2
            assert data["totals"]["failed"] == 1
            assert data["rates"]["delivery_rate"] == round(2 / 3 * 100, 1)
            assert data["rates"]["read_rate"] == round(1 / 3 * 100, 1)
            assert data["rates"]["response_rate"] == round(2 / 3 * 100, 1)
            assert data["business"]["active_contacts"] == 2
            assert data["business"]["total_campaigns"] == 2
            assert data["business"]["active_campaigns"] == 1
            assert data["business"]["orders_confirmed"] == 1
            assert data["business"]["conversations_active"] == 1
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_no_data_reports_zero_rates_not_division_error(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                data = await analytics_summary(current_user=user, db=db)
            assert data["rates"] == {"delivery_rate": 0.0, "read_rate": 0.0, "response_rate": 0.0}
        finally:
            await _cleanup([user_id])


class TestCampaignPerformance:
    @pytest.mark.asyncio
    async def test_breaks_down_message_status_per_campaign(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                contact = Contact(advertiser_id=user_id, name="C", phone="+521000000001", status="active")
                campaign = Campaign(advertiser_id=user_id, name="Promo", type="promo", message_text="hola", status="completed")
                db.add_all([contact, campaign])
                await db.commit()

                db.add_all([
                    Message(advertiser_id=user_id, contact_id=contact.id, campaign_id=campaign.id,
                            direction="outbound", content="a", status="delivered"),
                    Message(advertiser_id=user_id, contact_id=contact.id, campaign_id=campaign.id,
                            direction="outbound", content="b", status="read"),
                    Message(advertiser_id=user_id, contact_id=contact.id, campaign_id=campaign.id,
                            direction="outbound", content="c", status="failed"),
                    Message(advertiser_id=user_id, contact_id=contact.id, campaign_id=campaign.id,
                            direction="outbound", content="d", status="failed"),
                ])
                await db.commit()
                campaign_id = campaign.id

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                result = await campaign_performance(current_user=user, db=db, days=30)

            assert len(result) == 1
            entry = result[0]
            assert entry["campaign_id"] == str(campaign_id)
            assert entry["breakdown"] == {"delivered": 1, "read": 1, "failed": 2}
            assert entry["delivery_rate"] == round(1 / 4 * 100, 1)
            assert entry["read_rate"] == round(1 / 4 * 100, 1)
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_excludes_campaigns_outside_the_day_window(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                old = Campaign(
                    advertiser_id=user_id, name="Vieja", type="promo", message_text="hola", status="completed",
                    created_at=datetime.now(timezone.utc) - timedelta(days=60),
                )
                db.add(old)
                await db.commit()

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                result = await campaign_performance(current_user=user, db=db, days=30)
            assert result == []
        finally:
            await _cleanup([user_id])


class TestAnalyticsTrends:
    @pytest.mark.asyncio
    async def test_buckets_outbound_by_day_within_window(self):
        user_id = await _seed_user()
        try:
            now = datetime.now(timezone.utc)
            async with AsyncSessionLocal() as db:
                contact = Contact(advertiser_id=user_id, name="C", phone="+521000000001", status="active")
                db.add(contact)
                await db.commit()
                db.add_all([
                    Message(advertiser_id=user_id, contact_id=contact.id, direction="outbound", content="a", created_at=now),
                    Message(advertiser_id=user_id, contact_id=contact.id, direction="outbound", content="b", created_at=now),
                    Message(advertiser_id=user_id, contact_id=contact.id, direction="inbound", content="c", created_at=now),
                    Message(advertiser_id=user_id, contact_id=contact.id, direction="outbound", content="d", created_at=now - timedelta(days=40)),
                ])
                await db.commit()

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                data = await analytics_trends(current_user=user, db=db, days=30)

            assert len(data["days"]) == 30
            assert data["total"] == 2  # only the 2 outbound within the window
            today_entry = next(d for d in data["days"] if d["date"] == now.date().isoformat())
            assert today_entry["mensajes"] == 2
        finally:
            await _cleanup([user_id])


class TestTopContacts:
    @pytest.mark.asyncio
    async def test_ranks_contacts_by_message_volume(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                busy = Contact(advertiser_id=user_id, name="Ocupado", phone="+521000000001", status="active")
                quiet = Contact(advertiser_id=user_id, name="Tranquilo", phone="+521000000002", status="active")
                db.add_all([busy, quiet])
                await db.commit()

                db.add_all([
                    Message(advertiser_id=user_id, contact_id=busy.id, direction="outbound", content="a"),
                    Message(advertiser_id=user_id, contact_id=busy.id, direction="inbound", content="b"),
                    Message(advertiser_id=user_id, contact_id=busy.id, direction="outbound", content="c"),
                    Message(advertiser_id=user_id, contact_id=quiet.id, direction="outbound", content="d"),
                ])
                await db.commit()

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                result = await top_contacts(current_user=user, db=db, limit=10)

            assert len(result) == 2
            assert result[0]["name"] == "Ocupado"
            assert result[0]["total_messages"] == 3
            assert result[1]["name"] == "Tranquilo"
            assert result[1]["total_messages"] == 1
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_no_messages_returns_empty_list(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                result = await top_contacts(current_user=user, db=db, limit=10)
            assert result == []
        finally:
            await _cleanup([user_id])
