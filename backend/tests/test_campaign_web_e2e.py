"""Campaña "Solo por web" de punta a punta (2026-10-12): la tarea de Celery
real, base y Redis reales, y el aviso CIFRADO de verdad por pywebpush. Lo
único falso es el servicio de push del navegador (FCM/Mozilla): se intercepta
el POST y se descifra con las llaves del "navegador", como lo haría el celular.

Recorrido: el dueño lanza la promo → al cliente con avisos le llega una
notificación legible con su link → abre su tarjeta y ve la promo con su
cupón → toca "¡La quiero!" y el bot sabe de qué promo habla → la notificación
cuenta como leída en las estadísticas. Al cliente sin avisos no le llega nada
y no se gasta WhatsApp.
"""
import asyncio
import base64
import json
import os
import uuid
from unittest.mock import MagicMock, patch

import http_ece
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from sqlalchemy import delete, select
from starlette.requests import Request

from app.config import settings
from app.database import AsyncSessionLocal, engine
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.coupon import Coupon
from app.models.message import Message
from app.models.push_subscription import PushSubscription
from app.models.user import User
from app.services.portal_service import make_portal_token
from tests.test_portal_web_shift import FakeRedis


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class Browser:
    """Las llaves que un navegador real genera al activar avisos."""

    def __init__(self):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.auth = os.urandom(16)
        self.p256dh = _b64(self.key.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))

    def read(self, body: bytes) -> dict:
        return json.loads(http_ece.decrypt(body, private_key=self.key, auth_secret=self.auth, version="aes128gcm"))


class PushService:
    """Hace de FCM: recibe el POST de pywebpush y contesta 201."""

    def __init__(self):
        self.received: list[dict] = []

    def post(self, url, data=None, headers=None, timeout=None, **kw):
        # Los encabezados HTTP no distinguen mayúsculas: se guardan en minúsculas.
        self.received.append({"url": url, "body": data, "headers": {k.lower(): v for k, v in (headers or {}).items()}})
        return MagicMock(status_code=201, text="")


def _verify_vapid(headers: dict, public_key, endpoint: str) -> dict:
    """La firma VAPID que el servicio de push revisa antes de entregar."""
    auth = headers["authorization"]
    token = auth.split("t=")[1].split(",")[0].strip()
    head, payload, sig = token.split(".")
    raw = _unb64(sig)
    der = encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
    public_key.verify(der, f"{head}.{payload}".encode(), ec.ECDSA(hashes.SHA256()))  # lanza si no cuadra
    claims = json.loads(_unb64(payload))
    assert endpoint.startswith(claims["aud"])
    return claims


@pytest.fixture
def vapid(monkeypatch):
    # Las mismas llaves que se generan para producción (python -m app.services.web_push --generate).
    from app.services.web_push import generate_vapid_keys

    public, private = generate_vapid_keys()
    monkeypatch.setattr(settings, "VAPID_PRIVATE_KEY", private)
    monkeypatch.setattr(settings, "VAPID_PUBLIC_KEY", public)
    monkeypatch.setattr(settings, "SECRET_KEY", "test-secret-campaign-web")
    monkeypatch.setattr(settings, "FRONTEND_URL", "https://www.iaradio.online")
    return public


async def _seed(browser: Browser):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="CityCell",
                    city="Tlaxiaco", subscription_status="active", messages_remaining=0)
        db.add(user)
        await db.flush()
        with_push = Contact(advertiser_id=user.id, name="Alfredo", phone=f"+52155{uuid.uuid4().int % 10**8:08d}")
        without = Contact(advertiser_id=user.id, name="Beto", phone=f"+52155{uuid.uuid4().int % 10**8:08d}")
        db.add_all([with_push, without])
        await db.flush()
        db.add(PushSubscription(advertiser_id=user.id, contact_id=with_push.id, p256dh=browser.p256dh,
                                auth=_b64(browser.auth),
                                endpoint=f"https://fcm.googleapis.com/fcm/send/{uuid.uuid4()}"))
        campaign = Campaign(advertiser_id=user.id, name="2x1 en fundas", type="promo", status="scheduled",
                            message_text="Hola {{nombre}}, esta semana 2x1 en fundas en {{negocio}} 📱",
                            segment={}, ab_test={"enabled": False, "web_only": True, "campaign_mode": "regular",
                                                 "has_coupon": True, "coupon_description": "2x1 en fundas",
                                                 "coupon_hours": 72})
        db.add(campaign)
        await db.commit()
        return user.id, with_push.id, without.id, campaign.id


async def _cleanup(user_id):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        for model in (Coupon, PushSubscription, Message):
            await db.execute(delete(model).where(model.advertiser_id == user_id))
        await db.execute(delete(Campaign).where(Campaign.advertiser_id == user_id))
        await db.execute(delete(Contact).where(Contact.advertiser_id == user_id))
        from app.models.campaign_segment_send import CampaignSegmentSend
        from app.models.send_block_log import SendBlockLog
        for model in (CampaignSegmentSend, SendBlockLog):
            await db.execute(delete(model).where(model.advertiser_id == user_id))
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()
    await engine.dispose()


