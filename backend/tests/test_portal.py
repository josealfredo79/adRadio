"""Portal del cliente — token firmado (portal_service.py) y endpoints públicos
(api/v1/portal.py). Real-DB: lo que más importa probar es el aislamiento —
un link nunca debe mostrar ni dejar cancelar nada de otro contacto."""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import delete
from starlette.requests import Request

from app.api.v1.portal import (
    _banner_from_message,
    cancel_appointment,
    get_portal,
    get_promo,
    start_chat_session,
)
from app.api.v1.widget import SESSION_CONTACT_REDIS_PREFIX
from app.config import settings
from app.database import AsyncSessionLocal, engine
from app.models.appointment import Appointment
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.coupon import Coupon
from app.models.message import Message
from app.models.order import Order
from app.models.user import User
from app.services.portal_service import (
    make_portal_token,
    portal_footer,
    portal_url,
    promo_footer,
    promo_url,
    read_portal_token,
)

SECRET = "test-secret-for-portal-links"


@pytest.fixture(autouse=True)
def _secret_key(monkeypatch):
    monkeypatch.setattr(settings, "SECRET_KEY", SECRET)
    monkeypatch.setattr(settings, "FRONTEND_URL", "https://www.iaradio.online")


def _request() -> Request:
    scope = {
        "type": "http", "method": "GET", "path": "/api/v1/public/portal/x", "headers": [],
        "client": (f"test-{uuid.uuid4()}", 123), "query_string": b"",
    }
    return Request(scope)


class TestPortalToken:
    def test_round_trips_to_same_contact(self):
        cid = uuid.uuid4()
        assert read_portal_token(make_portal_token(cid)) == cid

    def test_token_is_short_and_url_safe(self):
        token = make_portal_token(uuid.uuid4())
        assert len(token) < 45
        assert all(c.isalnum() or c in "-_." for c in token)

    def test_tampered_signature_is_rejected(self):
        token = make_portal_token(uuid.uuid4())
        id_part, sig = token.split(".")
        flipped = ("A" if sig[0] != "A" else "B") + sig[1:]
        assert read_portal_token(f"{id_part}.{flipped}") is None

    def test_signature_of_one_contact_does_not_open_another(self):
        a, b = uuid.uuid4(), uuid.uuid4()
        sig_a = make_portal_token(a).split(".")[1]
        id_b = make_portal_token(b).split(".")[0]
        assert read_portal_token(f"{id_b}.{sig_a}") is None

    @pytest.mark.parametrize("garbage", ["", ".", "abc", "abc.def", "!!!.???", "a" * 200])
    def test_garbage_never_raises(self, garbage):
        assert read_portal_token(garbage) is None

    def test_different_secret_invalidates(self, monkeypatch):
        token = make_portal_token(uuid.uuid4())
        monkeypatch.setattr(settings, "SECRET_KEY", "otra-llave")
        assert read_portal_token(token) is None

    def test_no_secret_means_no_links(self, monkeypatch):
        monkeypatch.setattr(settings, "SECRET_KEY", "")
        assert read_portal_token(make_portal_token(uuid.uuid4())) is None
        assert portal_footer(uuid.uuid4()) == ""

    def test_footer_carries_the_portal_url(self):
        cid = uuid.uuid4()
        assert portal_url(cid) == f"https://www.iaradio.online/c/{make_portal_token(cid)}"
        assert portal_url(cid) in portal_footer(cid)

    def test_footer_is_empty_without_contact(self):
        assert portal_footer(None) == ""

    def test_promo_footer_points_inside_the_portal(self):
        cid, camp = uuid.uuid4(), uuid.uuid4()
        assert promo_url(cid, camp) == f"{portal_url(cid)}/promo/{camp}"
        assert promo_url(cid, camp) in promo_footer(cid, camp)
        assert promo_footer(None, camp) == "" and promo_footer(cid, None) == ""


