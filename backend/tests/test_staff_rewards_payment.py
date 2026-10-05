"""Personal (users.staff), canje del premio de la tarjeta desde el chat y
datos de cobro del negocio (2026-10-05)."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.domain.appointment_actions import AppointmentConflictError, check_no_conflict
from app.models.appointment import Appointment
from app.models.coupon import Coupon
from app.models.loyalty_stamp import LoyaltyStamp
from app.models.user import User
from app.services.availability_service import (
    TZ,
    free_staff,
    get_available_slots,
    staff_for,
)
from app.services.payment_info import payment_lines
from tests.test_customer_agent import (  # noqa: F401 — _keys es fixture autouse
    Redis,
    _cleanup,
    _keys,
    _next_open_day,
    _say,
    _seed,
    fake_claude,
    resp,
    text,
    tool,
    tool_results,
)

STAFF = [{"name": "Lupita", "services": []}, {"name": "Toño", "services": ["Barba"]}]


async def _with_staff(user_id, staff=STAFF):
    async with AsyncSessionLocal() as db:
        user = await db.get(User, user_id)
        user.staff = staff
        await db.commit()


async def _appt(user_id, when, staff_name=None, minutes=30):
    async with AsyncSessionLocal() as db:
        db.add(Appointment(advertiser_id=user_id, customer_name="Otro", service="Corte", scheduled_at=when,
                           duration_min=minutes, status="confirmed", staff_name=staff_name))
        await db.commit()


class TestStaffAvailability:
    def test_who_can_do_what(self):
        owner = SimpleNamespace(staff=STAFF)
        assert staff_for(owner, service="Corte de dama") == ["Lupita"]
        assert staff_for(owner, service="barba") == ["Lupita", "Toño"]
        assert staff_for(owner, staff="toño") == ["Toño"]
        assert staff_for(owner, staff="Pedro") == []

    def test_unassigned_appointments_use_up_capacity(self):
        t = datetime(2026, 10, 9, 10, 0, tzinfo=TZ)
        end = t + timedelta(minutes=30)
        everyone = ["Lupita", "Toño"]
        assert free_staff([(t, end, "Lupita")], t, end, everyone, everyone) == ["Toño"]
        assert free_staff([(t, end, None)], t, end, ["Lupita"], everyone) == ["Lupita"]
        assert free_staff([(t, end, None), (t, end, "Toño")], t, end, everyone, everyone) == []

    @pytest.mark.asyncio
    async def test_two_people_two_appointments_at_once(self):
        user_id, *_ = await _seed()
        await _with_staff(user_id)
        when = _next_open_day().replace(hour=10)
        try:
            await _appt(user_id, when, "Lupita")
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                any_slot = await get_available_slots(db, user, when.date(), 30, service="Barba")
                lupita = await get_available_slots(db, user, when.date(), 30, staff="Lupita")
                corte = await get_available_slots(db, user, when.date(), 30, service="Corte")
            assert when in any_slot  # Toño hace barba y está libre
            assert when not in lupita
            assert when not in corte  # solo Lupita hace cortes y ya está ocupada
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_owner_can_book_the_other_person_but_not_the_same(self):
        user_id, *_ = await _seed()
        await _with_staff(user_id)
        when = _next_open_day().replace(hour=11)
        try:
            await _appt(user_id, when, "Lupita")
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                await check_no_conflict(db, user, when, 30, staff_name="Toño")
                with pytest.raises(AppointmentConflictError):
                    await check_no_conflict(db, user, when, 30, staff_name="Lupita")
        finally:
            await _cleanup(user_id)


class TestAgentWithStaff:
    @pytest.mark.asyncio
    async def test_books_with_the_requested_person(self):
        user_id, ana, *_ = await _seed()
        await _with_staff(user_id)
        when = _next_open_day().replace(hour=12)
        r = Redis()
        try:
            claude, client = fake_claude(
                resp(tool("proponer_cita", servicio="Barba", fecha_hora=when.strftime("%Y-%m-%dT%H:%M"), con_quien="toño")),
                resp(text("Barba con Toño. ¿Lo confirmo?"), stop="end_turn"),
            )
            out = await _say(user_id, ana, "agéndame barba con toño", r, claude)
            assert "con Toño" in tool_results(client)[0]["listo_para_confirmar"] and out.confirm
            out = await _say(user_id, ana, "sí", r)
            assert "con Toño" in out.text
            async with AsyncSessionLocal() as db:
                appt = (await db.execute(select(Appointment).where(Appointment.contact_id == ana))).scalar_one()
            assert appt.staff_name == "Toño"
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_assigns_whoever_is_free_and_rejects_unknown_people(self):
        user_id, ana, *_ = await _seed()
        await _with_staff(user_id)
        when = _next_open_day().replace(hour=13)
        try:
            await _appt(user_id, when, "Lupita")
            claude, client = fake_claude(
                resp(tool("proponer_cita", servicio="Barba", fecha_hora=when.strftime("%Y-%m-%dT%H:%M"), con_quien="Pedro")),
                resp(tool("proponer_cita", servicio="Barba", fecha_hora=when.strftime("%Y-%m-%dT%H:%M"))),
                resp(text("Barba con Toño. ¿Lo confirmo?"), stop="end_turn"),
            )
            await _say(user_id, ana, "agéndame barba", Redis(), claude)
            unknown, assigned = tool_results(client)
            assert "Lupita, Toño" in unknown["error"]
            assert assigned["listo_para_confirmar"].endswith("con Toño")
        finally:
            await _cleanup(user_id)


class TestRedeemReward:
    async def _stamps(self, user_id, contact_id, n):
        async with AsyncSessionLocal() as db:
            db.add_all([LoyaltyStamp(advertiser_id=user_id, contact_id=contact_id, source="order", source_key=f"k{i}")
                        for i in range(n)])
            await db.commit()

    @pytest.mark.asyncio
    async def test_full_card_gives_a_code_after_yes(self):
        user_id, ana, *_ = await _seed()  # tarjeta de 5 sellos, premio "Orden gratis"
        await self._stamps(user_id, ana, 6)
        r = Redis()
        try:
            claude, _ = fake_claude(resp(tool("proponer_canjear_premio")),
                                    resp(text("¿Canjeo tu Orden gratis? ¿Lo confirmo?"), stop="end_turn"))
            out = await _say(user_id, ana, "quiero canjear mi premio", r, claude)
            assert out.confirm
            out = await _say(user_id, ana, "sí", r)
            assert "Orden gratis" in out.text
            async with AsyncSessionLocal() as db:
                coupon = (await db.execute(select(Coupon).where(Coupon.contact_id == ana))).scalar_one()
                left = (await db.execute(select(LoyaltyStamp).where(
                    LoyaltyStamp.contact_id == ana, LoyaltyStamp.redeemed_at.is_(None)))).scalars().all()
            assert coupon.code in out.text and coupon.source == "loyalty"
            assert coupon.expires_at > datetime.now(timezone.utc) + timedelta(days=29)
            assert len(left) == 1  # el sello que sobra pasa a la tarjeta nueva
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_incomplete_card_cannot_be_redeemed(self):
        user_id, ana, *_ = await _seed()
        await self._stamps(user_id, ana, 2)
        try:
            claude, client = fake_claude(resp(tool("proponer_canjear_premio")),
                                         resp(text("Llevas 2 de 5."), stop="end_turn"))
            out = await _say(user_id, ana, "canjea mi premio", Redis(), claude)
            assert "2 de 5" in tool_results(client)[0]["error"] and out.confirm is False
        finally:
            await _cleanup(user_id)


class TestPaymentInfo:
    def _owner(self, link=None, transfer=None):
        return SimpleNamespace(payment_link=link, payment_transfer=transfer)

    def test_card_gets_the_link_transfer_gets_the_bank_data(self):
        owner = self._owner("https://mpago.la/abc", "BBVA, CLABE 012345678901234567, a nombre de Lupita")
        assert "https://mpago.la/abc" in payment_lines(owner, "Tarjeta")
        assert "CLABE 012345678901234567" in payment_lines(owner, "transferencia")
        assert payment_lines(owner, "Efectivo") == ""

    def test_nothing_configured_adds_nothing(self):
        assert payment_lines(self._owner(), "Tarjeta") == ""

    def test_validator_requires_https(self):
        from pydantic import ValidationError

        from app.schemas.profile import ProfileUpdate

        with pytest.raises(ValidationError):
            ProfileUpdate(payment_link="javascript:alert(1)")
        assert ProfileUpdate(payment_link="").payment_link == ""
        assert ProfileUpdate(staff=[{"name": " Lupita ", "services": ["Corte"]}]).staff == [
            {"name": "Lupita", "services": ["Corte"]}]
