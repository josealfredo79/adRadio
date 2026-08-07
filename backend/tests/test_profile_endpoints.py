"""Real-DB integration tests for profile.py — zero coverage existed
before this file. Covers /me GET/PATCH, change-password, the
white-label feature gate, and the dashboard/dashboard-chart aggregate
queries. Checked `UserOut` against the `User` model for the
str/UUID/datetime response-typing bug seen in Admin/Public API/User
Webhooks — already correctly typed (`id: uuid.UUID`), no bug found."""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy import delete

from app.api.v1.profile import (
    ChangePasswordBody,
    WhiteLabelUpdate,
    change_password,
    dashboard,
    dashboard_chart,
    get_profile,
    get_white_label,
    update_profile,
    update_white_label,
)
from app.core.security import hash_password
from app.database import AsyncSessionLocal, engine
from app.models.automation import AutomationFlow
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.coupon import Coupon
from app.models.message import Message
from app.models.order import Order
from app.models.user import User
from app.schemas.profile import ProfileUpdate


async def _seed_user(current_plan: str = "trial", password: str = "old-password-123"):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(
            email=f"{uuid.uuid4()}@test.com", password_hash=hash_password(password),
            current_plan=current_plan, subscription_status="active",
        )
        db.add(user)
        await db.commit()
        return user.id


async def _cleanup(user_ids):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Coupon).where(Coupon.advertiser_id.in_(user_ids)))
        await db.execute(delete(Message).where(Message.advertiser_id.in_(user_ids)))
        await db.execute(delete(Order).where(Order.advertiser_id.in_(user_ids)))
        await db.execute(delete(Campaign).where(Campaign.advertiser_id.in_(user_ids)))
        await db.execute(delete(AutomationFlow).where(AutomationFlow.advertiser_id.in_(user_ids)))
        await db.execute(delete(Contact).where(Contact.advertiser_id.in_(user_ids)))
        await db.execute(delete(User).where(User.id.in_(user_ids)))
        await db.commit()
    await engine.dispose()