class TestBannerFromMessage:
    def test_sent_banner(self):
        assert _banner_from_message("[BANNER] https://cdn/x.png") == "https://cdn/x.png"

    def test_pending_banner(self):
        assert _banner_from_message('[PENDING:banner] {"banner_url": "https://cdn/y.png", "caption": "hola"}') == "https://cdn/y.png"

    @pytest.mark.parametrize("content", ["hola", "[AUDIO] https://a.mp3", "[PENDING:banner] {roto", ""])
    def test_anything_else_is_none(self, content):
        assert _banner_from_message(content) is None


async def _seed():
    """Negocio con dos clientes (Ana y Beto), cada uno con su cita, pedido y
    cupón — para comprobar que el link de Ana solo ve lo de Ana."""
    await engine.dispose()
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        user = User(
            email=f"{uuid.uuid4()}@test.com", password_hash="x",
            business_name="Barbería Don Pepe", widget_color="#ff5500", slug=f"pepe-{uuid.uuid4().hex[:8]}",
        )
        db.add(user)
        await db.flush()
        ana = Contact(advertiser_id=user.id, name="Ana López", phone=f"+52155{uuid.uuid4().int % 10**8:08d}")
        beto = Contact(advertiser_id=user.id, name="Beto Ruiz", phone=f"+52155{uuid.uuid4().int % 10**8:08d}")
        db.add_all([ana, beto])
        await db.flush()

        def appt(contact, when, status="confirmed", service="Corte"):
            return Appointment(
                advertiser_id=user.id, contact_id=contact.id, customer_name=contact.name,
                service=service, scheduled_at=when, status=status,
            )

        ana_future = appt(ana, now + timedelta(days=2), service="Corte y barba")
        ana_past = appt(ana, now - timedelta(days=10), status="completed")
        beto_future = appt(beto, now + timedelta(days=1))
        db.add_all([ana_future, ana_past, beto_future])
        db.add_all([
            Order(advertiser_id=user.id, contact_id=ana.id, order_number=1, state="confirmed", items_raw="2 shampoo"),
            Order(advertiser_id=user.id, contact_id=beto.id, order_number=2, state="confirmed", items_raw="cera"),
        ])
        tag = uuid.uuid4().hex[:6].upper()
        db.add_all([
            Coupon(advertiser_id=user.id, contact_id=ana.id, code=f"ANA{tag}", discount_value=10,
                   expires_at=now + timedelta(days=5)),
            Coupon(advertiser_id=user.id, contact_id=ana.id, code=f"OLD{tag}", discount_value=10,
                   expires_at=now - timedelta(days=1)),
            Coupon(advertiser_id=user.id, contact_id=ana.id, code=f"USD{tag}", discount_value=10,
                   expires_at=now + timedelta(days=5), max_uses=1, used_count=1),
            Coupon(advertiser_id=user.id, contact_id=beto.id, code=f"BET{tag}", discount_value=10,
                   expires_at=now + timedelta(days=5)),
        ])
        await db.commit()
        return {
            "user_id": user.id, "ana": ana.id, "beto": beto.id,
            "ana_future": ana_future.id, "ana_past": ana_past.id, "beto_future": beto_future.id, "tag": tag,
        }


async def _cleanup(user_id):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Coupon).where(Coupon.advertiser_id == user_id))
        await db.execute(delete(Message).where(Message.advertiser_id == user_id))
        await db.execute(delete(Campaign).where(Campaign.advertiser_id == user_id))
        await db.execute(delete(Order).where(Order.advertiser_id == user_id))
        await db.execute(delete(Appointment).where(Appointment.advertiser_id == user_id))
        await db.execute(delete(Contact).where(Contact.advertiser_id == user_id))
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()
    await engine.dispose()


