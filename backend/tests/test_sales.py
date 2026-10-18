""""Cobré $___": ventas del mostrador y de pedidos (spec docs/specs/2026-10-17-cobre.md) — real-DB."""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import delete, select, update

from app.api.v1.admin import pilot_overview
from app.api.v1.orders import OrderStateUpdate, update_order_state
from app.api.v1.sales import (
    NewCustomer,
    SaleCreate,
    create_sale,
    delete_sale,
    sales_today,
    search_customers,
)
from app.database import AsyncSessionLocal, engine
from app.models.contact import Contact
from app.models.loyalty_stamp import LoyaltyStamp
from app.models.order import Order
from app.models.sale import Sale
from app.models.user import User

CONFIG = {"enabled": True, "stamps_required": 5, "reward": "Un kilo gratis"}


@pytest.fixture(autouse=True)
def _no_push():
    # El aviso del sello es push web; aquí no se manda nada.
    with patch("app.services.loyalty_service.notify_stamp", new=AsyncMock()):
        yield


@pytest.fixture
async def seeded():
    await engine.dispose()
    tail = f"{uuid.uuid4().int % 10**6:06d}"
    async with AsyncSessionLocal() as db:
        lupe = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Tortillería Lupita",
                    loyalty_config=CONFIG)
        otro = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Otro Negocio",
                    loyalty_config=None)
        db.add_all([lupe, otro])
        await db.flush()
        ana = Contact(advertiser_id=lupe.id, name="Ana López", phone=f"+52953{tail}1234")
        beto = Contact(advertiser_id=lupe.id, name="Beto Ruiz", phone=f"+52953{tail}5678")
        ajeno = Contact(advertiser_id=otro.id, name="Ana Ajena", phone=f"+52953{tail}9999")
        db.add_all([ana, beto, ajeno])
        await db.commit()
        ids = {"lupe": lupe.id, "otro": otro.id, "ana": ana.id, "beto": beto.id, "ajeno": ajeno.id, "tail": tail}
    yield ids
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        for uid in (ids["lupe"], ids["otro"]):
            await db.execute(delete(Sale).where(Sale.advertiser_id == uid))
            await db.execute(delete(LoyaltyStamp).where(LoyaltyStamp.advertiser_id == uid))
            await db.execute(delete(Order).where(Order.advertiser_id == uid))
            await db.execute(delete(Contact).where(Contact.advertiser_id == uid))
            await db.execute(delete(User).where(User.id == uid))
        await db.commit()
    await engine.dispose()


async def _sell(owner_id, **body):
    async with AsyncSessionLocal() as db:
        owner = await db.get(User, owner_id)
        return await create_sale(SaleCreate(**body), db=db, current_user=owner)


async def _sales(owner_id) -> list[Sale]:
    async with AsyncSessionLocal() as db:
        return list((await db.execute(select(Sale).where(Sale.advertiser_id == owner_id))).scalars().all())


async def _stamps(contact_id) -> int:
    async with AsyncSessionLocal() as db:
        return len((await db.execute(select(LoyaltyStamp).where(LoyaltyStamp.contact_id == contact_id))).scalars().all())


async def test_caso1_search_by_name_or_last_digits_then_charge_gives_a_stamp(seeded):
    async with AsyncSessionLocal() as db:
        lupe = await db.get(User, seeded["lupe"])
        by_digits = await search_customers(q="1234", db=db, current_user=lupe)
        by_name = await search_customers(q="beto", db=db, current_user=lupe)
    assert [c["name"] for c in by_digits] == ["Ana López"] and by_digits[0]["phone_last4"] == "1234"
    assert [c["name"] for c in by_name] == ["Beto Ruiz"]

    out = await _sell(seeded["lupe"], amount="85", contact_id=seeded["ana"])
    assert out["amount"] == 85.0 and out["stamped"] is True and out["customer"]["name"] == "Ana López"
    sales = await _sales(seeded["lupe"])
    assert len(sales) == 1 and sales[0].amount == Decimal("85.00") and sales[0].contact_id == seeded["ana"]
    assert await _stamps(seeded["ana"]) == 1


