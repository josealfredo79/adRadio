"""Avisos de pedido y cita al dueño por el número central
(docs/specs/2026-10-23-avisos-al-dueno-por-central.md). Redis de verdad para
el tope; Meta (el WhatsApp del negocio y el central) simulado."""
import asyncio
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.core.redis import close_redis
from app.models.appointment import Appointment
from app.models.contact import Contact
from app.models.order import Order
from app.models.user import User
from app.services import owner_notify, platform_whatsapp


@contextmanager
def central_wa():
    """Para otras pruebas: número central encendido y simulado; da el mock de
    send_platform_text (args: número del dueño, texto)."""
    with patch.object(platform_whatsapp.settings, "IARADIO_WA_PHONE_NUMBER_ID", "999"), \
            patch("app.services.platform_whatsapp.send_platform_text", new_callable=AsyncMock,
                  return_value=("wamid.x", None)) as send:
        yield send


@pytest.fixture(autouse=True)
async def _central(monkeypatch):
    await close_redis()  # cada prueba corre en su propio event loop
    monkeypatch.setattr(platform_whatsapp.settings, "IARADIO_WA_PHONE_NUMBER_ID", "999")
    yield
    await close_redis()


def _owner(**kw) -> User:
    fields = {"business_name": "CityCell", "email": "x@wa.iaradio.online", "phone": "+529511112222", **kw}
    return User(id=uuid.uuid4(), **fields)


def _order() -> Order:
    return Order(id=uuid.uuid4(), order_number=2, items_raw="1 Cargador marca", customer_name="Ana",
                 delivery_address="Para recoger en el negocio", payment_method=None)


def _sends():
    """(WhatsApp propio, central) simulados."""
    own = patch("app.services.meta_service.send_whatsapp", new_callable=AsyncMock, return_value=("wamid.own", None))
    central = patch("app.services.platform_whatsapp.send_platform_text", new_callable=AsyncMock,
                    return_value=("wamid.central", None))
    return own, central


@pytest.mark.asyncio
async def test_caso1_order_notice_goes_through_central_without_own_whatsapp():
    from app.services.widget_order_service import _notify_owner

    own, central = _sends()
    with own as own_wa, central as central_wa, patch("app.core.email.send_new_order_email", new_callable=AsyncMock):
        await _notify_owner(_owner(), Contact(name="Ana", phone="+529511234567"), _order(), total=120.0)
    own_wa.assert_not_awaited()
    to, body = central_wa.await_args.args
    assert to == "+529511112222"
    assert "NUEVO PEDIDO #0002" in body and "👉 Escribirle al cliente" in body


@pytest.mark.asyncio
async def test_caso2_appointment_notice_goes_through_central():
    from app.services.appointment_booking_service import _notify_owner

    appt = Appointment(service="Corte", customer_name="Ana", customer_phone="+529511234567",
                       scheduled_at=datetime(2026, 10, 24, 17, 0, tzinfo=timezone.utc))
    own, central = _sends()
    with own as own_wa, central as central_wa, patch("app.core.email.send_new_appointment_email", new_callable=AsyncMock):
        await _notify_owner(_owner(), appt, "widget")
    own_wa.assert_not_awaited()
    body = central_wa.await_args.args[1]
    assert "NUEVA CITA" in body and "Corte" in body and "Ana" in body


@pytest.mark.asyncio
async def test_caso3_own_whatsapp_first():
    owner = _owner()
    own, central = _sends()
    with own as own_wa, central as central_wa, \
            patch("app.services.meta_service._connection", return_value=("pnid", "tok")):
        assert await owner_notify.notify_owner(owner, "📦 NUEVO PEDIDO") == "own"
    own_wa.assert_awaited_once()
    central_wa.assert_not_awaited()
    # No cuenta para el tope del central.
    assert await owner_notify._count_central(owner) == 1


@pytest.mark.asyncio
async def test_caso4_own_rejected_falls_back_to_central():
    own = patch("app.services.meta_service.send_whatsapp", new_callable=AsyncMock,
                return_value=(None, "(#131047) Re-engagement message"))
    _, central = _sends()
    with own as own_wa, central as central_wa, \
            patch("app.services.meta_service._connection", return_value=("pnid", "tok")):
        assert await owner_notify.notify_owner(_owner(), "📦 NUEVO PEDIDO") == "central"
    own_wa.assert_awaited_once()
    assert central_wa.await_args.args[1] == "📦 NUEVO PEDIDO"


@pytest.mark.asyncio
async def test_caso5_daily_cap_then_one_last_notice():
    owner = _owner()
    _, central = _sends()
    with central as central_wa:
        results = [await owner_notify.notify_owner(owner, f"aviso {i}") for i in range(1, 34)]
    assert results[:30] == ["central"] * 30
    assert results[30] == "cap" and results[31:] == [None, None]
    assert central_wa.await_count == 31
    assert "30 avisos" in central_wa.await_args_list[30].args[1]

    # Al día siguiente (hora de México) vuelve a avisar normal.
    class Tomorrow(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(tz) + timedelta(days=1)

    _, central = _sends()
    with central as central_wa, patch.object(owner_notify, "datetime", Tomorrow):
        assert await owner_notify.notify_owner(owner, "aviso de mañana") == "central"
    assert central_wa.await_args.args[1] == "aviso de mañana"


@pytest.mark.asyncio
async def test_caso6_no_owner_phone_sends_nothing(monkeypatch):
    own, central = _sends()
    with own as own_wa, central as central_wa:
        assert await owner_notify.notify_owner(_owner(phone=None), "📦") is None
        monkeypatch.setattr(platform_whatsapp.settings, "IARADIO_WA_PHONE_NUMBER_ID", "")
        assert await owner_notify.notify_owner(_owner(), "📦") is None
    own_wa.assert_not_awaited()
    central_wa.assert_not_awaited()


@pytest.mark.asyncio
async def test_caso7_email_still_sent():
    from app.services.widget_order_service import _notify_owner

    own, central = _sends()
    with own, central, patch("app.core.email.send_new_order_email", new_callable=AsyncMock) as email:
        await _notify_owner(_owner(email="dueno@citycell.mx"), Contact(name="Ana", phone="+529511234567"),
                            _order(), total=120.0)
        await asyncio.sleep(0.05)
    assert email.await_args.kwargs["to"] == "dueno@citycell.mx" and email.await_args.kwargs["order_number"] == 2
