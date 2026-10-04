"""Tarjeta de lealtad del portal (loyalty_service.py) — real-DB: sellos
idempotentes, regalo de bienvenida, sellos automáticos por cita/pedido,
entrega del premio, lo que sabe el bot y la invitación con regalo."""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import delete, select
from starlette.requests import Request

from app.api.v1.appointments import update_appointment
from app.api.v1.contacts import (
    add_contact_stamp,
    get_contact_loyalty,
    redeem_contact_reward,
)
from app.api.v1.orders import OrderStateUpdate, update_order_state
from app.api.v1.portal import get_portal, push_subscribe
from app.config import settings
from app.database import AsyncSessionLocal, engine
from app.models.appointment import Appointment
from app.models.contact import Contact
from app.models.loyalty_stamp import LoyaltyStamp
from app.models.order import Order
from app.models.push_subscription import PushSubscription
from app.models.user import User
from app.schemas.appointment import AppointmentUpdate
from app.schemas.profile import ProfileUpdate
from app.services import loyalty_service as ls
from app.services import portal_service as ps
from app.services.portal_service import make_portal_token

CONFIG = {"enabled": True, "stamps_required": 3, "reward": "Un corte gratis"}


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setattr(settings, "SECRET_KEY", "test-secret-for-loyalty")
    monkeypatch.setattr(settings, "FRONTEND_URL", "https://www.iaradio.online")


def _request() -> Request:
    return Request({
        "type": "http", "method": "GET", "path": "/api/v1/public/portal/x",
        "headers": [(b"user-agent", b"Mozilla/5.0 (Linux; Android 14)")],
        "client": (f"test-{uuid.uuid4()}", 123), "query_string": b"",
    })


async def _seed(config: dict | None = CONFIG):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Barbería Don Pepe",
                    loyalty_config=config)
        db.add(user)
        await db.flush()
        ana = Contact(advertiser_id=user.id, name="Ana López", phone=f"+52155{uuid.uuid4().int % 10**8:08d}")
        beto = Contact(advertiser_id=user.id, name="Beto Ruiz", phone=f"+52155{uuid.uuid4().int % 10**8:08d}")
        db.add_all([ana, beto])
        await db.commit()
        return user.id, ana.id, beto.id


async def _cleanup(user_id):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(LoyaltyStamp).where(LoyaltyStamp.advertiser_id == user_id))
        await db.execute(delete(PushSubscription).where(PushSubscription.advertiser_id == user_id))
        await db.execute(delete(Order).where(Order.advertiser_id == user_id))
        await db.execute(delete(Appointment).where(Appointment.advertiser_id == user_id))
        await db.execute(delete(Contact).where(Contact.advertiser_id == user_id))
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()
    await engine.dispose()


async def _stamps(contact_id) -> list[str]:
    async with AsyncSessionLocal() as db:
        return sorted((await db.execute(
            select(LoyaltyStamp.source).where(LoyaltyStamp.contact_id == contact_id, LoyaltyStamp.redeemed_at.is_(None))
        )).scalars().all())


class TestConfig:
    def test_disabled_or_without_reward_means_no_card(self):
        assert ls.loyalty_config(User(loyalty_config=None)) is None
        assert ls.loyalty_config(User(loyalty_config={"enabled": True, "reward": "  "})) is None
        assert ls.loyalty_config(User(loyalty_config={**CONFIG, "enabled": False})) is None
        assert ls.loyalty_config(User(loyalty_config=CONFIG))["stamps_required"] == 3

    def test_profile_validation(self):
        out = ProfileUpdate(loyalty_config={"enabled": True, "stamps_required": "10", "reward": " Café gratis "})
        assert out.loyalty_config == {"enabled": True, "stamps_required": 10, "reward": "Café gratis"}
        with pytest.raises(ValidationError):
            ProfileUpdate(loyalty_config={"enabled": True, "stamps_required": 8, "reward": ""})
        with pytest.raises(ValidationError):
            ProfileUpdate(loyalty_config={"enabled": True, "stamps_required": 1, "reward": "x"})
        # Apagada se puede guardar sin premio.
        assert ProfileUpdate(loyalty_config={"enabled": False}).loyalty_config["enabled"] is False


