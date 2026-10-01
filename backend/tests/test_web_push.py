"""Notificaciones web — llaves VAPID, envío y limpieza de suscripciones
(web_push.py), endpoints del portal (activar/desactivar, confirmar cita,
"leída", manifest) y el ruteo que las usa en lugar de WhatsApp: campañas
(campaign_ops.py) y recordatorios de cita (appointment_ops.py).

El servicio de push real (FCM/Mozilla/Apple) nunca se toca: se parchea
_send_one / push_to_contact."""
import base64
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select
from starlette.requests import Request

from app.api.v1.portal import (
    confirm_appointment,
    notification_opened,
    portal_manifest,
    push_subscribe,
    push_unsubscribe,
)
from app.config import settings
from app.database import AsyncSessionLocal, engine
from app.models.appointment import Appointment
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.coupon import Coupon
from app.models.message import Message
from app.models.push_subscription import PushSubscription
from app.models.user import User
from app.services import web_push
from app.services.portal_service import make_portal_token

PUBLIC, PRIVATE = web_push.generate_vapid_keys()


@pytest.fixture(autouse=True)
def _keys(monkeypatch):
    monkeypatch.setattr(settings, "SECRET_KEY", "test-secret-for-portal-links")
    monkeypatch.setattr(settings, "FRONTEND_URL", "https://www.iaradio.online")
    monkeypatch.setattr(settings, "VAPID_PUBLIC_KEY", PUBLIC)
    monkeypatch.setattr(settings, "VAPID_PRIVATE_KEY", PRIVATE)


def _request(ua: str = "Mozilla/5.0 (Linux; Android 14)") -> Request:
    scope = {
        "type": "http", "method": "POST", "path": "/api/v1/public/portal/x",
        "headers": [(b"user-agent", ua.encode())],
        "client": (f"test-{uuid.uuid4()}", 123), "query_string": b"",
    }
    return Request(scope)


def _sub_body(n: int = 0) -> dict:
    return {"endpoint": f"https://fcm.googleapis.com/fcm/send/test-{uuid.uuid4()}-{n}",
            "keys": {"p256dh": "BPk" + "x" * 80, "auth": "authsecret123"}}


class TestVapidKeys:
    def test_public_key_is_an_uncompressed_p256_point(self):
        raw = base64.urlsafe_b64decode(PUBLIC + "=" * (-len(PUBLIC) % 4))
        assert len(raw) == 65 and raw[0] == 0x04

    def test_private_key_is_accepted_by_pywebpush(self):
        from py_vapid import Vapid02
        assert Vapid02.from_string(PRIVATE) is not None

    def test_disabled_without_keys(self, monkeypatch):
        monkeypatch.setattr(settings, "VAPID_PRIVATE_KEY", "")
        assert web_push.push_enabled() is False


async def _seed(n_contacts: int = 2):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Barbería Don Pepe",
                    widget_color="#e8590c")
        db.add(user)
        await db.flush()
        contacts = [
            Contact(advertiser_id=user.id, name=f"Cliente {i}", phone=f"+52155{uuid.uuid4().int % 10**8:08d}")
            for i in range(n_contacts)
        ]
        db.add_all(contacts)
        await db.commit()
        return user.id, [c.id for c in contacts]


async def _cleanup(user_id):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        for model in (PushSubscription, Coupon, Message, Campaign, Appointment, Contact):
            await db.execute(delete(model).where(model.advertiser_id == user_id))
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()
    await engine.dispose()


async def _add_subs(user_id, contact_id, n: int):
    async with AsyncSessionLocal() as db:
        subs = [
            PushSubscription(advertiser_id=user_id, contact_id=contact_id, endpoint=_sub_body(i)["endpoint"],
                             p256dh="k", auth="a")
            for i in range(n)
        ]
        db.add_all(subs)
        await db.commit()
        return [s.id for s in subs]


