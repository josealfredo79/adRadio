"""Campañas por web sin las reglas anti-baneo de WhatsApp, y máximo una
notificación de promo al día por cliente — un test por caso de
docs/specs/2026-10-13-web-sin-reglas-whatsapp.md. BD real; el push real
(FCM) y WhatsApp nunca se tocan."""
import asyncio
from datetime import datetime, time, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from app.api.v1.portal import get_messages
from app.database import AsyncSessionLocal, engine
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.message import Message
from app.models.user import User
from app.services.availability_service import TZ
from app.services.campaign_reach import campaign_reach
from app.services.portal_service import make_portal_token
from app.services.send_block_explain import preflight_campaign_send
from app.workers.task_helpers.campaign_ops import (
    is_segment_on_cooldown,
    record_segment_send,
    segment_fingerprint,
    send_regular_messages,
)
from tests.test_campaign_reach import _campaign
from tests.test_web_push import (  # noqa: F401 — _keys es fixture autouse
    _add_subs,
    _keys,
    _request,
    _seed,
)
from tests.test_web_push import _cleanup as _cleanup_push


async def _cleanup(user_id):
    from sqlalchemy import delete

    from app.models.campaign_segment_send import CampaignSegmentSend

    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(CampaignSegmentSend).where(CampaignSegmentSend.advertiser_id == user_id))
        await db.commit()
    await _cleanup_push(user_id)


async def _web_only(camp_id):
    async with AsyncSessionLocal() as db:
        camp = await db.get(Campaign, camp_id)
        camp.ab_test = {**(camp.ab_test or {}), "web_only": True}
        await db.commit()


async def _earlier_push(user_id, contact_id, at):
    """Una promo que ya le sonó a este cliente a la hora `at`."""
    async with AsyncSessionLocal() as db:
        other = Campaign(advertiser_id=user_id, name="Promo anterior", type="promo", message_text="antes")
        db.add(other)
        await db.flush()
        db.add(Message(advertiser_id=user_id, contact_id=contact_id, campaign_id=other.id, direction="outbound",
                       content="[PUSH] Promo anterior", status="sent", created_at=at))
        await db.commit()


async def _send(user_id, camp_id, contact_ids):
    push = AsyncMock(return_value=1)
    whatsapp = MagicMock()
    with patch("app.services.web_push.push_to_contact", push), \
            patch("app.workers.task_helpers.campaign_ops._offer_or_queue", AsyncMock(return_value=("open", None))), \
            patch("app.services.radio.tts.text_to_speech", AsyncMock(side_effect=RuntimeError("no tts in tests"))), \
            patch("app.workers.tasks.send_whatsapp_message.apply_async", whatsapp), \
            patch("app.core.email.send_campaign_sent_email", AsyncMock()):
        async with AsyncSessionLocal() as db:
            camp = await db.get(Campaign, camp_id)
            user = await db.get(User, user_id)
            contacts = [await db.get(Contact, c) for c in contact_ids]
            await send_regular_messages(db, camp, contacts, user, camp.ab_test or {}, [], ban_delay=0)
            await db.commit()
    return push, whatsapp


async def _campaign_messages(camp_id):
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(Message).where(Message.campaign_id == camp_id))).scalars().all()


def _start_of_today_mx():
    return datetime.combine(datetime.now(TZ).date(), time.min, tzinfo=TZ)


@pytest.mark.asyncio
async def test_web_ignores_whatsapp_48h_cooldown():
    user_id, (cid,) = await _seed(1)
    try:
        await _add_subs(user_id, cid, 1)
        async with AsyncSessionLocal() as db:
            (await db.get(Contact, cid)).last_campaign_sent_at = datetime.now(timezone.utc) - timedelta(hours=1)
            await db.commit()
        camp_id = await _campaign(user_id)
        await _web_only(camp_id)
        push, _ = await _send(user_id, camp_id, [cid])
        assert push.await_count == 1
        assert [m.content for m in await _campaign_messages(camp_id)] == ["[PUSH] 2x1 en cortes"]
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_web_only_skips_segment_cooldown():
    user_id, (cid,) = await _seed(1)
    try:
        await _add_subs(user_id, cid, 1)
        camp_id = await _campaign(user_id)
        async with AsyncSessionLocal() as db:
            camp = await db.get(Campaign, camp_id)
            await record_segment_send(db, user_id, segment_fingerprint(camp.segment or {}))
            await db.commit()
            user = await db.get(User, user_id)
            # Por WhatsApp sigue bloqueada; solo por web, no.
            assert await preflight_campaign_send(db, camp, user) is not None
            assert await preflight_campaign_send(db, camp, user, web_only=True) is None
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_first_promo_of_the_day_rings():
    user_id, (cid,) = await _seed(1)
    try:
        await _add_subs(user_id, cid, 1)
        camp_id = await _campaign(user_id)
        await _web_only(camp_id)
        push, _ = await _send(user_id, camp_id, [cid])
        assert push.await_count == 1
        assert push.await_args.kwargs["tag"] == f"campaign-{camp_id}"
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_second_promo_same_day_arrives_silently():
    user_id, (cid,) = await _seed(1)
    try:
        await _add_subs(user_id, cid, 1)
        await _earlier_push(user_id, cid, datetime.now(timezone.utc) - timedelta(minutes=5))
        camp_id = await _campaign(user_id)
        await _web_only(camp_id)
        async with AsyncSessionLocal() as db:
            camp = await db.get(Campaign, camp_id)
            camp.ab_test = {**camp.ab_test, "has_coupon": True, "coupon_description": "2x1"}
            await db.commit()
        push, whatsapp = await _send(user_id, camp_id, [cid])
        assert push.await_count == 0 and whatsapp.call_count == 0
        msgs = await _campaign_messages(camp_id)
        assert [(m.content, m.status) for m in msgs] == [("[WEB] 2x1 en cortes", "sent")]
        # Aparece en su chat como burbuja, con su cupón.
        async with AsyncSessionLocal() as db:
            out = await get_messages(request=_request(), token=make_portal_token(cid), db=db)
        promo = next(m for m in out["messages"] if m.get("promo", {}).get("id") == str(camp_id))
        assert promo["promo"]["coupon"] is not None
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_promo_rings_again_next_day():
    user_id, (cid,) = await _seed(1)
    try:
        await _add_subs(user_id, cid, 1)
        # Le sonó ayer a las 23:59 (hora de México).
        await _earlier_push(user_id, cid, _start_of_today_mx() - timedelta(minutes=1))
        camp_id = await _campaign(user_id)
        await _web_only(camp_id)
        push, _ = await _send(user_id, camp_id, [cid])
        assert push.await_count == 1
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_owner_reply_still_rings_after_promo():
    from app.services.web_conversation import push_owner_reply

    user_id, (cid,) = await _seed(1)
    try:
        await _add_subs(user_id, cid, 1)
        await _earlier_push(user_id, cid, datetime.now(timezone.utc) - timedelta(minutes=5))
        push = AsyncMock(return_value=1)
        with patch("app.services.web_push.push_to_contact", push):
            async with AsyncSessionLocal() as db:
                assert await push_owner_reply(db, "Barbería Don Pepe", cid, "Sí te la aparto") == 1
        assert push.await_count == 1
    finally:
        await _cleanup(user_id)


