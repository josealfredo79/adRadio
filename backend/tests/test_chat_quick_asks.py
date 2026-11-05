import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete

from app.database import AsyncSessionLocal, engine
from app.models.appointment import Appointment
from app.models.product import Product
from app.models.user import User
from app.services.chat_quick_asks import (
    SALES_QUICK_ASKS,
    chat_quick_asks,
    chat_quick_asks_for,
)


def test_iaradio_account_gets_sales_buttons():
    assert chat_quick_asks(User(email="TecnologicoTlaxiaco@gmail.com")) == SALES_QUICK_ASKS


def test_other_businesses_keep_default_buttons():
    assert chat_quick_asks(User(email="tacos@example.com")) is None
    assert chat_quick_asks(User(email=None)) is None


async def _asks(products: int = 0, appointments: tuple = (), **fields) -> list[str]:
    """appointments: (servicio, estado, teléfono) de citas que ya tiene el negocio."""
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", **fields)
        db.add(user)
        await db.flush()
        for i in range(products):
            db.add(Product(advertiser_id=user.id, name=f"P{i}", price=10, active=True))
        for service, status, phone in appointments:
            db.add(Appointment(advertiser_id=user.id, customer_name="Cliente", customer_phone=phone,
                               service=service, status=status,
                               scheduled_at=datetime.now(timezone.utc) + timedelta(days=1)))
        await db.commit()
        try:
            return [a["text"] for a in await chat_quick_asks_for(db, user)]
        finally:
            await db.execute(delete(Product).where(Product.advertiser_id == user.id))
            await db.execute(delete(Appointment).where(Appointment.advertiser_id == user.id))
            await db.execute(delete(User).where(User.id == user.id))
            await db.commit()


@pytest.mark.asyncio
async def test_a_phone_shop_with_products_is_not_offered_appointments():
    # Prueba CityCell 2026-11-04: una tienda de celulares mostraba "Quiero agendar una cita".
    asks = await _asks(products=2, business_category="Tienda de celulares", delivers_home=True)
    assert "Quiero agendar una cita" not in asks
    assert "Quiero hacer un pedido" in asks and "¿Hacen entregas a domicilio?" in asks
    assert len(asks) == 4


@pytest.mark.asyncio
async def test_a_salon_gets_appointments_and_no_order_without_products():
    asks = await _asks(business_category="Estética")
    assert "Quiero agendar una cita" in asks
    assert "Quiero hacer un pedido" not in asks


@pytest.mark.asyncio
async def test_listed_appointment_services_mean_appointments():
    asks = await _asks(appointment_services=[{"name": "Reparación", "minutes": 60}])
    assert "Quiero agendar una cita" in asks


@pytest.mark.asyncio
async def test_the_iaradio_account_keeps_its_sales_buttons():
    async with AsyncSessionLocal() as db:
        assert await chat_quick_asks_for(db, User(email="tecnologicotlaxiaco@gmail.com")) == SALES_QUICK_ASKS


OWNER = "+5219531953182"


@pytest.mark.asyncio
async def test_test_appointments_do_not_make_a_phone_shop_take_appointments():
    # CityCell 2026-11-04: 3 citas de prueba ("Cita general", 2 canceladas) seguían
    # mostrando "agendar una cita".
    asks = await _asks(products=2, business_category="Tienda de celulares", phone=OWNER, appointments=(
        ("Cita general", "cancelled", "+5219531112233"),
        ("Cita general", "confirmed", "+5219531112233"),
        ("Reparación de pantalla", "confirmed", OWNER),
        ("Reparación de pantalla", "cancelled", "+5219534445566"),
    ))
    assert "Quiero agendar una cita" not in asks


@pytest.mark.asyncio
async def test_a_real_customer_appointment_still_shows_the_button():
    asks = await _asks(products=2, business_category="Tienda de celulares", phone=OWNER, appointments=(
        ("Reparación de pantalla", "confirmed", "+5219534445566"),
    ))
    assert "Quiero agendar una cita" in asks
