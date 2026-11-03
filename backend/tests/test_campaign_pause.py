"""La pausa frena de verdad: no la pisa el fin del encolado, un aviso de Meta
alcanza la cola de una campaña "completada" y reanudar no repite a nadie. Base
y Redis reales; el envío es falso."""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api.v1.campaigns import pause_campaign
from app.database import AsyncSessionLocal, _get_celery_engine, engine
from app.models.campaign import Campaign
from app.models.message import Message
from app.models.user import User
from app.services.meta_quality_service import pause_active_campaigns
from app.workers import tasks
from app.workers.task_helpers.campaign_ops import _paused_now
from tests.test_campanas_fase_a import _camp, _plan
from tests.test_web_push import (  # noqa: F401 — _keys es fixture autouse
    _cleanup,
    _keys,
    _seed,
)


def _db(work):
    """Cada asyncio.run trae su propio loop: las conexiones no pueden pasar al siguiente."""
    async def run():
        await engine.dispose()
        try:
            return await work()
        finally:
            await engine.dispose()
    return asyncio.run(run())


@pytest.fixture
def business():
    async def setup():
        seeded = await _seed(2)
        await _plan(seeded[0], "growth")
        return seeded
    user_id, contact_ids = _db(setup)
    yield user_id, contact_ids
    _db(lambda: _cleanup(user_id))


def _make(user_id, status):
    return _db(lambda: _camp(user_id, "regular", status=status, web_only=False))


def _status(camp_id):
    async def read():
        async with AsyncSessionLocal() as db:
            return (await db.get(Campaign, camp_id)).status
    return _db(read)


def _add_message(user_id, contact_id, camp_id, status="queued", content="hola", hours_ago=0, error_code=None):
    async def run():
        async with AsyncSessionLocal() as db:
            msg = Message(advertiser_id=user_id, contact_id=contact_id, campaign_id=camp_id,
                          direction="outbound", content=content, status=status, error_code=error_code)
            db.add(msg)
            await db.flush()
            if hours_ago:
                msg.created_at = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
            await db.commit()
    _db(run)


def _run_send(camp_id, on_send=None):
    """Corre schedule_campaign con envío falso; regresa a quién iba dirigido."""
    sent_to = []

    async def fake_send(db, campaign, contacts, *args, **kwargs):
        sent_to.extend(c.id for c in contacts)
        if on_send:
            await on_send()

    _get_celery_engine().sync_engine.dispose(close=False)
    with patch("app.services.messaging_throttle.is_human_hour", return_value=True), \
            patch("app.workers.tasks.send_regular_messages", fake_send), \
            patch("app.core.email.send_campaign_sent_email", AsyncMock()):
        tasks.schedule_campaign(str(camp_id))
    _get_celery_engine().sync_engine.dispose(close=False)
    return sent_to


def _meta_pause(user_id):
    async def run():
        async with AsyncSessionLocal() as db:
            await pause_active_campaigns(db, user_id)
            await db.commit()
    _db(run)


def test_a_normal_send_ends_completed(business):
    user_id, _ = business
    camp_id = _make(user_id, "scheduled")
    assert len(_run_send(camp_id)) == 2
    assert _status(camp_id) == "completed"


def test_a_pause_during_the_send_is_not_overwritten(business):
    user_id, _ = business
    camp_id = _make(user_id, "scheduled")

    async def owner_pauses():
        async with AsyncSessionLocal() as other:
            (await other.get(Campaign, camp_id)).status = "paused"
            await other.commit()

    _run_send(camp_id, owner_pauses)
    assert _status(camp_id) == "paused"


def test_meta_warning_reaches_the_queue_of_a_completed_campaign(business):
    user_id, (contact_id, _) = business
    camp_id = _make(user_id, "completed")
    _add_message(user_id, contact_id, camp_id)
    _meta_pause(user_id)
    assert _status(camp_id) == "paused"


@pytest.mark.parametrize("kw", [
    {"status": "sent"},
    {"content": "[PENDING:text] hola"},
    {"hours_ago": 72},
], ids=["ya-salio", "espera-respuesta", "cola-perdida"])
def test_meta_warning_leaves_finished_campaigns_alone(business, kw):
    user_id, (contact_id, _) = business
    camp_id = _make(user_id, "completed")
    _add_message(user_id, contact_id, camp_id, **kw)
    _meta_pause(user_id)
    assert _status(camp_id) == "completed"


def test_resuming_skips_who_already_got_it_or_is_queued(business):
    user_id, (first, second) = business
    camp_id = _make(user_id, "running")
    _add_message(user_id, first, camp_id, status="delivered")
    _add_message(user_id, second, camp_id, status="queued")
    assert _run_send(camp_id) == []


def test_resuming_retries_who_was_stopped(business):
    user_id, (first, second) = business
    camp_id = _make(user_id, "running")
    _add_message(user_id, first, camp_id, status="delivered")
    _add_message(user_id, second, camp_id, status="failed")
    assert _run_send(camp_id) == [second]


def _flag(camp_id, **values):
    async def run():
        async with AsyncSessionLocal() as db:
            camp = await db.get(Campaign, camp_id)
            camp.ab_test = {**camp.ab_test, **values}
            await db.commit()
    _db(run)