class TestPushToContact:
    @pytest.mark.asyncio
    async def test_counts_accepted_drops_dead_and_tracks_failures(self):
        user_id, (cid, _) = await _seed()
        try:
            await _add_subs(user_id, cid, 3)
            with patch("app.services.web_push._send_one", side_effect=[201, 410, 503]):
                async with AsyncSessionLocal() as db:
                    accepted = await web_push.push_to_contact(db, cid, title="t", body="b", url="https://x")
                    await db.commit()
            assert accepted == 1
            async with AsyncSessionLocal() as db:
                left = (await db.execute(select(PushSubscription).where(PushSubscription.contact_id == cid))).scalars().all()
            # 410 = navegador dado de baja → borrada; 503 = fallo temporal → contador.
            assert len(left) == 2
            assert sorted(s.failure_count for s in left) == [0, 1]
            assert any(s.last_success_at for s in left)
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_no_subscriptions_means_zero(self):
        user_id, (cid, _) = await _seed()
        try:
            async with AsyncSessionLocal() as db:
                assert await web_push.push_to_contact(db, cid, title="t", body="b", url="https://x") == 0
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_contacts_with_push_ignores_worn_out_subscriptions(self):
        user_id, (a, b) = await _seed()
        try:
            await _add_subs(user_id, a, 1)
            (sub_b,) = await _add_subs(user_id, b, 1)
            async with AsyncSessionLocal() as db:
                (await db.get(PushSubscription, sub_b)).failure_count = web_push.MAX_FAILURES
                await db.commit()
            async with AsyncSessionLocal() as db:
                assert await web_push.contacts_with_push(db, [a, b]) == {a}
        finally:
            await _cleanup(user_id)


class TestSubscribeEndpoints:
    @pytest.mark.asyncio
    async def test_subscribe_then_unsubscribe(self):
        user_id, (cid, _) = await _seed()
        body = _sub_body()
        try:
            async with AsyncSessionLocal() as db:
                await push_subscribe(request=_request(), token=make_portal_token(cid), body=body, db=db)
            async with AsyncSessionLocal() as db:
                sub = (await db.execute(select(PushSubscription).where(PushSubscription.endpoint == body["endpoint"]))).scalar_one()
                assert sub.contact_id == cid and "Android" in sub.user_agent
            async with AsyncSessionLocal() as db:
                await push_unsubscribe(request=_request(), token=make_portal_token(cid), body={"endpoint": body["endpoint"]}, db=db)
            async with AsyncSessionLocal() as db:
                assert (await db.execute(select(PushSubscription).where(PushSubscription.endpoint == body["endpoint"]))).first() is None
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_same_browser_moves_to_the_latest_contact(self):
        user_id, (a, b) = await _seed()
        body = _sub_body()
        try:
            for cid in (a, b):
                async with AsyncSessionLocal() as db:
                    await push_subscribe(request=_request(), token=make_portal_token(cid), body=body, db=db)
            async with AsyncSessionLocal() as db:
                subs = (await db.execute(select(PushSubscription).where(PushSubscription.endpoint == body["endpoint"]))).scalars().all()
            assert [s.contact_id for s in subs] == [b]
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_cannot_unsubscribe_someone_elses_browser(self):
        user_id, (a, b) = await _seed()
        body = _sub_body()
        try:
            async with AsyncSessionLocal() as db:
                await push_subscribe(request=_request(), token=make_portal_token(a), body=body, db=db)
            async with AsyncSessionLocal() as db:
                await push_unsubscribe(request=_request(), token=make_portal_token(b), body={"endpoint": body["endpoint"]}, db=db)
            async with AsyncSessionLocal() as db:
                assert (await db.execute(select(PushSubscription).where(PushSubscription.endpoint == body["endpoint"]))).first()
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad", [
        {"endpoint": "http://fcm.googleapis.com/x", "keys": {"p256dh": "k", "auth": "a"}},
        {"endpoint": "https://fcm.googleapis.com/x", "keys": {}},
        {"endpoint": "", "keys": {"p256dh": "k", "auth": "a"}},
    ])
    async def test_rejects_invalid_subscriptions(self, bad):
        user_id, (cid, _) = await _seed()
        try:
            async with AsyncSessionLocal() as db:
                with pytest.raises(HTTPException) as exc:
                    await push_subscribe(request=_request(), token=make_portal_token(cid), body=bad, db=db)
            assert exc.value.status_code == 400
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_404_when_push_is_not_configured(self, monkeypatch):
        monkeypatch.setattr(settings, "VAPID_PRIVATE_KEY", "")
        user_id, (cid, _) = await _seed()
        try:
            async with AsyncSessionLocal() as db:
                with pytest.raises(HTTPException) as exc:
                    await push_subscribe(request=_request(), token=make_portal_token(cid), body=_sub_body(), db=db)
            assert exc.value.status_code == 404
        finally:
            await _cleanup(user_id)


