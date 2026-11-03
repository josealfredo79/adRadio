"""El aviso "tu prueba termina" llega a toda prueba, una vez, y nunca a quien
paga o está exento. Base y Redis reales; correo y WhatsApp son falsos."""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
import redis.asyncio as aioredis
from sqlalchemy import delete

from app.config import settings
from app.database import AsyncSessionLocal, _get_celery_engine, engine
from app.models.user import User
from app.workers import tasks


@pytest.fixture
def seed():
    created = []

    def make(hours_left, status="trial", exempt=False, email=None, phone=None):
        async def run():
            await engine.dispose()
            async with AsyncSessionLocal() as db:
                user = User(
                    email=email or f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Test",
                    phone=phone,
                    subscription_status=status, billing_exempt=exempt,
                    plan_expires_at=datetime.now(timezone.utc) + timedelta(hours=hours_left),
                    whatsapp_number="+525500000001",
                )
                db.add(user)
                await db.commit()
                user_id = user.id
            await engine.dispose()
            return user_id
        user_id = asyncio.run(run())
        _get_celery_engine().sync_engine.dispose(close=False)
        created.append(user_id)
        return user_id

    yield make

    async def cleanup():
        await engine.dispose()
        async with AsyncSessionLocal() as db:
            await db.execute(delete(User).where(User.id.in_(created)))
            await db.commit()
        await engine.dispose()
    asyncio.run(cleanup())


def _run():
    mail = AsyncMock()
    whatsapp = AsyncMock(return_value=("wamid.1", None))
    with patch("app.core.email.send_trial_expiring_email", mail), \
            patch("app.services.meta_service.send_whatsapp", whatsapp):
        tasks.send_trial_expiry_reminders()
    return whatsapp.await_args_list



# Antes solo entraban las de un rango de 2 h: las demás se quedaban sin aviso.
@pytest.mark.parametrize("hours_left", [70, 60, 50, 23, 13, 2])
def test_every_trial_gets_it_whatever_the_hour(seed, hours_left):
    seed(hours_left)
    assert len(_run()) == 1


def test_only_once_though_the_task_runs_every_12_hours(seed):
    seed(20)
    assert len(_run()) == 1
    assert len(_run()) == 0


def test_the_five_extra_days_get_their_own_reminder(seed):
    """El aviso de la fecha vieja no le quita el de la fecha nueva."""
    user_id = seed(20)

    async def mark_old_end():
        client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        old_end = (datetime.now(timezone.utc) - timedelta(days=5)).date().isoformat()
        await client.set(tasks.TRIAL_REMINDER_KEY.format(user_id=user_id, days=1, ends=old_end), "1", ex=60)
        await client.aclose()
    asyncio.run(mark_old_end())

    assert len(_run()) == 1


@pytest.mark.parametrize("kw", [{"status": "active"}, {"exempt": True}], ids=["paga", "exenta"])
def test_never_to_who_pays_or_is_exempt(seed, kw):
    seed(20, **kw)
    assert _run() == []


def test_not_after_it_ended_nor_too_early(seed):
    seed(-5)
    seed(80)
    assert _run() == []


def _run_central(result):
    """Cuenta dada de alta por WhatsApp (sin correo): regresa a quién le mandó el central."""
    central = AsyncMock(return_value=result)
    whatsapp = AsyncMock(return_value=("wamid.1", None))
    with patch("app.core.email.send_trial_expiring_email", AsyncMock()), \
            patch("app.services.meta_service.send_whatsapp", whatsapp), \
            patch("app.services.platform_whatsapp.platform_enabled", return_value=True), \
            patch("app.services.platform_whatsapp.send_platform_text", central):
        tasks.send_trial_expiry_reminders()
    assert whatsapp.await_count == 0, "nunca por el bot de su propio negocio"
    return [c.args[0] for c in central.await_args_list]


def _no_inbox(seed):
    from app.core.email import NO_INBOX_DOMAIN
    return seed(20, email=f"{uuid.uuid4().hex[:10]}@{NO_INBOX_DOMAIN}", phone="+529531112233")


def test_without_email_it_goes_by_the_central_even_with_a_public_number(seed):
    _no_inbox(seed)  # el seed le pone whatsapp_number (número público del negocio)
    assert _run_central(("wamid.c", None)) == ["+529531112233"]
    assert _run_central(("wamid.c", None)) == []


def test_without_email_a_failed_central_send_is_tried_again(seed):
    """Es su único aviso: si Meta falla, la siguiente vuelta lo intenta otra vez."""
    _no_inbox(seed)
    assert _run_central((None, "(#131000) algo falló")) == ["+529531112233"]
    assert _run_central(("wamid.c", None)) == ["+529531112233"]
    assert _run_central(("wamid.c", None)) == []