class TestWelcomeGift:
    @pytest.mark.asyncio
    async def test_opening_the_portal_gives_one_welcome_stamp_ever(self):
        user_id, ana, beto = await _seed()
        try:
            for _ in range(2):
                async with AsyncSessionLocal() as db:
                    data = await get_portal(request=_request(), token=make_portal_token(ana), db=db)
            assert data["loyalty"]["stamps"] == 1 and data["loyalty"]["required"] == 3
            assert data["loyalty"]["reward"] == "Un corte gratis"
            assert data["loyalty"]["history"][0]["label"] == "Regalo de bienvenida"
            assert await _stamps(ana) == ["welcome"]
            assert await _stamps(beto) == []  # el link de Ana no le sella a Beto
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_no_card_no_stamps(self):
        user_id, ana, _ = await _seed(config=None)
        try:
            async with AsyncSessionLocal() as db:
                data = await get_portal(request=_request(), token=make_portal_token(ana), db=db)
            assert data["loyalty"] is None
            assert await _stamps(ana) == []
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_turning_on_notifications_gives_the_extra_stamp_once(self):
        user_id, ana, _ = await _seed()
        try:
            for i in range(2):
                body = {"endpoint": f"https://fcm.googleapis.com/fcm/send/{uuid.uuid4()}",
                        "keys": {"p256dh": "k" * 20, "auth": "a" * 10}}
                with patch("app.api.v1.portal.push_enabled", return_value=True):
                    async with AsyncSessionLocal() as db:
                        out = await push_subscribe(request=_request(), token=make_portal_token(ana), body=body, db=db)
                assert out["stamped"] is (i == 0)
            assert await _stamps(ana) == ["push"]
        finally:
            await _cleanup(user_id)


class TestAutomaticStamps:
    @pytest.mark.asyncio
    async def test_completed_appointment_stamps_once_and_undoing_removes_it(self):
        user_id, ana, _ = await _seed()
        try:
            async with AsyncSessionLocal() as db:
                appt = Appointment(advertiser_id=user_id, contact_id=ana, customer_name="Ana", service="Corte",
                                   scheduled_at=datetime.now(timezone.utc) - timedelta(hours=1), status="confirmed")
                db.add(appt)
                await db.commit()
                appt_id = appt.id
            push = AsyncMock(return_value=1)
            with patch("app.services.web_push.push_to_contact", push):
                for status in ("completed", "completed"):
                    async with AsyncSessionLocal() as db:
                        user = await db.get(User, user_id)
                        await update_appointment(appt_id, AppointmentUpdate(status=status), current_user=user, db=db)
            assert await _stamps(ana) == ["appointment"]
            push.assert_awaited_once()  # el segundo "completada" no vuelve a avisar
            assert "Llevas 1 de 3" in push.await_args.kwargs["body"]

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                await update_appointment(appt_id, AppointmentUpdate(status="no_show"), current_user=user, db=db)
            assert await _stamps(ana) == []
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_owner_confirming_and_cancelling_an_order(self):
        user_id, ana, _ = await _seed()
        try:
            async with AsyncSessionLocal() as db:
                order = Order(advertiser_id=user_id, contact_id=ana, order_number=1, state="collecting_payment")
                db.add(order)
                await db.commit()
                order_id = order.id
            with patch("app.services.web_push.push_to_contact", AsyncMock(return_value=0)):
                async with AsyncSessionLocal() as db:
                    user = await db.get(User, user_id)
                    await update_order_state(order_id, OrderStateUpdate(state="confirmed"), current_user=user, db=db)
            assert await _stamps(ana) == ["order"]
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                await update_order_state(order_id, OrderStateUpdate(state="cancelled"), current_user=user, db=db)
            assert await _stamps(ana) == []
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_web_chat_order_confirmation_carries_the_stamp_line(self):
        from app.services.widget_order_service import _advance

        user_id, ana, _ = await _seed()
        try:
            async with AsyncSessionLocal() as db:
                order = Order(advertiser_id=user_id, contact_id=ana, order_number=1, state="collecting_payment",
                              items_raw="cera", customer_name="Ana", delivery_address="Centro")
                db.add(order)
                await db.commit()
                user, contact = await db.get(User, user_id), await db.get(Contact, ana)
                with patch("app.services.widget_order_service._notify_owner", AsyncMock()):
                    reply = await _advance(db, user, contact, order, "Efectivo")
            assert "⭐ ¡Sumaste un sello! Llevas 1 de 3 para: Un corte gratis" in reply
            assert await _stamps(ana) == ["order"]
        finally:
            await _cleanup(user_id)