class TestPortalExtras:
    @pytest.mark.asyncio
    async def test_confirm_own_pending_appointment(self):
        user_id, (a, b) = await _seed()
        try:
            async with AsyncSessionLocal() as db:
                appt = Appointment(advertiser_id=user_id, contact_id=a, customer_name="Cliente 0", service="Corte",
                                   scheduled_at=datetime.now(timezone.utc) + timedelta(days=1), status="pending",
                                   awaiting_confirmation=True)
                db.add(appt)
                await db.commit()
                appt_id = appt.id
            async with AsyncSessionLocal() as db:
                with pytest.raises(HTTPException) as exc:
                    await confirm_appointment(request=_request(), token=make_portal_token(b), appointment_id=appt_id, db=db)
            assert exc.value.status_code == 404
            async with AsyncSessionLocal() as db:
                out = await confirm_appointment(request=_request(), token=make_portal_token(a), appointment_id=appt_id, db=db)
            assert out["appointment"]["status"] == "confirmed"
            async with AsyncSessionLocal() as db:
                assert (await db.get(Appointment, appt_id)).awaiting_confirmation is False
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_opened_marks_only_own_push_message_as_read(self):
        user_id, (a, b) = await _seed()
        try:
            async with AsyncSessionLocal() as db:
                push_msg = Message(advertiser_id=user_id, contact_id=a, direction="outbound",
                                   content="[PUSH] 2x1", status="sent")
                wa_msg = Message(advertiser_id=user_id, contact_id=a, direction="outbound",
                                 content="hola", status="sent")
                db.add_all([push_msg, wa_msg])
                await db.commit()
                push_id, wa_id = push_msg.id, wa_msg.id
            async with AsyncSessionLocal() as db:
                assert (await notification_opened(request=_request(), token=make_portal_token(b),
                                                  body={"message_id": str(push_id)}, db=db)) == {"ok": False}
                assert (await notification_opened(request=_request(), token=make_portal_token(a),
                                                  body={"message_id": str(wa_id)}, db=db)) == {"ok": False}
                assert (await notification_opened(request=_request(), token=make_portal_token(a),
                                                  body={"message_id": "basura"}, db=db)) == {"ok": False}
                assert (await notification_opened(request=_request(), token=make_portal_token(a),
                                                  body={"message_id": str(push_id)}, db=db)) == {"ok": True}
            async with AsyncSessionLocal() as db:
                assert (await db.get(Message, push_id)).status == "read"
                assert (await db.get(Message, wa_id)).status == "sent"
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_manifest_installs_the_business_app_on_this_link(self):
        import json as _json
        user_id, (cid, _) = await _seed()
        token = make_portal_token(cid)
        try:
            async with AsyncSessionLocal() as db:
                resp = await portal_manifest(request=_request(), token=token, db=db)
            data = _json.loads(resp.body)
            assert data["name"] == "Barbería Don Pepe"
            assert data["start_url"] == f"/c/{token}"
            assert data["display"] == "standalone" and data["theme_color"] == "#e8590c"
            assert resp.media_type == "application/manifest+json"
        finally:
            await _cleanup(user_id)


