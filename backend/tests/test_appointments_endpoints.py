"""Real-DB integration tests for appointments.py — zero coverage existed
before this file (only reminder-sending logic was tested, via
test_tasks_helpers.py, not this router at all). Covers CRUD ownership
scoping, stats, and the OAuth CSRF state-token signing used by the Google
Calendar connect flow (_sign_state/_verify_state) — a hand-rolled HMAC
scheme that had never been tested despite being the only thing standing
between the callback endpoint and an open redirect / state-forgery."""
import time
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import delete

from app.api.v1.appointments import (
    _sign_state,
    _verify_state,
    appointment_stats,
    create_appointment,
    delete_appointment,
    google_disconnect,
    list_appointments,
    update_appointment,
)
from app.database import AsyncSessionLocal, engine
from app.models.appointment import Appointment
from app.models.user import User
from app.schemas.appointment import AppointmentCreate, AppointmentUpdate


async def _seed_user(**kwargs):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", **kwargs)
        db.add(user)
        await db.commit()
        return user.id


async def _cleanup(user_ids):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Appointment).where(Appointment.advertiser_id.in_(user_ids)))
        await db.execute(delete(User).where(User.id.in_(user_ids)))
        await db.commit()
    await engine.dispose()


class TestStateTokenSigning:
    """_sign_state/_verify_state — the CSRF guard on the Google OAuth
    callback. Pure functions, no DB needed. Since 2026-08-13 also carries
    the PKCE code_verifier through the round trip (see calendar_service.py
    docstrings for why) — signature is now (user_id, code_verifier) ->
    (user_id, code_verifier) instead of a bare user_id string."""

    def test_valid_token_round_trips_to_same_user_id_and_verifier(self):
        user_id = str(uuid.uuid4())
        token = _sign_state(user_id, "verifier-abc")
        assert _verify_state(token) == (user_id, "verifier-abc")

    def test_tampered_signature_is_rejected(self):
        user_id = str(uuid.uuid4())
        token = _sign_state(user_id, "verifier-abc")
        tampered = token[:-2] + ("aa" if token[-2:] != "aa" else "bb")
        assert _verify_state(tampered) is None

    def test_tampered_user_id_is_rejected(self):
        """Swap in a different user_id but keep the original signature —
        must fail, or an attacker could redirect the OAuth grant to any
        account by editing the state param."""
        real_user_id = str(uuid.uuid4())
        token = _sign_state(real_user_id, "verifier-abc")
        import base64
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        payload_with_ts, sig = raw.rsplit(":", 1)
        _, ts = payload_with_ts.rsplit(":", 1)
        forged_raw = f"{uuid.uuid4()}:verifier-abc:{ts}:{sig}"
        forged_token = base64.urlsafe_b64encode(forged_raw.encode()).decode()
        assert _verify_state(forged_token) is None

    def test_expired_token_is_rejected(self):
        user_id = str(uuid.uuid4())
        with patch("app.api.v1.appointments.time.time", return_value=time.time() - 400):
            token = _sign_state(user_id, "verifier-abc")
        assert _verify_state(token) is None

    def test_garbage_token_does_not_raise(self):
        assert _verify_state("not-a-valid-token-at-all") is None

    def test_empty_token_does_not_raise(self):
        assert _verify_state("") is None