class TestOwnerCard:
    @pytest.mark.asyncio
    async def test_manual_stamps_then_redeem_carries_leftovers(self):
        user_id, ana, _ = await _seed()
        try:
            with patch("app.services.web_push.push_to_contact", AsyncMock(return_value=0)):
                for _ in range(4):
                    async with AsyncSessionLocal() as db:
                        user = await db.get(User, user_id)
                        out = await add_contact_stamp(ana, db=db, current_user=user)
            assert out["card"]["stamps"] == 4 and out["card"]["rewards_ready"] == 1

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                out = await redeem_contact_reward(ana, db=db, current_user=user)
            assert out["card"]["stamps"] == 1 and out["card"]["rewards_ready"] == 0

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with pytest.raises(HTTPException) as exc:
                    await redeem_contact_reward(ana, db=db, current_user=user)
                assert exc.value.status_code == 409
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_other_business_cannot_touch_the_card(self):
        user_id, ana, _ = await _seed()
        other_id, _, _ = await _seed()
        try:
            async with AsyncSessionLocal() as db:
                other = await db.get(User, other_id)
                with pytest.raises(HTTPException) as exc:
                    await get_contact_loyalty(ana, db=db, current_user=other)
                assert exc.value.status_code == 404
                with pytest.raises(HTTPException):
                    await add_contact_stamp(ana, db=db, current_user=other)
        finally:
            await _cleanup(user_id)
            await _cleanup(other_id)

    @pytest.mark.asyncio
    async def test_manual_stamp_without_card_is_409(self):
        user_id, ana, _ = await _seed(config=None)
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with pytest.raises(HTTPException) as exc:
                    await add_contact_stamp(ana, db=db, current_user=user)
                assert exc.value.status_code == 409
        finally:
            await _cleanup(user_id)


class TestBotAndInvite:
    @pytest.mark.asyncio
    async def test_bot_note_knows_the_program_and_this_customer(self):
        user_id, ana, _ = await _seed()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                assert await ls.has_unopened_gift(db, user, ana) is True
                await ls.add_stamp(db, user, ana, "welcome")
                await db.commit()
                assert await ls.has_unopened_gift(db, user, ana) is False
                note = await ls.bot_note(db, user, ana)
                assert "Un corte gratis" in note and "lleva 1 de 3" in note
                assert "ESTE CLIENTE" not in await ls.bot_note(db, user, None)
                user.loyalty_config = None
                assert await ls.bot_note(db, user, ana) == ""
                assert await ls.has_unopened_gift(db, user, ana) is False
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_gift_invite_goes_out_on_the_first_message(self):
        from tests.test_portal_web_shift import FakeRedis

        cid = uuid.uuid4()
        out = await ps.maybe_portal_invite(FakeRedis(), cid, "hola", "¡Hola!", gift=True)
        assert out.startswith("\n\n🎁") and ps.portal_url(cid) in out
        # Sin regalo, el "hola" del primer mensaje no invita (regla de siempre).
        assert await ps.maybe_portal_invite(FakeRedis(), uuid.uuid4(), "hola", "¡Hola!") == ""
