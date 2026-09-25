"""Regression tests for the 2026-09-18 core-actions-gap fixes in
copilot_service.py: the Copiloto (chat CRM) let an advertiser double-book
an appointment slot and launch a campaign missing the content its mode
requires — both already blocked on the REST side, neither blocked here.
Real-DB integration, same pattern as test_appointment_booking_service.py."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select

from app.database import AsyncSessionLocal, engine
from app.models.appointment import Appointment
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.user import User
from app.services.copilot_service import (
    _execute_launch_campaign,
    _execute_schedule_appointment,
)


async def _seed_user(**overrides):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", **overrides)
        db.add(user)
        await db.commit()
        return user.id


async def _seed_contact(advertiser_id, **overrides):
    async with AsyncSessionLocal() as db:
        contact = Contact(advertiser_id=advertiser_id, name="Ana Torres", phone="+525511112222", **overrides)
        db.add(contact)
        await db.commit()
        return contact.id


async def _cleanup(user_ids):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Appointment).where(Appointment.advertiser_id.in_(user_ids)))
        await db.execute(delete(Campaign).where(Campaign.advertiser_id.in_(user_ids)))
        await db.execute(delete(Contact).where(Contact.advertiser_id.in_(user_ids)))
        await db.execute(delete(User).where(User.id.in_(user_ids)))
        await db.commit()
    await engine.dispose()


class TestExecuteScheduleAppointmentConflict:
    @pytest.mark.asyncio
    async def test_rejects_double_booking_same_slot(self):
        user_id = await _seed_user()
        contact_id = await _seed_contact(user_id)
        try:
            when = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=1)
            async with AsyncSessionLocal() as db:
                db.add(Appointment(
                    advertiser_id=user_id, contact_id=contact_id, customer_name="Existente",
                    service="Corte", scheduled_at=when, duration_min=30, status="confirmed",
                ))
                await db.commit()

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                result, error = await _execute_schedule_appointment(
                    db, user,
                    {"contact_id": str(contact_id), "datetime_iso": when.isoformat(), "service": "Tinte"},
                )
            assert result is None
            assert "Ya tienes una cita" in error

            async with AsyncSessionLocal() as db:
                count = (await db.execute(
                    select(Appointment).where(Appointment.advertiser_id == user_id)
                )).scalars().all()
            assert len(count) == 1  # no se creó una segunda
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_allows_non_conflicting_slot(self):
        user_id = await _seed_user()
        contact_id = await _seed_contact(user_id)
        try:
            when = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=1)
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                result, error = await _execute_schedule_appointment(
                    db, user,
                    {"contact_id": str(contact_id), "datetime_iso": when.isoformat(), "service": "Corte"},
                )
            assert error is None
            assert result["customer_name"] == "Ana Torres"
        finally:
            await _cleanup([user_id])


class TestExecuteLaunchCampaignContentCheck:
    @pytest.mark.asyncio
    async def test_rejects_empty_regular_campaign(self):
        user_id = await _seed_user()
        async with AsyncSessionLocal() as db:
            campaign = Campaign(
                advertiser_id=user_id, name="Vacía", type="promo", message_text="",
                status="draft", ab_test={"enabled": False, "campaign_mode": "regular"},
            )
            db.add(campaign)
            await db.commit()
            await db.refresh(campaign)
            campaign_id = campaign.id
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                result, error = await _execute_launch_campaign(db, user, {"campaign_id": str(campaign_id)})
            assert result is None
            assert "mensaje" in error.lower()

            async with AsyncSessionLocal() as db:
                reloaded = await db.get(Campaign, campaign_id)
            assert reloaded.status == "draft"  # no se lanzó
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_rejects_radio_campaign_without_audio(self):
        user_id = await _seed_user()
        async with AsyncSessionLocal() as db:
            campaign = Campaign(
                advertiser_id=user_id, name="Radio sin audio", type="promo", message_text="Hola",
                status="draft", ab_test={"enabled": False, "campaign_mode": "radio"},
            )
            db.add(campaign)
            await db.commit()
            await db.refresh(campaign)
            campaign_id = campaign.id
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                result, error = await _execute_launch_campaign(db, user, {"campaign_id": str(campaign_id)})
            assert result is None
            assert "audio" in error.lower()
        finally:
            await _cleanup([user_id])
