"""
Appointments router — /api/v1/appointments
CRUD de citas + flujo OAuth de Google Calendar.
"""
import base64
import hashlib
import hmac
import logging
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import settings
from app.database import get_db
from app.models.appointment import Appointment
from app.models.user import User
from app.schemas.appointment import AppointmentCreate, AppointmentOut, AppointmentUpdate

logger = logging.getLogger(__name__)


def _sign_state(user_id: str, code_verifier: str) -> str:
    """Create a signed, time-limited state token for OAuth.

    Carries the PKCE code_verifier alongside the user_id — Google echoes
    `state` back verbatim in the callback, so this round-trips the verifier
    through the redirect without needing separate server-side storage (see
    calendar_service.py's get_auth_url/exchange_code docstrings for why a
    verifier can't just be regenerated fresh in the callback). Safe to
    concatenate with ":" since code_verifier's charset (RFC 7636: A-Za-z0-9
    plus "-._~") never contains ":"."""
    payload = f"{user_id}:{code_verifier}:{int(time.time())}"
    sig = hmac.new(settings.SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
    token = base64.urlsafe_b64encode(f"{payload}:{sig}".encode()).decode()
    return token


def _verify_state(token: str) -> tuple[str, str] | None:
    """Verify and decode state token. Returns (user_id, code_verifier) or
    None if invalid/expired."""
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        parts = raw.rsplit(":", 1)
        if len(parts) != 2:
            return None
        payload_with_ts, received_sig = parts
        ts_parts = payload_with_ts.rsplit(":", 1)
        if len(ts_parts) != 2:
            return None
        user_id_and_verifier, ts_str = ts_parts
        uv_parts = user_id_and_verifier.split(":", 1)
        if len(uv_parts) != 2:
            return None
        user_id, code_verifier = uv_parts
        ts = int(ts_str)
        if abs(int(time.time()) - ts) > 300:
            return None
        payload = f"{user_id}:{code_verifier}:{ts}"
        expected_sig = hmac.new(settings.SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
        if not hmac.compare_digest(received_sig, expected_sig):
            return None
        return user_id, code_verifier
    except Exception:
        logger.warning("[APPOINTMENTS] Failed to verify state token", exc_info=True)
        return None

router = APIRouter(prefix="/appointments", tags=["appointments"])


# ── CRUD ─────────────────────────────────────────────────────────────────────


@router.get("", response_model=list[AppointmentOut])
async def list_appointments(
    status_filter: str | None = Query(None, alias="status"),
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AppointmentOut]:
    """List appointments for the authenticated advertiser."""
    q = select(Appointment).where(Appointment.advertiser_id == current_user.id)

    if status_filter:
        q = q.where(Appointment.status == status_filter)
    if from_date:
        q = q.where(Appointment.scheduled_at >= from_date)
    if to_date:
        q = q.where(Appointment.scheduled_at <= to_date)

    q = q.order_by(Appointment.scheduled_at.asc()).limit(limit).offset(offset)
    result = await db.execute(q)
    return [AppointmentOut.model_validate(a) for a in result.scalars().all()]


@router.post("", response_model=AppointmentOut, status_code=status.HTTP_201_CREATED)
async def create_appointment(
    body: AppointmentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AppointmentOut:
    """Create a new appointment. Syncs to Google Calendar if connected."""
    appointment = Appointment(
        advertiser_id=current_user.id,
        **body.model_dump(),
    )
    db.add(appointment)

    # Sync to Google Calendar if connected
    if current_user.google_calendar_connected and current_user.google_refresh_token:
        try:
            from app.services.calendar_service import create_event

            event_id = create_event(
                refresh_token=current_user.google_refresh_token,
                summary=f"📅 {body.service} — {body.customer_name}",
                description=f"Cliente: {body.customer_name}\nTeléfono: {body.customer_phone or 'N/A'}\nNotas: {body.notes or '—'}",
                start_dt=body.scheduled_at,
                duration_min=body.duration_min,
                customer_phone=body.customer_phone,
            )
            appointment.google_event_id = event_id
        except Exception as e:
            logger.warning("[APPOINTMENTS] Google Calendar sync failed: %s", e)

    await db.commit()
    await db.refresh(appointment)
    return AppointmentOut.model_validate(appointment)


@router.patch("/{appointment_id}", response_model=AppointmentOut)
async def update_appointment(
    appointment_id: uuid.UUID,
    body: AppointmentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AppointmentOut:
    """Update an appointment. Syncs changes to Google Calendar."""
    result = await db.execute(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.advertiser_id == current_user.id,
        )
    )
    appointment = result.scalar_one_or_none()
    if not appointment:
        raise HTTPException(status_code=404, detail="Cita no encontrada")

    update_data = body.model_dump(exclude_none=True)
    for field, value in update_data.items():
        setattr(appointment, field, value)

    # Sync to Google Calendar
    if appointment.google_event_id and current_user.google_refresh_token:
        try:
            if body.status == "cancelled":
                from app.services.calendar_service import delete_event
                delete_event(current_user.google_refresh_token, appointment.google_event_id)
                appointment.google_event_id = None
            elif body.scheduled_at or body.service:
                from app.services.calendar_service import update_event
                update_event(
                    refresh_token=current_user.google_refresh_token,
                    event_id=appointment.google_event_id,
                    summary=f"📅 {appointment.service} — {appointment.customer_name}" if body.service else None,
                    start_dt=body.scheduled_at,
                    duration_min=body.duration_min or appointment.duration_min,
                )
        except Exception as e:
            logger.warning("[APPOINTMENTS] Google Calendar sync failed: %s", e)

    await db.commit()
    await db.refresh(appointment)
    return AppointmentOut.model_validate(appointment)


@router.delete("/{appointment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_appointment(
    appointment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete an appointment and remove from Google Calendar."""
    result = await db.execute(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.advertiser_id == current_user.id,
        )
    )
    appointment = result.scalar_one_or_none()
    if not appointment:
        raise HTTPException(status_code=404, detail="Cita no encontrada")

    # Remove from Google Calendar
    if appointment.google_event_id and current_user.google_refresh_token:
        try:
            from app.services.calendar_service import delete_event
            delete_event(current_user.google_refresh_token, appointment.google_event_id)
        except Exception:
            logger.warning("[APPOINTMENTS] Failed to delete Google Calendar event", exc_info=True)

    await db.delete(appointment)
    await db.commit()


@router.get("/stats")
async def appointment_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Quick stats for the appointments dashboard."""
    now = datetime.now(timezone.utc)

    total = (await db.execute(
        select(func.count()).select_from(Appointment).where(Appointment.advertiser_id == current_user.id)
    )).scalar() or 0

    upcoming = (await db.execute(
        select(func.count()).select_from(Appointment).where(
            Appointment.advertiser_id == current_user.id,
            Appointment.scheduled_at >= now,
            Appointment.status.in_(["pending", "confirmed"]),
        )
    )).scalar() or 0

    today_count = (await db.execute(
        select(func.count()).select_from(Appointment).where(
            Appointment.advertiser_id == current_user.id,
            func.date(Appointment.scheduled_at) == now.date(),
            Appointment.status.in_(["pending", "confirmed"]),
        )
    )).scalar() or 0

    return {
        "total": total,
        "upcoming": upcoming,
        "today": today_count,
        "google_connected": current_user.google_calendar_connected,
    }


# ── Google Calendar OAuth ────────────────────────────────────────────────────


@router.get("/google/connect")
async def google_connect(
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Redirect user to Google OAuth consent screen."""
    if not settings.GOOGLE_CALENDAR_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Google Calendar no configurado")

    import secrets

    from app.services.calendar_service import get_auth_url

    redirect_uri = f"{settings.BASE_URL}/api/v1/appointments/google/callback"
    code_verifier = secrets.token_urlsafe(96)  # RFC 7636: 43-128 chars
    state = _sign_state(str(current_user.id), code_verifier)
    url = get_auth_url(redirect_uri, state, code_verifier)
    return {"auth_url": url}


@router.get("/google/callback")
async def google_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Handle Google OAuth callback — exchange code for refresh token."""
    from app.services.calendar_service import exchange_code

    redirect_uri = f"{settings.BASE_URL}/api/v1/appointments/google/callback"

    try:
        verified = _verify_state(state)
        if not verified:
            logger.warning("[GCAL] Invalid state token: %s", state)
            return RedirectResponse(f"{settings.FRONTEND_URL}/app/appointments?error=invalid_state")
        user_id, code_verifier = verified

        refresh_token = exchange_code(code, redirect_uri, code_verifier)
    except Exception as e:
        logger.error("[GCAL] OAuth exchange failed: %s", e, exc_info=True)
        error_detail = str(e)[:200] if str(e) else "unknown"
        return RedirectResponse(f"{settings.FRONTEND_URL}/app/appointments?error=oauth_failed&detail={error_detail}")

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        return RedirectResponse(f"{settings.FRONTEND_URL}/app/appointments?error=user_not_found")

    user.google_refresh_token = refresh_token
    user.google_calendar_connected = True
    await db.commit()

    return RedirectResponse(f"{settings.FRONTEND_URL}/app/appointments?connected=true")


@router.delete("/google/disconnect")
async def google_disconnect(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Disconnect Google Calendar."""
    current_user.google_refresh_token = None
    current_user.google_calendar_connected = False
    await db.commit()
    return {"message": "Google Calendar desconectado"}