def test_web_send_does_not_start_whatsapp_cooldowns():
    # schedule_campaign corre su propio asyncio.run(): este test es síncrono (ver test_segment_cooldown).
    from app.workers.tasks import schedule_campaign

    user_id, (cid,) = asyncio.run(_seed(1))
    try:
        async def _prepare():
            await engine.dispose()  # cada asyncio.run es otro ciclo: conexiones nuevas
            await _add_subs(user_id, cid, 1)
            camp_id = await _campaign(user_id)
            await _web_only(camp_id)
            async with AsyncSessionLocal() as db:
                (await db.get(Campaign, camp_id)).status = "scheduled"
                await db.commit()
            return camp_id

        camp_id = asyncio.run(_prepare())
        # El motor de Celery guarda conexiones de otros tests (otro ciclo de asyncio):
        # que la tarea abra las suyas.
        from app.database import _get_celery_engine

        _get_celery_engine().sync_engine.dispose(close=False)
        with patch("app.services.messaging_throttle.is_human_hour", return_value=True), \
                patch("app.services.web_push.push_to_contact", AsyncMock(return_value=1)), \
                patch("app.core.email.send_campaign_sent_email", AsyncMock()):
            schedule_campaign(str(camp_id))

        async def _check():
            await engine.dispose()
            async with AsyncSessionLocal() as db:
                camp = await db.get(Campaign, camp_id)
                contact = await db.get(Contact, cid)
                on_cooldown = await is_segment_on_cooldown(db, user_id, segment_fingerprint(camp.segment or {}))
                contents = (await db.execute(select(Message.content).where(Message.campaign_id == camp_id))).scalars().all()
                return camp.status, contact.last_campaign_sent_at, on_cooldown, contents

        status, last_sent, on_cooldown, contents = asyncio.run(_check())
        assert contents == ["[PUSH] 2x1 en cortes"] and status == "completed"
        assert last_sent is None  # sin la pausa de 48 h de WhatsApp
        assert on_cooldown is False  # sin los 7 días del grupo
    finally:
        asyncio.run(_cleanup(user_id))


@pytest.mark.asyncio
async def test_whatsapp_part_keeps_its_rules():
    user_id, (with_push, recent_wa) = await _seed(2)
    try:
        await _add_subs(user_id, with_push, 1)
        async with AsyncSessionLocal() as db:
            recent = datetime.now(timezone.utc) - timedelta(hours=1)
            (await db.get(Contact, recent_wa)).last_campaign_sent_at = recent
            (await db.get(Contact, with_push)).last_campaign_sent_at = recent
            await db.commit()
        camp_id = await _campaign(user_id)  # "Enviar a todos", no solo web
        push, whatsapp = await _send(user_id, camp_id, [with_push, recent_wa])
        assert push.await_count == 1  # la web no espera las 48 h
        assert whatsapp.call_count == 0  # WhatsApp sí: le escribieron hace 1 h
        async with AsyncSessionLocal() as db:
            camp = await db.get(Campaign, camp_id)
            await record_segment_send(db, user_id, segment_fingerprint(camp.segment or {}))
            await db.commit()
            assert await preflight_campaign_send(db, camp, await db.get(User, user_id)) is not None
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_reach_counts_silent_web():
    user_id, (rang, fresh, recent_wa) = await _seed(3)
    try:
        await _add_subs(user_id, rang, 1)
        await _add_subs(user_id, fresh, 1)
        await _earlier_push(user_id, rang, datetime.now(timezone.utc) - timedelta(minutes=5))
        async with AsyncSessionLocal() as db:
            for cid in (rang, recent_wa):
                (await db.get(Contact, cid)).last_campaign_sent_at = datetime.now(timezone.utc) - timedelta(hours=1)
            await db.commit()
        camp_id = await _campaign(user_id)
        async with AsyncSessionLocal() as db:
            reach = await campaign_reach(db, await db.get(Campaign, camp_id))
        # Los dos con avisos cuentan por web (aunque a uno le escribieron hace 1 h);
        # el de WhatsApp en pausa de 48 h no cuenta.
        assert (reach["web"], reach["web_silent"], reach["whatsapp"], reach["total"]) == (2, 1, 0, 2)
    finally:
        await _cleanup(user_id)