class TestGetProfile:
    @pytest.mark.asyncio
    async def test_returns_current_user(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                out = await get_profile(current_user=user)
            assert out.id == user_id
            assert out.current_plan == "trial"
        finally:
            await _cleanup([user_id])


class TestUpdateProfile:
    @pytest.mark.asyncio
    async def test_updates_provided_fields_only(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                out = await update_profile(
                    body=ProfileUpdate(business_name="Tacos El Primo", city="CDMX"),
                    db=db, current_user=user,
                )
            assert out.business_name == "Tacos El Primo"
            assert out.city == "CDMX"

            async with AsyncSessionLocal() as db:
                reloaded = await db.get(User, user_id)
                assert reloaded.business_name == "Tacos El Primo"
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_rejects_invalid_phone_format(self):
        with pytest.raises(ValueError):
            ProfileUpdate(phone="5511112222")


class TestChangePassword:
    @pytest.mark.asyncio
    async def test_wrong_current_password_returns_400(self):
        user_id = await _seed_user(password="correct-horse-battery")
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with pytest.raises(HTTPException) as exc_info:
                    await change_password(
                        request=MagicMock(headers={}),
                        body=ChangePasswordBody(current_password="wrong-one", new_password="newpassword123"),
                        db=db, current_user=user, _=None, redis=None,
                    )
                assert exc_info.value.status_code == 400
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_new_password_too_short_returns_400(self):
        user_id = await _seed_user(password="correct-horse-battery")
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with pytest.raises(HTTPException) as exc_info:
                    await change_password(
                        request=MagicMock(headers={}),
                        body=ChangePasswordBody(current_password="correct-horse-battery", new_password="short"),
                        db=db, current_user=user, _=None, redis=None,
                    )
                assert exc_info.value.status_code == 400
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_successful_change_updates_hash(self):
        from app.core.security import verify_password

        user_id = await _seed_user(password="correct-horse-battery")
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                result = await change_password(
                    request=MagicMock(headers={}),
                    body=ChangePasswordBody(current_password="correct-horse-battery", new_password="newpassword123"),
                    db=db, current_user=user, _=None, redis=None,
                )
            assert "message" in result

            async with AsyncSessionLocal() as db:
                reloaded = await db.get(User, user_id)
                assert verify_password("newpassword123", reloaded.password_hash)
                assert not verify_password("correct-horse-battery", reloaded.password_hash)
        finally:
            await _cleanup([user_id])


class TestWhiteLabel:
    @pytest.mark.asyncio
    async def test_get_blocked_below_enterprise_plan(self):
        user_id = await _seed_user(current_plan="business")
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with pytest.raises(HTTPException) as exc_info:
                    await get_white_label(current_user=user)
                assert exc_info.value.status_code == 402
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_get_returns_defaults_when_unset(self):
        user_id = await _seed_user(current_plan="enterprise")
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                out = await get_white_label(current_user=user)
            assert out.primary_color == "#6366f1"
            assert out.hide_branding is False
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_update_merges_partial_fields_and_persists(self):
        user_id = await _seed_user(current_plan="enterprise")
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                await update_white_label(
                    body=WhiteLabelUpdate(app_name="Mi Radio"), db=db, current_user=user,
                )

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                out = await update_white_label(
                    body=WhiteLabelUpdate(primary_color="#ff0000"), db=db, current_user=user,
                )
            assert out.app_name == "Mi Radio"
            assert out.primary_color == "#ff0000"
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_update_blocked_below_enterprise_plan(self):
        user_id = await _seed_user(current_plan="business")
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with pytest.raises(HTTPException) as exc_info:
                    await update_white_label(
                        body=WhiteLabelUpdate(app_name="X"), db=db, current_user=user,
                    )
                assert exc_info.value.status_code == 402
        finally:
            await _cleanup([user_id])


class TestDashboard:
    @pytest.mark.asyncio
    async def test_zero_data_reports_zeros_not_error(self):
        user_id = await _seed_user(current_plan="growth")
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                data = await dashboard(db=db, current_user=user, redis=None)
            assert data["contacts_total"] == 0
            assert data["campaigns_active"] == 0
            assert data["automations_active"] == 0
            assert data["messages_sent_this_month"] == 0
            assert data["orders_confirmed"] == 0
            assert data["orders_pending"] == 0
            assert data["leads_from_bot"] == 0
            assert data["plan_requests"] == 0
            assert data["leads_unreplied"] == 0
            assert data["plan"] == "growth"
            assert data["engagement"] == {"hot": 0, "warm": 0, "cold": 0}
            assert data["coupons"] == {"issued": 0, "redeemed": 0, "redemption_rate": 0.0}
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_counts_reflect_seeded_data(self):
        user_id = await _seed_user()
        try:
            now = datetime.now(timezone.utc)
            first_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            last_month = first_of_month - timedelta(days=5)

            async with AsyncSessionLocal() as db:
                contact_activo = Contact(advertiser_id=user_id, name="Activo", phone="+521000000001", status="active", engagement_score=85)
                contact_unreplied = Contact(advertiser_id=user_id, name="SinRespuesta", phone="+521000000004", status="active", engagement_score=45)
                contact_replied = Contact(advertiser_id=user_id, name="Respondido", phone="+521000000005", status="active", engagement_score=10)
                db.add_all([
                    contact_activo,
                    Contact(advertiser_id=user_id, name="Baja", phone="+521000000002", status="unsubscribed", engagement_score=99),
                    Contact(advertiser_id=user_id, name="Lead", phone="+521000000003", status="active",
                            source="landing", created_at=now),  # engagement_score defaults to 0 -> cold
                    contact_unreplied,
                    contact_replied,
                    Campaign(advertiser_id=user_id, name="Activa", type="promo", message_text="hola", status="running"),
                    Campaign(advertiser_id=user_id, name="Borrador", type="promo", message_text="hola", status="draft"),
                    AutomationFlow(advertiser_id=user_id, name="Activo", is_active=True),
                    AutomationFlow(advertiser_id=user_id, name="Inactivo", is_active=False),
                    Order(advertiser_id=user_id, state="confirmed"),
                    Order(advertiser_id=user_id, state="collecting_name"),
                    Order(advertiser_id=user_id, state="cancelled"),
                    Order(advertiser_id=user_id, state="plan_pending_confirmation"),
                    Coupon(advertiser_id=user_id, code="ISSUED1", expires_at=now + timedelta(days=30)),
                    Coupon(advertiser_id=user_id, code="REDEEMED1", expires_at=now + timedelta(days=30), used_count=1),
                ])
                await db.commit()

                # Messages this month vs. last month, plus reply-state per contact
                # (Message.contact_id is required by the live DB schema — the ORM's
                # `Mapped[uuid.UUID | None]` claims it's optional but the original
                # migration 0001 declared it NOT NULL and no later migration relaxed
                # it, so every real send path always supplies one anyway.)
                db.add_all([
                    Message(advertiser_id=user_id, contact_id=contact_activo.id, direction="outbound", content="hola", created_at=now),
                    Message(advertiser_id=user_id, contact_id=contact_activo.id, direction="outbound", content="hola", created_at=now),
                    Message(advertiser_id=user_id, contact_id=contact_activo.id, direction="outbound", content="viejo", created_at=last_month),
                    Message(advertiser_id=user_id, contact_id=contact_unreplied.id, direction="outbound",
                            content="hola", created_at=now - timedelta(hours=2)),
                    Message(advertiser_id=user_id, contact_id=contact_unreplied.id, direction="inbound",
                            content="?", created_at=now - timedelta(hours=1)),
                    Message(advertiser_id=user_id, contact_id=contact_replied.id, direction="inbound",
                            content="?", created_at=now - timedelta(hours=2)),
                    Message(advertiser_id=user_id, contact_id=contact_replied.id, direction="outbound",
                            content="ya", created_at=now - timedelta(hours=1)),
                ])
                await db.commit()

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                data = await dashboard(db=db, current_user=user, redis=None)

            assert data["contacts_total"] == 4  # 4 active (Baja is unsubscribed, excluded)
            assert data["campaigns_active"] == 1
            assert data["automations_active"] == 1
            assert data["messages_sent_this_month"] == 4  # 2 to contact_activo + 1 to contact_unreplied + 1 to contact_replied, last_month excluded
            assert data["orders_confirmed"] == 1
            assert data["orders_pending"] == 2  # collecting_name + plan_pending_confirmation, cancelled excluded
            assert data["leads_from_bot"] == 1
            assert data["plan_requests"] == 1
            assert data["leads_unreplied"] == 1  # only contact_unreplied's latest message is inbound
            # hot=contact_activo(85), warm=contact_unreplied(45), cold=contact_replied(10)+Lead(0, default)
            # "Baja" (score 99) excluded — status=unsubscribed, not active.
            assert data["engagement"] == {"hot": 1, "warm": 1, "cold": 2}
            assert data["coupons"] == {"issued": 2, "redeemed": 1, "redemption_rate": 50.0}
        finally:
            await _cleanup([user_id])


class TestDashboardChart:
    @pytest.mark.asyncio
    async def test_returns_7_days_bucketed_by_date(self):
        user_id = await _seed_user()
        try:
            now = datetime.now(timezone.utc)
            async with AsyncSessionLocal() as db:
                contact = Contact(advertiser_id=user_id, name="Cliente", phone="+521000000009", status="active")
                db.add(contact)
                await db.commit()
                db.add_all([
                    Message(advertiser_id=user_id, contact_id=contact.id, direction="outbound", content="a", created_at=now),
                    Message(advertiser_id=user_id, contact_id=contact.id, direction="outbound", content="b", created_at=now),
                    Message(advertiser_id=user_id, contact_id=contact.id, direction="inbound", content="c", created_at=now),
                    Message(advertiser_id=user_id, contact_id=contact.id, direction="outbound", content="d", created_at=now - timedelta(days=10)),
                ])
                await db.commit()

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                days = await dashboard_chart(db=db, current_user=user, redis=None)

            assert len(days) == 7
            today_str = now.date().isoformat()
            today_entry = next(d for d in days if d["date"] == today_str)
            assert today_entry["mensajes"] == 2  # only the 2 outbound today; inbound and 10-days-ago excluded
        finally:
            await _cleanup([user_id])