class TestGetPortal:
    @pytest.mark.asyncio
    async def test_invalid_token_is_404(self):
        async with AsyncSessionLocal() as db:
            with pytest.raises(HTTPException) as exc:
                await get_portal(request=_request(), token="nope.nope", db=db)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_valid_token_for_deleted_contact_is_404(self):
        async with AsyncSessionLocal() as db:
            with pytest.raises(HTTPException) as exc:
                await get_portal(request=_request(), token=make_portal_token(uuid.uuid4()), db=db)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_shows_only_this_contacts_data(self):
        s = await _seed()
        try:
            async with AsyncSessionLocal() as db:
                out = await get_portal(request=_request(), token=make_portal_token(s["ana"]), db=db)

            assert out["business"]["name"] == "Barbería Don Pepe"
            assert out["business"]["color"] == "#ff5500"
            assert out["customer"] == {"first_name": "Ana"}

            assert [a["id"] for a in out["upcoming_appointments"]] == [str(s["ana_future"])]
            assert out["upcoming_appointments"][0]["can_cancel"] is True
            assert [a["id"] for a in out["past_appointments"]] == [str(s["ana_past"])]
            assert out["past_appointments"][0]["can_cancel"] is False

            assert [o["items"] for o in out["orders"]] == ["2 shampoo"]
            assert out["orders"][0]["state_label"] == "Confirmado"
            # Solo el cupón vigente y sin usar de Ana — ni el vencido, ni el agotado, ni el de Beto.
            assert [c["code"] for c in out["coupons"]] == [f"ANA{s['tag']}"]

            # Nada de Beto, y nada sensible del contacto (teléfono, apellido).
            flat = str(out)
            assert "Beto" not in flat and "cera" not in flat
            assert "López" not in flat and "+52" not in flat
        finally:
            await _cleanup(s["user_id"])

    @pytest.mark.asyncio
    async def test_blocked_contact_loses_access(self):
        s = await _seed()
        try:
            async with AsyncSessionLocal() as db:
                contact = await db.get(Contact, s["ana"])
                contact.status = "blocked"
                await db.commit()
            async with AsyncSessionLocal() as db:
                with pytest.raises(HTTPException) as exc:
                    await get_portal(request=_request(), token=make_portal_token(s["ana"]), db=db)
            assert exc.value.status_code == 404
        finally:
            await _cleanup(s["user_id"])


class TestCancelAppointment:
    @pytest.mark.asyncio
    async def test_cancels_own_future_appointment(self):
        s = await _seed()
        try:
            with patch("app.api.v1.portal._notify_owner_cancelled", new=AsyncMock()) as notify:
                async with AsyncSessionLocal() as db:
                    out = await cancel_appointment(
                        request=_request(), token=make_portal_token(s["ana"]),
                        appointment_id=s["ana_future"], db=db,
                    )
            assert out["appointment"]["status"] == "cancelled"
            assert out["appointment"]["can_cancel"] is False
            notify.assert_awaited_once()
            async with AsyncSessionLocal() as db:
                assert (await db.get(Appointment, s["ana_future"])).status == "cancelled"
        finally:
            await _cleanup(s["user_id"])

    @pytest.mark.asyncio
    async def test_cannot_cancel_someone_elses_appointment(self):
        s = await _seed()
        try:
            async with AsyncSessionLocal() as db:
                with pytest.raises(HTTPException) as exc:
                    await cancel_appointment(
                        request=_request(), token=make_portal_token(s["ana"]),
                        appointment_id=s["beto_future"], db=db,
                    )
            assert exc.value.status_code == 404
            async with AsyncSessionLocal() as db:
                assert (await db.get(Appointment, s["beto_future"])).status == "confirmed"
        finally:
            await _cleanup(s["user_id"])

    @pytest.mark.asyncio
    async def test_cannot_cancel_past_appointment(self):
        s = await _seed()
        try:
            async with AsyncSessionLocal() as db:
                with pytest.raises(HTTPException) as exc:
                    await cancel_appointment(
                        request=_request(), token=make_portal_token(s["ana"]),
                        appointment_id=s["ana_past"], db=db,
                    )
            assert exc.value.status_code == 409
        finally:
            await _cleanup(s["user_id"])