async def test_caso2_with_loyalty_off_the_sale_is_saved_without_stamp(seeded):
    async with AsyncSessionLocal() as db:
        db.add(Contact(advertiser_id=seeded["otro"], name="Caro", phone=f"+52953{seeded['tail']}4321"))
        await db.commit()
        caro = (await db.execute(select(Contact).where(Contact.name == "Caro",
                                                       Contact.advertiser_id == seeded["otro"]))).scalar_one()
    out = await _sell(seeded["otro"], amount=40, contact_id=caro.id)
    assert out["stamped"] is False and len(await _sales(seeded["otro"])) == 1
    assert await _stamps(caro.id) == 0


async def test_caso3_new_customer_is_created_once_and_gets_stamp(seeded):
    phone = f"953 {seeded['tail'][:3]} {seeded['tail'][3:]}7"  # como lo escribe el dueño
    first = await _sell(seeded["lupe"], amount="120", new_customer={"name": "Doña Mari", "phone": phone})
    again = await _sell(seeded["lupe"], amount="60", new_customer={"name": "Mari", "phone": phone})
    assert first["customer"]["id"] == again["customer"]["id"] and first["stamped"] and again["stamped"]
    async with AsyncSessionLocal() as db:
        maris = (await db.execute(select(Contact).where(Contact.advertiser_id == seeded["lupe"],
                                                        Contact.name == "Doña Mari"))).scalars().all()
    assert len(maris) == 1 and maris[0].source == "manual"
    with pytest.raises(ValidationError):
        NewCustomer(name="X", phone="123")


async def test_caso4_sale_without_customer_only_keeps_the_amount(seeded):
    out = await _sell(seeded["lupe"], amount="$1,250.50")
    assert out["customer"] is None and out["stamped"] is False
    (sale,) = await _sales(seeded["lupe"])
    assert sale.contact_id is None and sale.amount == Decimal("1250.50")


@pytest.mark.parametrize("bad", ["0", "-5", "abc", "", "100001", "nan"])
async def test_caso5_bad_amounts_are_rejected_with_a_reason(seeded, bad):
    with pytest.raises(HTTPException) as e:
        await _sell(seeded["lupe"], amount=bad, contact_id=seeded["ana"])
    assert e.value.status_code == 422 and e.value.detail
    assert await _sales(seeded["lupe"]) == [] and await _stamps(seeded["ana"]) == 0


async def test_caso6_undo_removes_the_sale_and_its_stamp_but_not_after_15_min(seeded):
    out = await _sell(seeded["lupe"], amount="85", contact_id=seeded["ana"])
    async with AsyncSessionLocal() as db:
        lupe = await db.get(User, seeded["lupe"])
        undone = await delete_sale(uuid.UUID(out["id"]), db=db, current_user=lupe)
    assert undone["today"] == {"count": 0, "total": 0.0}
    assert await _sales(seeded["lupe"]) == [] and await _stamps(seeded["ana"]) == 0

    old = await _sell(seeded["lupe"], amount="85", contact_id=seeded["ana"])
    async with AsyncSessionLocal() as db:
        await db.execute(update(Sale).where(Sale.id == uuid.UUID(old["id"]))
                         .values(created_at=datetime.now(timezone.utc) - timedelta(minutes=20)))
        await db.commit()
        lupe = await db.get(User, seeded["lupe"])
        with pytest.raises(HTTPException) as e:
            await delete_sale(uuid.UUID(old["id"]), db=db, current_user=lupe)
    assert e.value.status_code == 409


async def test_caso7_today_total(seeded):
    await _sell(seeded["lupe"], amount="85", contact_id=seeded["ana"])
    out = await _sell(seeded["lupe"], amount="15.50")
    assert out["today"] == {"count": 2, "total": 100.5}
    async with AsyncSessionLocal() as db:
        lupe = await db.get(User, seeded["lupe"])
        assert await sales_today(db=db, current_user=lupe) == {"count": 2, "total": 100.5}