def test_a_paused_queue_resumes_only_what_was_stopped(business):
    """Una campaña vieja no se vuelve tanda nueva para contactos agregados después."""
    user_id, (first, _new_customer) = business
    camp_id = _make(user_id, "running")
    _flag(camp_id, queue_paused=True)
    _add_message(user_id, first, camp_id, status="failed", error_code="campaign_paused")
    assert _run_send(camp_id) == [first]


def test_resuming_by_web_skips_who_got_it_and_covers_the_queue(business):
    """Cupón solo una vez; lo que seguía en cola se frena y le llega por web."""
    user_id, (first, second) = business
    camp_id = _make(user_id, "running")
    _flag(camp_id, web_only=True)
    _add_message(user_id, first, camp_id, status="sent")
    _add_message(user_id, second, camp_id, status="queued")
    assert _run_send(camp_id) == [second]


def test_a_queued_whatsapp_stops_if_resumed_by_web(business):
    user_id, (contact_id, _) = business
    camp_id = _make(user_id, "running")
    _flag(camp_id, web_only=True)
    _add_message(user_id, contact_id, camp_id)

    async def check():
        async with AsyncSessionLocal() as db:
            msg = (await db.execute(select(Message).where(Message.campaign_id == camp_id))).scalar_one()
            return await tasks._campaign_send_stop(db, msg, True)
    assert _db(check) == "campaign_web_only"


def test_the_send_loop_sees_a_pause_made_elsewhere(business):
    user_id, _ = business
    camp_id = _make(user_id, "running")

    async def check():
        async with AsyncSessionLocal() as db:
            camp = await db.get(Campaign, camp_id)
            before = await _paused_now(db, camp)
            async with AsyncSessionLocal() as other:
                (await other.get(Campaign, camp_id)).status = "paused"
                await other.commit()
            return before, await _paused_now(db, camp)
    assert _db(check) == (False, True)


def _pause_button(user_id, camp_id):
    async def run():
        async with AsyncSessionLocal() as db:
            await pause_campaign(camp_id, MagicMock(), db, await db.get(User, user_id), None, None)
    _db(run)


def test_pause_refuses_a_campaign_with_nothing_queued(business):
    user_id, (contact_id, _) = business
    camp_id = _make(user_id, "completed")
    _add_message(user_id, contact_id, camp_id, content="[PENDING:text] hola")
    with pytest.raises(HTTPException) as refused:
        _pause_button(user_id, camp_id)
    assert refused.value.status_code == 409
    assert _status(camp_id) == "completed"


def test_pause_stops_a_real_queue_and_marks_it(business):
    user_id, (contact_id, _) = business
    camp_id = _make(user_id, "completed")
    _add_message(user_id, contact_id, camp_id)
    with patch("app.api.v1.campaigns.store_idempotency_response", AsyncMock()):
        _pause_button(user_id, camp_id)

    async def read():
        async with AsyncSessionLocal() as db:
            camp = await db.get(Campaign, camp_id)
            return camp.status, camp.ab_test.get("queue_paused")
    assert _db(read) == ("paused", True)


def test_a_paused_queue_resumed_by_web_covers_who_was_still_queued(business):
    """Cola pausada + solo por web: lo que seguía esperando también le llega por web,
    porque su WhatsApp ya no sale (lo frena campaign_web_only)."""
    user_id, (stopped, waiting) = business
    camp_id = _make(user_id, "running")
    _flag(camp_id, queue_paused=True, web_only=True)
    _add_message(user_id, stopped, camp_id, status="failed", error_code="campaign_paused")
    _add_message(user_id, waiting, camp_id, status="queued")
    assert sorted(_run_send(camp_id)) == sorted([stopped, waiting])


def test_a_paused_queue_resumed_by_whatsapp_leaves_the_queue_alone(business):
    """Por WhatsApp la cola sigue saliendo sola: no se le manda otra vez."""
    user_id, (stopped, waiting) = business
    camp_id = _make(user_id, "running")
    _flag(camp_id, queue_paused=True)
    _add_message(user_id, stopped, camp_id, status="failed", error_code="campaign_paused")
    _add_message(user_id, waiting, camp_id, status="queued")
    assert _run_send(camp_id) == [stopped]


def test_bulk_send_drops_the_paused_queue_flag(business):
    """Elegir contactos a mano es una lista nueva, no "reintentar lo frenado"."""
    from app.api.v1.contacts import BulkSendCampaignRequest, bulk_send_campaign
    from tests.test_campanas_fase_a import _request

    user_id, (contact_id, _) = business
    camp_id = _make(user_id, "paused")
    _flag(camp_id, queue_paused=True)

    async def run():
        async with AsyncSessionLocal() as db:
            user = await db.get(User, user_id)
            with patch("app.workers.tasks.schedule_campaign.delay", MagicMock()), \
                    patch("app.services.send_block_explain.preflight_campaign_send", AsyncMock(return_value=None)):
                await bulk_send_campaign(_request(), BulkSendCampaignRequest(
                    contact_ids=[str(contact_id)], campaign_id=str(camp_id)), db=db, current_user=user)
        async with AsyncSessionLocal() as db:
            camp = await db.get(Campaign, camp_id)
            return camp.status, (camp.ab_test or {}).get("queue_paused")
    assert _db(run) == ("scheduled", None)