class TestCampaignRouting:
    async def _campaign(self, user_id):
        async with AsyncSessionLocal() as db:
            camp = Campaign(advertiser_id=user_id, name="2x1 en cortes", type="promo",
                            message_text="Hola {{primer_nombre}}, 2x1 este viernes")
            db.add(camp)
            user = await db.get(User, user_id)
            user.messages_remaining = 5
            await db.commit()
            return camp.id

    @pytest.mark.asyncio
    async def test_push_subscriber_gets_free_push_others_get_whatsapp(self):
        from app.workers.task_helpers.campaign_ops import send_regular_messages
        user_id, (with_push, without) = await _seed()
        try:
            camp_id = await self._campaign(user_id)
            calls = []

            async def fake_push(db, contact_id, **kw):
                calls.append((contact_id, kw))
                return 1

            whatsapp = MagicMock()
            with patch("app.workers.task_helpers.campaign_ops.contacts_with_push", AsyncMock(return_value={with_push})), \
                 patch("app.services.web_push.push_to_contact", side_effect=fake_push), \
                 patch("app.workers.task_helpers.campaign_ops._offer_or_queue", AsyncMock(return_value=("open", None))), \
                 patch("app.services.radio.tts.text_to_speech", AsyncMock(side_effect=RuntimeError("no tts in tests"))), \
                 patch("app.workers.tasks.send_whatsapp_message.apply_async", whatsapp), \
                 patch("app.core.email.send_campaign_sent_email", AsyncMock()):
                async with AsyncSessionLocal() as db:
                    camp = await db.get(Campaign, camp_id)
                    user = await db.get(User, user_id)
                    contacts = [await db.get(Contact, with_push), await db.get(Contact, without)]
                    await send_regular_messages(db, camp, contacts, user, {"has_coupon": True}, [], ban_delay=0)

            assert [c[0] for c in calls] == [with_push]
            push_kw = calls[0][1]
            assert push_kw["title"] == "Barbería Don Pepe"
            assert "Hola Cliente, 2x1 este viernes" in push_kw["body"]
            assert f"/promo/{camp_id}?n=" in push_kw["url"]
            # Solo el que no tiene push salió por WhatsApp.
            assert whatsapp.call_count == 1
            assert whatsapp.call_args.kwargs["args"][1] != ""
            async with AsyncSessionLocal() as db:
                msgs = (await db.execute(select(Message).where(Message.campaign_id == camp_id))).scalars().all()
                by_contact = {m.contact_id: m for m in msgs}
                assert by_contact[with_push].content.startswith("[PUSH]")
                assert by_contact[with_push].status == "sent"
                coupons = (await db.execute(select(Coupon).where(Coupon.campaign_id == camp_id))).scalars().all()
                assert {c.contact_id for c in coupons} == {with_push, without}
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_failed_push_falls_back_to_whatsapp_without_leftovers(self):
        from app.workers.task_helpers.campaign_ops import send_regular_messages
        user_id, (cid,) = await _seed(1)
        try:
            camp_id = await self._campaign(user_id)
            whatsapp = MagicMock()
            with patch("app.workers.task_helpers.campaign_ops.contacts_with_push", AsyncMock(return_value={cid})), \
                 patch("app.services.web_push.push_to_contact", AsyncMock(return_value=0)), \
                 patch("app.workers.task_helpers.campaign_ops._offer_or_queue", AsyncMock(return_value=("open", None))), \
                 patch("app.services.radio.tts.text_to_speech", AsyncMock(side_effect=RuntimeError("no tts in tests"))), \
                 patch("app.workers.tasks.send_whatsapp_message.apply_async", whatsapp), \
                 patch("app.core.email.send_campaign_sent_email", AsyncMock()):
                async with AsyncSessionLocal() as db:
                    camp = await db.get(Campaign, camp_id)
                    user = await db.get(User, user_id)
                    await send_regular_messages(db, camp, [await db.get(Contact, cid)], user, {}, [], ban_delay=0)
            assert whatsapp.call_count == 1
            async with AsyncSessionLocal() as db:
                contents = (await db.execute(select(Message.content).where(Message.campaign_id == camp_id))).scalars().all()
            assert not any(c.startswith("[PUSH]") for c in contents)
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_push_keeps_going_when_whatsapp_quota_is_used_up(self):
        from app.workers.task_helpers.campaign_ops import send_regular_messages
        user_id, (with_push, without) = await _seed()
        try:
            camp_id = await self._campaign(user_id)
            async with AsyncSessionLocal() as db:
                (await db.get(User, user_id)).messages_remaining = 0
                await db.commit()
            push = AsyncMock(return_value=1)
            whatsapp = MagicMock()
            with patch("app.workers.task_helpers.campaign_ops.contacts_with_push", AsyncMock(return_value={with_push})), \
                 patch("app.services.web_push.push_to_contact", push), \
                 patch("app.workers.tasks.send_whatsapp_message.apply_async", whatsapp), \
                 patch("app.core.email.send_campaign_sent_email", AsyncMock()):
                async with AsyncSessionLocal() as db:
                    camp = await db.get(Campaign, camp_id)
                    user = await db.get(User, user_id)
                    # El cliente con push va SEGUNDO: antes, sin saldo, el ciclo se cortaba en el primero.
                    contacts = [await db.get(Contact, without), await db.get(Contact, with_push)]
                    await send_regular_messages(db, camp, contacts, user, {}, [], ban_delay=0)
            assert push.await_count == 1
            assert whatsapp.call_count == 0
        finally:
            await _cleanup(user_id)


