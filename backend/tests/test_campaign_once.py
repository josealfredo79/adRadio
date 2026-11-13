"""Una campaña sale una sola vez aunque Redis reentregue la tarea: el 29-oct
16 copias de 2 promos corrieron juntas a las 8:00. Base y Redis reales; el push
del navegador y WhatsApp son falsos."""
import asyncio
import uuid
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


# ── Si la corrida truena a media lista, lo que ya salió queda guardado ──────
# Antes todo se guardaba al final: con un corte de la base a media lista la
# tarea se reintentaba y la plantilla (que Meta cobra) salía otra vez.

async def _crash_setup(n=2):
    from app.models.user import User

    user_id, contacts = await _seed(n)
    async with AsyncSessionLocal() as db:
        user = await db.get(User, user_id)
        user.messages_remaining = 10
        user.meta_utility_template_name = "reabrir"
        camp = Campaign(advertiser_id=user_id, name="Promo micas", type="promo", message_text="2x1 en micas",
                        status="running", image_url="https://cdn.test/micas.jpg", ab_test={"photo_fixed": True})
        db.add(camp)
        await db.commit()
        return user_id, contacts, camp.id


async def _crash_cleanup(user_id):
    from sqlalchemy import delete

    from app.models.conversation import Conversation
    from app.models.recipient_send import RecipientSend

    async with AsyncSessionLocal() as db:
        for model in (RecipientSend, Message, Conversation):
            await db.execute(delete(model).where(model.advertiser_id == user_id))
        await db.commit()
    await _cleanup(user_id)


async def _run_banner(user_id, contacts, camp_id, offer):
    from app.models.contact import Contact
    from app.models.user import User
    from app.workers.task_helpers import campaign_ops

    async with AsyncSessionLocal() as db:
        camp = await db.get(Campaign, camp_id)
        user = await db.get(User, user_id)
        rows = [await db.get(Contact, c) for c in contacts]
        with patch.object(campaign_ops, "_offer_or_queue", offer):
            await campaign_ops.send_banner_messages(db, camp, rows, user, camp.ab_test, ban_delay=0)


@pytest.mark.asyncio
async def test_template_already_sent_is_saved_when_the_run_crashes():
    from app.models.user import User
    from app.workers.task_helpers import campaign_ops

    real = campaign_ops._offer_or_queue
    user_id, (c1, c2), camp_id = await _crash_setup()
    try:
        async def offer(db, adv, contact, **kw):
            if contact.id == c2:
                raise TimeoutError  # el corte de la base del 12-nov
            return await real(db, adv, contact, **kw)

        with patch("app.services.whatsapp_window.is_window_open", return_value=False), \
             patch("app.services.meta_service.send_whatsapp_template", AsyncMock(side_effect=lambda **kw: (f"wamid.{uuid.uuid4().hex}", None))), \
             pytest.raises(TimeoutError):
            await _run_banner(user_id, [c1, c2], camp_id, offer)

        async with AsyncSessionLocal() as db:
            rows = (await db.execute(select(Message.content, Message.status).where(
                Message.campaign_id == camp_id, Message.contact_id == c1))).all()
            assert {r.content.split("]")[0] + "]" for r in rows} == {"[TEMPLATE:reabrir]", "[PENDING:banner]"}
            # El reintento ve a c1 como hecho (queued/sent) y no le vuelve a mandar ni a cobrar.
            assert {r.status for r in rows} <= {"queued", "sent"}
            assert (await db.get(User, user_id)).messages_remaining == 9
    finally:
        await _crash_cleanup(user_id)


@pytest.mark.asyncio
async def test_send_task_finds_its_message_saved():
    user_id, (c1,), camp_id = await _crash_setup(1)
    try:
        seen = []

        def dispatch(*, args, **kw):
            async def look():
                from app.database import CeleryAsyncSessionLocal
                async with CeleryAsyncSessionLocal() as other:  # otra conexión, como el worker
                    return await other.get(Message, uuid.UUID(args[0]))
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(1) as pool:
                seen.append(pool.submit(asyncio.run, look()).result())

        with patch("app.workers.tasks.send_whatsapp_image_message.apply_async", side_effect=dispatch):
            await _run_banner(user_id, [c1], camp_id, AsyncMock(return_value=("open", None)))
        assert len(seen) == 1 and seen[0] is not None and seen[0].status == "queued"
    finally:
        await _crash_cleanup(user_id)


@pytest.mark.asyncio
async def test_charge_does_not_overwrite_what_send_tasks_discounted():
    from sqlalchemy import text, update

    from app.models.user import User
    from app.workers.task_helpers import campaign_ops

    real = campaign_ops._offer_or_queue
    user_id, (c1, c2), camp_id = await _crash_setup()
    try:
        async def offer(db, adv, contact, **kw):
            if contact.id == c2:  # mientras tanto una tarea de envío descuenta 1
                async with AsyncSessionLocal() as other:
                    # Si la corrida tuviera bloqueado al dueño sin guardar, esto se quedaría esperando.
                    await other.execute(text("SET LOCAL lock_timeout = '5s'"))
                    await other.execute(update(User).where(User.id == user_id)
                                        .values(messages_remaining=User.messages_remaining - 1))
                    await other.commit()
            return await real(db, adv, contact, **kw)

        with patch("app.services.whatsapp_window.is_window_open", return_value=False), \
             patch("app.services.meta_service.send_whatsapp_template", AsyncMock(side_effect=lambda **kw: (f"wamid.{uuid.uuid4().hex}", None))):
            await _run_banner(user_id, [c1, c2], camp_id, offer)

        async with AsyncSessionLocal() as db:
            assert (await db.get(User, user_id)).messages_remaining == 7  # 10 − 2 plantillas − 1 envío
    finally:
        await _crash_cleanup(user_id)


@pytest.mark.asyncio
async def test_with_balance_two_both_contacts_get_the_template():
    """Revisor 12-nov: el saldo en memoria bajaba 2 por plantilla y la promo
    paraba a la mitad sin avisar."""
    from app.models.user import User

    user_id, (c1, c2), camp_id = await _crash_setup()
    try:
        async with AsyncSessionLocal() as db:
            (await db.get(User, user_id)).messages_remaining = 2
            await db.commit()
        send = AsyncMock(side_effect=lambda **kw: (f"wamid.{uuid.uuid4().hex}", None))
        from app.workers.task_helpers import campaign_ops
        with patch("app.services.whatsapp_window.is_window_open", return_value=False), \
             patch("app.services.meta_service.send_whatsapp_template", send):
            await _run_banner(user_id, [c1, c2], camp_id, campaign_ops._offer_or_queue)
        assert send.await_count == 2
        async with AsyncSessionLocal() as db:
            assert (await db.get(User, user_id)).messages_remaining == 0
    finally:
        await _crash_cleanup(user_id)