def _request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/api/v1/x", "headers": [],
                    "client": (f"test-{uuid.uuid4()}", 1), "query_string": b""})


def test_web_only_campaign_end_to_end(vapid):
    browser = Browser()
    user_id, ana_id, beto_id, campaign_id = asyncio.run(_seed(browser))
    fcm = PushService()
    try:
        # ── 1. El dueño lanza la campaña: la tarea real de Celery ──────────────
        from app.workers import tasks

        whatsapp = MagicMock()
        with patch("app.services.messaging_throttle.is_human_hour", return_value=True), \
                patch("requests.post", fcm.post), \
                patch.object(tasks, "send_whatsapp_voice_note", whatsapp), \
                patch.object(tasks, "send_whatsapp_message", whatsapp):
            tasks.schedule_campaign(str(campaign_id))
        whatsapp.apply_async.assert_not_called()  # solo por web: cero WhatsApp
        whatsapp.delay.assert_not_called()

        # ── 2. Al navegador le llega un aviso que SÍ puede leer ────────────────
        assert len(fcm.received) == 1, "solo Alfredo tiene avisos"
        sent = fcm.received[0]
        assert sent["headers"]["content-encoding"] == "aes128gcm"
        public_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), _unb64(vapid))
        claims = _verify_vapid(sent["headers"], public_key, sent["url"])
        assert claims["sub"] == settings.VAPID_SUBJECT
        note = browser.read(sent["body"])
        assert note["title"] == "CityCell"
        assert "2x1 en fundas" in note["body"] and "Alfredo" in note["body"]
        token = make_portal_token(ana_id)
        # El aviso abre el chat, donde la promo ya está como burbuja.
        assert note["url"].startswith(f"https://www.iaradio.online/c/{token}?chat=1&n=")
        message_id = note["url"].split("&n=")[1]

        async def after_send():
            await engine.dispose()
            async with AsyncSessionLocal() as db:
                camp = await db.get(Campaign, campaign_id)
                msgs = (await db.execute(select(Message).where(Message.campaign_id == campaign_id))).scalars().all()
                coupons = (await db.execute(select(Coupon).where(Coupon.campaign_id == campaign_id))).scalars().all()
                return camp.status, msgs, coupons

        status, msgs, coupons = asyncio.run(after_send())
        assert status == "completed"  # no se autopausó por los que no tienen avisos
        assert [(m.contact_id, m.content, m.status) for m in msgs] == [(ana_id, "[PUSH] 2x1 en fundas", "sent")]
        assert str(msgs[0].id) == message_id
        assert [(c.contact_id, c.description) for c in coupons] == [(ana_id, "2x1 en fundas")]

        # ── 3. El cliente abre su tarjeta: ve la promo y su cupón ──────────────
        async def customer_opens():
            from app.api.v1.portal import (
                get_portal,
                get_promo,
                notification_opened,
                start_chat_session,
            )

            await engine.dispose()
            async with AsyncSessionLocal() as db:
                card = await get_portal(request=_request(), token=token, db=db)
                promo = await get_promo(request=_request(), token=token, campaign_id=campaign_id, db=db)
                # Tocó la notificación → "leído"
                opened = await notification_opened(request=_request(), token=token,
                                                   body={"message_id": message_id}, db=db)
                # "¡La quiero!" → el chat abre sabiendo de qué promo habla
                redis = FakeRedis()
                session = await start_chat_session(request=_request(), token=token, db=db, redis=redis,
                                                   body={"promo_id": str(campaign_id)})
                beto_card = await get_portal(request=_request(), token=make_portal_token(beto_id), db=db)
                return card, promo, opened, redis, session, beto_card

        card, promo, opened, redis, session, beto_card = asyncio.run(customer_opens())
        assert [p["title"] for p in card["promotions"]] == ["2x1 en fundas"]
        assert card["promotions"][0]["has_coupon"] is True
        assert promo["coupon"]["description"] == "2x1 en fundas" and promo["coupon"]["code"]
        assert "Alfredo" in promo["text"]
        assert opened == {"ok": True}
        chat_context = [v for k, v in redis.store.items() if session["session_id"] in k and "chat" in k]
        assert any("2x1 en fundas" in str(v) and promo["coupon"]["code"] in str(v) for v in chat_context)
        assert beto_card["promotions"] == []  # a quien no le llegó, no la ve

        # ── 4. Estadísticas del dueño: 1 enviada, 1 leída ──────────────────────
        async def stats():
            from app.api.v1.campaigns import campaign_stats

            await engine.dispose()
            async with AsyncSessionLocal() as db:
                return await campaign_stats(campaign_id, db=db, current_user=await db.get(User, user_id))

        s = asyncio.run(stats())
        assert s.get("sent") == 1, s
        assert s.get("read") == 1, s
    finally:
        asyncio.run(_cleanup(user_id))