async def test_caso8_order_amount_on_confirm_and_removed_on_cancel(seeded):
    async with AsyncSessionLocal() as db:
        order = Order(advertiser_id=seeded["lupe"], contact_id=seeded["beto"], order_number=1, state="collecting_payment")
        no_amount = Order(advertiser_id=seeded["lupe"], contact_id=seeded["beto"], order_number=2, state="collecting_payment")
        db.add_all([order, no_amount])
        await db.commit()
        lupe = await db.get(User, seeded["lupe"])
        await update_order_state(order.id, OrderStateUpdate(state="confirmed", amount="230"), current_user=lupe, db=db)
        # Reconfirmar con otro monto lo corrige, no duplica.
        await update_order_state(order.id, OrderStateUpdate(state="confirmed", amount="250"), current_user=lupe, db=db)
        await update_order_state(no_amount.id, OrderStateUpdate(state="confirmed"), current_user=lupe, db=db)
        with pytest.raises(HTTPException):
            await update_order_state(no_amount.id, OrderStateUpdate(state="confirmed", amount="-1"),
                                     current_user=lupe, db=db)
    (sale,) = await _sales(seeded["lupe"])
    assert sale.source == "order" and sale.amount == Decimal("250.00") and sale.contact_id == seeded["beto"]

    async with AsyncSessionLocal() as db:
        lupe = await db.get(User, seeded["lupe"])
        await update_order_state(order.id, OrderStateUpdate(state="cancelled"), current_user=lupe, db=db)
    assert await _sales(seeded["lupe"]) == []


async def test_caso8_order_sale_cannot_be_undone_from_the_cashier(seeded):
    async with AsyncSessionLocal() as db:
        order = Order(advertiser_id=seeded["lupe"], contact_id=seeded["beto"], order_number=1, state="collecting_payment")
        db.add(order)
        await db.commit()
        lupe = await db.get(User, seeded["lupe"])
        await update_order_state(order.id, OrderStateUpdate(state="confirmed", amount="99"), current_user=lupe, db=db)
    (sale,) = await _sales(seeded["lupe"])
    async with AsyncSessionLocal() as db:
        lupe = await db.get(User, seeded["lupe"])
        with pytest.raises(HTTPException) as e:
            await delete_sale(sale.id, db=db, current_user=lupe)
    assert e.value.status_code == 409


async def test_caso9_a_business_only_sees_and_touches_its_own(seeded):
    out = await _sell(seeded["lupe"], amount="85")
    async with AsyncSessionLocal() as db:
        otro = await db.get(User, seeded["otro"])
        assert await search_customers(q="ana", db=db, current_user=otro) == [
            {"id": str(seeded["ajeno"]), "name": "Ana Ajena", "phone_last4": "9999"}]
        assert (await sales_today(db=db, current_user=otro))["count"] == 0
        with pytest.raises(HTTPException) as e:
            await delete_sale(uuid.UUID(out["id"]), db=db, current_user=otro)
        assert e.value.status_code == 404
    # Ni cobrarle a un cliente de otro negocio.
    with pytest.raises(HTTPException) as e:
        await _sell(seeded["otro"], amount="10", contact_id=seeded["ana"])
    assert e.value.status_code == 404
    assert len(await _sales(seeded["lupe"])) == 1 and await _sales(seeded["otro"]) == []


async def test_caso10_admin_pilot_shows_sales_per_business(seeded):
    await _sell(seeded["lupe"], amount="85", contact_id=seeded["ana"])
    await _sell(seeded["lupe"], amount="15")
    async with AsyncSessionLocal() as db:
        data = await pilot_overview(db=db)
    row = next(n for n in data["negocios"] if n["id"] == str(seeded["lupe"]))
    other = next(n for n in data["negocios"] if n["id"] == str(seeded["otro"]))
    assert row["ventas_30d"] == 2 and row["vendido_30d"] == 100.0
    assert other["ventas_30d"] == 0 and other["vendido_30d"] == 0.0