class TestChatSession:
    @pytest.mark.asyncio
    async def test_session_is_bound_to_the_contact(self):
        s = await _seed()
        try:
            redis = AsyncMock()
            async with AsyncSessionLocal() as db:
                out = await start_chat_session(
                    request=_request(), token=make_portal_token(s["ana"]), db=db, redis=redis,
                )
            assert out["advertiser_id"] == str(s["user_id"])
            key, _ttl, value = redis.setex.await_args.args
            assert key == f"{SESSION_CONTACT_REDIS_PREFIX}{s['user_id']}:{out['session_id']}"
            assert value == str(s["ana"])
        finally:
            await _cleanup(s["user_id"])

    @pytest.mark.asyncio
    async def test_works_without_redis(self):
        s = await _seed()
        try:
            async with AsyncSessionLocal() as db:
                out = await start_chat_session(
                    request=_request(), token=make_portal_token(s["ana"]), db=db, redis=None,
                )
            assert out["session_id"]
        finally:
            await _cleanup(s["user_id"])


async def _seed_promos(s):
    """Sobre el negocio de _seed: una promo que Ana recibió (con banner y
    cupón), un testimonio ("voces") que también recibió, y una promo que solo
    le llegó a Beto."""
    await engine.dispose()
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        promo = Campaign(advertiser_id=s["user_id"], name="2x1 en cortes", type="promo",
                         message_text="Hola {{primer_nombre}}, este viernes 2x1 en {{negocio}}")
        voces = Campaign(advertiser_id=s["user_id"], name="Lo que dicen", type="voces", message_text="testimonio")
        beto_only = Campaign(advertiser_id=s["user_id"], name="Solo Beto", type="promo", message_text="secreto")
        db.add_all([promo, voces, beto_only])
        await db.flush()
        db.add_all([
            Message(advertiser_id=s["user_id"], contact_id=s["ana"], campaign_id=promo.id,
                    direction="outbound", content="[BANNER] https://cdn.test/ana.png", status="sent"),
            Message(advertiser_id=s["user_id"], contact_id=s["ana"], campaign_id=voces.id,
                    direction="outbound", content="testimonio", status="sent"),
            Message(advertiser_id=s["user_id"], contact_id=s["beto"], campaign_id=beto_only.id,
                    direction="outbound", content="secreto", status="sent"),
            Coupon(advertiser_id=s["user_id"], contact_id=s["ana"], campaign_id=promo.id,
                   code=f"PRO{s['tag']}", discount_value=50, expires_at=now + timedelta(days=3)),
        ])
        await db.commit()
        return {"promo": promo.id, "voces": voces.id, "beto_only": beto_only.id}


class TestPromotions:
    @pytest.mark.asyncio
    async def test_portal_lists_only_promos_this_contact_received(self):
        s = await _seed()
        try:
            c = await _seed_promos(s)
            async with AsyncSessionLocal() as db:
                out = await get_portal(request=_request(), token=make_portal_token(s["ana"]), db=db)
            assert [p["id"] for p in out["promotions"]] == [str(c["promo"])]
            promo = out["promotions"][0]
            assert promo["title"] == "2x1 en cortes"
            assert promo["excerpt"] == "Hola Ana, este viernes 2x1 en Barbería Don Pepe"
            assert promo["image_url"] == "https://cdn.test/ana.png"
            assert promo["has_coupon"] is True
            assert "secreto" not in str(out)
        finally:
            await _cleanup(s["user_id"])

    @pytest.mark.asyncio
    async def test_promo_page_is_personalized_with_its_coupon(self):
        s = await _seed()
        try:
            c = await _seed_promos(s)
            async with AsyncSessionLocal() as db:
                out = await get_promo(
                    request=_request(), token=make_portal_token(s["ana"]), campaign_id=c["promo"], db=db,
                )
            assert out["text"] == "Hola Ana, este viernes 2x1 en Barbería Don Pepe"
            assert out["coupon"]["code"] == f"PRO{s['tag']}"
        finally:
            await _cleanup(s["user_id"])

    @pytest.mark.asyncio
    @pytest.mark.parametrize("which", ["beto_only", "voces"])
    async def test_promo_not_received_or_not_commercial_is_404(self, which):
        s = await _seed()
        try:
            c = await _seed_promos(s)
            async with AsyncSessionLocal() as db:
                with pytest.raises(HTTPException) as exc:
                    await get_promo(
                        request=_request(), token=make_portal_token(s["ana"]), campaign_id=c[which], db=db,
                    )
            assert exc.value.status_code == 404
        finally:
            await _cleanup(s["user_id"])