class TestReminderRouting:
    async def _appt_tomorrow(self, user_id, cid):
        async with AsyncSessionLocal() as db:
            when = datetime.now(timezone.utc) + timedelta(hours=24)
            appt = Appointment(advertiser_id=user_id, contact_id=cid, customer_name="Ana López",
                               customer_phone="+5215511112222", service="Corte", scheduled_at=when, status="confirmed")
            db.add(appt)
            await db.commit()
            return appt.id, when

    @pytest.mark.asyncio
    async def test_24h_reminder_goes_by_push_when_accepted(self):
        from app.workers.task_helpers.appointment_ops import send_24h_reminders
        user_id, (cid,) = await _seed(1)
        try:
            appt_id, _when = await self._appt_tomorrow(user_id, cid)
            push = AsyncMock(return_value=1)
            with patch("app.services.web_push.push_to_contact", push), \
                 patch("app.services.meta_service.send_whatsapp", AsyncMock()) as wa, \
                 patch("app.services.meta_service.send_whatsapp_buttons", AsyncMock()) as wa_btn:
                async with AsyncSessionLocal() as db:
                    await send_24h_reminders(db, datetime.now(timezone.utc))
                    await db.commit()
            # El job recorre TODAS las citas de la BD de test; solo importa la nuestra.
            mine = [c for c in push.await_args_list if c.args[1] == cid]
            assert len(mine) == 1
            assert mine[0].kwargs["title"] == "Mañana: Corte"
            assert mine[0].kwargs["tag"] == f"appt-{appt_id}"
            assert not any(c.args[0] == "+5215511112222" for c in wa.await_args_list + wa_btn.await_args_list)
            async with AsyncSessionLocal() as db:
                appt = await db.get(Appointment, appt_id)
                assert appt.reminder_24h_sent is True
                assert appt.awaiting_confirmation is False
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_24h_reminder_falls_back_to_whatsapp_in_local_time_and_spanish(self):
        from app.services.availability_service import TZ
        from app.workers.task_helpers.appointment_ops import send_24h_reminders
        user_id, (cid,) = await _seed(1)
        try:
            appt_id, when = await self._appt_tomorrow(user_id, cid)
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                user.meta_appointment_template_name = None
                await db.commit()
            with patch("app.services.web_push.push_to_contact", AsyncMock(return_value=0)), \
                 patch("app.services.whatsapp_window.is_window_open", return_value=True), \
                 patch("app.services.meta_service.send_whatsapp", AsyncMock()) as wa:
                async with AsyncSessionLocal() as db:
                    await send_24h_reminders(db, datetime.now(timezone.utc))
                    await db.commit()
            mine = [c for c in wa.await_args_list if c.args[0] == "+5215511112222"]
            assert len(mine) == 1
            text = mine[0].args[1]
            local = when.astimezone(TZ)
            assert local.strftime("%I:%M").lstrip("0") in text
            assert not any(day in text for day in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"))
            async with AsyncSessionLocal() as db:
                assert (await db.get(Appointment, appt_id)).awaiting_confirmation is True
        finally:
            await _cleanup(user_id)
