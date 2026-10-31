"""Una campaña sale una sola vez aunque Redis reentregue la tarea: el 29-oct
16 copias de 2 promos corrieron juntas a las 8:00. Base y Redis reales; el push
del navegador y WhatsApp son falsos."""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest
import redis.asyncio as aioredis
from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal, _get_celery_engine, engine
from app.models.campaign import Campaign
from app.models.message import Message
from app.workers import tasks
from app.workers.celery_app import celery_app
from tests.test_campanas_fase_a import _camp, _plan
from tests.test_web_push import (  # noqa: F401 — _keys es fixture autouse
    _add_subs,
    _cleanup,
    _keys,
    _seed,
)


def _prepare(user_id, contact_id):
    async def setup():
        await engine.dispose()  # cada asyncio.run trae su propio loop
        await _plan(user_id, "growth")
        await _add_subs(user_id, contact_id, 1)
        return await _camp(user_id, "regular", status="scheduled")
    camp_id = asyncio.run(setup())
    _get_celery_engine().sync_engine.dispose(close=False)
    return str(camp_id)


def _sent(camp_id):
    async def read():
        await engine.dispose()
        async with AsyncSessionLocal() as db:
            camp = await db.get(Campaign, camp_id)
            msgs = (await db.execute(select(Message.content).where(Message.campaign_id == camp_id))).scalars().all()
            return camp.status, msgs
    return asyncio.run(read())


def _claim_exists(camp_id) -> bool:
    async def read():
        client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            return bool(await client.exists(tasks.CAMPAIGN_CLAIM_KEY.format(campaign_id=camp_id)))
        finally:
            await client.aclose()
    return asyncio.run(read())


def test_a_copy_that_arrives_while_sending_does_nothing():
    user_id, (contact_id,) = asyncio.run(_seed(1))
    try:
        camp_id = _prepare(user_id, contact_id)
        calls = []

        async def push_while_a_copy_arrives(*args, **kwargs):
            calls.append(1)
            await asyncio.to_thread(tasks.schedule_campaign, camp_id)  # la copia llega en pleno envío
            return 1

        with patch("app.services.messaging_throttle.is_human_hour", return_value=True), \
             patch("app.services.web_push.push_to_contact", push_while_a_copy_arrives), \
             patch("app.core.email.send_campaign_sent_email", AsyncMock()):
            tasks.schedule_campaign(camp_id)

        assert len(calls) == 1
        status, msgs = _sent(camp_id)
        assert status == "completed" and msgs == ["[PUSH] Promo regular"]
    finally:
        asyncio.run(_cleanup(user_id))


def test_a_copy_that_arrives_after_it_finished_does_nothing():
    user_id, (contact_id,) = asyncio.run(_seed(1))
    try:
        camp_id = _prepare(user_id, contact_id)
        push = AsyncMock(return_value=1)
        with patch("app.services.messaging_throttle.is_human_hour", return_value=True), \
             patch("app.services.web_push.push_to_contact", push), \
             patch("app.core.email.send_campaign_sent_email", AsyncMock()):
            tasks.schedule_campaign(camp_id)
            tasks.schedule_campaign(camp_id)
        push.assert_awaited_once()
        assert not _claim_exists(camp_id)
    finally:
        asyncio.run(_cleanup(user_id))


def test_a_failed_send_frees_the_campaign_for_its_retry():
    user_id, (contact_id,) = asyncio.run(_seed(1))
    try:
        camp_id = _prepare(user_id, contact_id)
        with patch("app.services.messaging_throttle.is_human_hour", return_value=True), \
             patch.object(tasks, "send_regular_messages", AsyncMock(side_effect=RuntimeError("boom"))), \
             patch("app.workers.task_helpers.campaign_ops.notify_campaign_failed", AsyncMock()), \
             patch.object(tasks.schedule_campaign, "retry", side_effect=RuntimeError("retry")), \
             pytest.raises(RuntimeError, match="retry"):
            tasks.schedule_campaign(camp_id)
        assert not _claim_exists(camp_id)
    finally:
        asyncio.run(_cleanup(user_id))


def test_tasks_that_wait_overnight_are_not_redelivered():
    # La promo de noche espera ~10 h y un envío espaciado puede esperar más.
    assert celery_app.conf.broker_transport_options["visibility_timeout"] >= 24 * 3600