class TestListAppointments:
    @pytest.mark.asyncio
    async def test_only_returns_own_appointments(self):
        owner_id = await _seed_user()
        other_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                db.add(Appointment(advertiser_id=owner_id, customer_name="Mía", service="Corte", scheduled_at=datetime.now(timezone.utc)))
                db.add(Appointment(advertiser_id=other_id, customer_name="Ajena", service="Corte", scheduled_at=datetime.now(timezone.utc)))
                await db.commit()

            async with AsyncSessionLocal() as db:
                owner = await db.get(User, owner_id)
                result = await list_appointments(
                    status_filter=None, from_date=None, to_date=None,
                    limit=100, offset=0, current_user=owner, db=db,
                )
            assert [a.customer_name for a in result] == ["Mía"]
        finally:
            await _cleanup([owner_id, other_id])

    @pytest.mark.asyncio
    async def test_filters_by_status(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                db.add(Appointment(advertiser_id=user_id, customer_name="Pendiente", service="X", scheduled_at=datetime.now(timezone.utc), status="pending"))
                db.add(Appointment(advertiser_id=user_id, customer_name="Confirmada", service="X", scheduled_at=datetime.now(timezone.utc), status="confirmed"))
                await db.commit()

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                result = await list_appointments(
                    status_filter="confirmed", from_date=None, to_date=None,
                    limit=100, offset=0, current_user=user, db=db,
                )
            assert [a.customer_name for a in result] == ["Confirmada"]
        finally:
            await _cleanup([user_id])


class TestCreateAppointment:
    @pytest.mark.asyncio
    async def test_creates_without_google_calendar_when_not_connected(self):
        user_id = await _seed_user(google_calendar_connected=False)
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                created = await create_appointment(
                    body=AppointmentCreate(customer_name="Ana", service="Corte", scheduled_at=datetime.now(timezone.utc)),
                    current_user=user, db=db,
                )
            assert created.customer_name == "Ana"
            assert created.google_event_id is None
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_google_calendar_failure_does_not_block_creation(self):
        """create_event failing must not prevent the appointment itself
        from being saved — Calendar sync is best-effort."""
        user_id = await _seed_user(google_calendar_connected=True, google_refresh_token="fake-token")
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with patch("app.services.calendar_service.create_event", side_effect=Exception("Google down")):
                    created = await create_appointment(
                        body=AppointmentCreate(customer_name="Ana", service="Corte", scheduled_at=datetime.now(timezone.utc)),
                        current_user=user, db=db,
                    )
            assert created.customer_name == "Ana"
            assert created.google_event_id is None
        finally:
            await _cleanup([user_id])


class TestUpdateAppointment:
    @pytest.mark.asyncio
    async def test_updates_only_provided_fields(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                created = await create_appointment(
                    body=AppointmentCreate(customer_name="Ana", service="Corte", scheduled_at=datetime.now(timezone.utc)),
                    current_user=user, db=db,
                )

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                updated = await update_appointment(
                    appointment_id=created.id, body=AppointmentUpdate(status="confirmed"),
                    current_user=user, db=db,
                )
            assert updated.status == "confirmed"
            assert updated.customer_name == "Ana"
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_cannot_update_another_advertisers_appointment(self):
        owner_id = await _seed_user()
        other_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                owner = await db.get(User, owner_id)
                created = await create_appointment(
                    body=AppointmentCreate(customer_name="Ana", service="Corte", scheduled_at=datetime.now(timezone.utc)),
                    current_user=owner, db=db,
                )

            async with AsyncSessionLocal() as db:
                other = await db.get(User, other_id)
                with pytest.raises(HTTPException) as exc_info:
                    await update_appointment(
                        appointment_id=created.id, body=AppointmentUpdate(status="confirmed"),
                        current_user=other, db=db,
                    )
                assert exc_info.value.status_code == 404
        finally:
            await _cleanup([owner_id, other_id])


class TestDeleteAppointment:
    @pytest.mark.asyncio
    async def test_deletes_and_disappears_from_list(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                created = await create_appointment(
                    body=AppointmentCreate(customer_name="Temp", service="X", scheduled_at=datetime.now(timezone.utc)),
                    current_user=user, db=db,
                )

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                await delete_appointment(appointment_id=created.id, current_user=user, db=db)
                remaining = await list_appointments(
                    status_filter=None, from_date=None, to_date=None,
                    limit=100, offset=0, current_user=user, db=db,
                )
            assert remaining == []
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_unknown_appointment_returns_404(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with pytest.raises(HTTPException) as exc_info:
                    await delete_appointment(appointment_id=uuid.uuid4(), current_user=user, db=db)
            assert exc_info.value.status_code == 404
        finally:
            await _cleanup([user_id])


class TestAppointmentStats:
    @pytest.mark.asyncio
    async def test_counts_total_upcoming_and_today(self):
        user_id = await _seed_user(google_calendar_connected=True)
        try:
            now = datetime.now(timezone.utc)
            async with AsyncSessionLocal() as db:
                db.add(Appointment(advertiser_id=user_id, customer_name="Hoy", service="X", scheduled_at=now.replace(hour=min(now.hour + 1, 23)), status="pending"))
                db.add(Appointment(advertiser_id=user_id, customer_name="Futura", service="X", scheduled_at=now + timedelta(days=5), status="confirmed"))
                db.add(Appointment(advertiser_id=user_id, customer_name="Pasada", service="X", scheduled_at=now - timedelta(days=5), status="completed"))
                await db.commit()

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                stats = await appointment_stats(current_user=user, db=db)
            assert stats["total"] == 3
            assert stats["upcoming"] == 2  # hoy + futura, no la pasada/completed
            assert stats["today"] == 1
            assert stats["google_connected"] is True
        finally:
            await _cleanup([user_id])


class TestGoogleDisconnect:
    @pytest.mark.asyncio
    async def test_clears_refresh_token_and_flag(self):
        user_id = await _seed_user(google_calendar_connected=True, google_refresh_token="secret-token")
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                result = await google_disconnect(current_user=user, db=db)
            assert "desconectado" in result["message"]

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
            assert user.google_calendar_connected is False
            assert user.google_refresh_token is None
        finally:
            await _cleanup([user_id])