class TestOrderStateLabel:
    def test_recent_incomplete_order_is_in_progress(self):
        from app.api.v1.portal import _order_state_label
        now = datetime.now(timezone.utc)
        o = Order(state="collecting_address", created_at=now - timedelta(minutes=5))
        assert _order_state_label(o, now) == "En proceso"

    def test_abandoned_order_says_so(self):
        from app.api.v1.portal import _order_state_label
        now = datetime.now(timezone.utc)
        o = Order(state="collecting_payment", created_at=now - timedelta(days=2))
        assert _order_state_label(o, now) == "Sin terminar"

    def test_confirmed_order_stays_confirmed_forever(self):
        from app.api.v1.portal import _order_state_label
        now = datetime.now(timezone.utc)
        o = Order(state="confirmed", created_at=now - timedelta(days=200))
        assert _order_state_label(o, now) == "Confirmado"


class TestDashboardPortalLink:
    @pytest.mark.asyncio
    async def test_owner_gets_link_only_for_own_contacts(self):
        from app.api.v1.contacts import get_portal_link
        s = await _seed()
        other_id = None
        try:
            async with AsyncSessionLocal() as db:
                owner = await db.get(User, s["user_id"])
                out = await get_portal_link(contact_id=s["ana"], db=db, current_user=owner)
            assert out["url"] == portal_url(s["ana"])

            async with AsyncSessionLocal() as db:
                other = User(email=f"{uuid.uuid4()}@test.com", password_hash="x")
                db.add(other)
                await db.commit()
                other_id = other.id
            async with AsyncSessionLocal() as db:
                other = await db.get(User, other_id)
                with pytest.raises(HTTPException) as exc:
                    await get_portal_link(contact_id=s["ana"], db=db, current_user=other)
            assert exc.value.status_code == 404
        finally:
            await _cleanup(s["user_id"])
            if other_id:
                await _cleanup(other_id)



class TestChatFromPromo:
    @pytest.mark.asyncio
    async def test_promo_and_coupon_seed_the_bot_history(self):
        import json as _json

        from app.api.v1.widget import CHAT_REDIS_PREFIX
        s = await _seed()
        try:
            c = await _seed_promos(s)
            redis = AsyncMock()
            async with AsyncSessionLocal() as db:
                out = await start_chat_session(
                    request=_request(), token=make_portal_token(s["ana"]), db=db, redis=redis,
                    body={"promo_id": str(c["promo"])},
                )
            calls = {call.args[0]: call.args[2] for call in redis.setex.await_args_list}
            history = _json.loads(calls[f"{CHAT_REDIS_PREFIX}{s['user_id']}:{out['session_id']}"])
            assert history[0]["role"] == "assistant"
            assert "2x1 en cortes" in history[0]["content"]
            assert f"PRO{s['tag']}" in history[0]["content"]
        finally:
            await _cleanup(s["user_id"])

    @pytest.mark.asyncio
    @pytest.mark.parametrize("promo", ["beto_only", "garbage"])
    async def test_foreign_or_bad_promo_seeds_nothing(self, promo):
        s = await _seed()
        try:
            c = await _seed_promos(s)
            redis = AsyncMock()
            promo_id = str(c[promo]) if promo in c else "no-es-uuid"
            async with AsyncSessionLocal() as db:
                await start_chat_session(
                    request=_request(), token=make_portal_token(s["ana"]), db=db, redis=redis,
                    body={"promo_id": promo_id},
                )
            assert redis.setex.await_count == 1  # solo el vínculo sesión→contacto
        finally:
            await _cleanup(s["user_id"])
