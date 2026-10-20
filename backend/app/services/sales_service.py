"""Ventas del negocio (spec docs/specs/2026-10-17-cobre.md).

El dueño registra lo que cobró en el mostrador ("Cobré $85") o el monto de un
pedido al confirmarlo. Es la base para medir si IaRadio le trae dinero. Un
cobro con cliente le pone su sello (si la tarjeta está activa); borrar el
cobro se lo quita. Cualquier cobro del mostrador de hoy se puede borrar.

Nada aquí hace commit: le toca al que llama, igual que loyalty_service.py.
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.order import Order
from app.models.sale import Sale
from app.models.user import User
from app.services.customer_account import contact_phone_canonical
from app.services.loyalty_service import add_stamp, remove_stamp

MAX_AMOUNT = Decimal(100000)


class SaleError(ValueError):
    """Lo que el dueño hizo mal; el mensaje se le muestra tal cual."""


def parse_amount(raw) -> Decimal:
    try:
        amount = Decimal(str(raw).replace("$", "").replace(",", "").strip())
    except (InvalidOperation, ValueError):
        raise SaleError("Escribe cuánto cobraste, por ejemplo 85") from None
    if not amount.is_finite() or amount <= 0:
        raise SaleError("El monto debe ser mayor a $0")
    if amount > MAX_AMOUNT:
        raise SaleError("¿Seguro? Ese monto pasa de $100,000. Revisa la cantidad.")
    return amount.quantize(Decimal("0.01"))


def _stamp_key(sale_id: uuid.UUID) -> str:
    return f"sale:{sale_id.hex}"


async def own_contact(db: AsyncSession, owner: User, contact_id: uuid.UUID) -> Contact:
    contact = (
        await db.execute(select(Contact).where(Contact.id == contact_id, Contact.advertiser_id == owner.id))
    ).scalar_one_or_none()
    if contact is None:
        raise LookupError("contact")
    return contact


async def find_customers(db: AsyncSession, owner: User, query: str, limit: int = 8) -> list[Contact]:
    """Por nombre o por los últimos dígitos del teléfono (lo que el dueño
    recuerda en el mostrador)."""
    q = query.strip()
    if not q:
        return []
    digits = "".join(ch for ch in q if ch.isdigit())
    match = Contact.name.ilike(f"%{q}%")
    if len(digits) >= 3:
        match = or_(match, contact_phone_canonical().endswith(digits))
    rows = await db.execute(
        select(Contact)
        .where(Contact.advertiser_id == owner.id, Contact.status != "blocked", match)
        .order_by(Contact.name)
        .limit(limit)
    )
    return list(rows.scalars().all())


async def find_or_create_customer(db: AsyncSession, owner: User, name: str, phone: str) -> Contact:
    """"Cliente nuevo" en el mostrador; si ese teléfono ya es cliente, se usa
    el mismo. `phone` ya viene validado (+52…)."""
    existing = (
        await db.execute(
            select(Contact)
            .where(Contact.advertiser_id == owner.id, contact_phone_canonical() == phone.lstrip("+"))
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    name = name.strip()
    if not name:
        raise SaleError("Escribe el nombre del cliente")
    contact = Contact(advertiser_id=owner.id, name=name[:200], phone=phone, source="manual")
    db.add(contact)
    await db.flush()
    return contact


async def record_counter_sale(
    db: AsyncSession, owner: User, amount: Decimal, contact_id: uuid.UUID | None
) -> tuple[Sale, bool]:
    """(venta, ¿le dio sello?)."""
    sale = Sale(id=uuid.uuid4(), advertiser_id=owner.id, contact_id=contact_id, amount=amount, source="counter")
    db.add(sale)
    await db.flush()
    stamped = False
    if contact_id is not None:
        stamped = await add_stamp(db, owner, contact_id, "manual", _stamp_key(sale.id))
    return sale, stamped


async def undo_sale(db: AsyncSession, owner: User, sale_id: uuid.UUID) -> None:
    sale = (
        await db.execute(select(Sale).where(Sale.id == sale_id, Sale.advertiser_id == owner.id))
    ).scalar_one_or_none()
    if sale is None:
        raise LookupError("sale")
    if sale.source != "counter":
        raise SaleError("Esta venta es de un pedido: cancélalo en Pedidos")
    if sale.created_at < _local_day_start():
        raise SaleError("Solo se pueden borrar los cobros de hoy")
    await remove_stamp(db, sale.contact_id, "manual", _stamp_key(sale.id))
    await db.delete(sale)


async def set_order_sale(db: AsyncSession, owner: User, order: Order, amount: Decimal) -> None:
    """El pedido confirmado vale `amount`; reconfirmarlo con otro monto lo corrige."""
    existing = (
        await db.execute(
            select(Sale).where(Sale.advertiser_id == owner.id, Sale.source == "order", Sale.source_key == str(order.id))
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.amount = amount
        existing.contact_id = order.contact_id
        return
    db.add(Sale(advertiser_id=owner.id, contact_id=order.contact_id, amount=amount,
                source="order", source_key=str(order.id)))


async def remove_order_sale(db: AsyncSession, owner: User, order: Order) -> None:
    await db.execute(
        delete(Sale).where(Sale.advertiser_id == owner.id, Sale.source == "order", Sale.source_key == str(order.id))
    )


def _local_day_start() -> datetime:
    from app.services.availability_service import TZ

    return datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)


async def today_counter_sales(db: AsyncSession, owner: User) -> list[tuple[Sale, Contact | None]]:
    """Los cobros del mostrador de hoy, el más nuevo primero: los que se pueden borrar."""
    rows = await db.execute(
        select(Sale, Contact)
        .outerjoin(Contact, Contact.id == Sale.contact_id)
        .where(Sale.advertiser_id == owner.id, Sale.source == "counter", Sale.created_at >= _local_day_start())
        .order_by(Sale.created_at.desc())
    )
    return [(sale, contact) for sale, contact in rows.all()]


async def today_summary(db: AsyncSession, owner: User) -> dict:
    """"Hoy llevas $X en N ventas" (día de México)."""
    row = (
        await db.execute(
            select(func.count(), func.coalesce(func.sum(Sale.amount), 0))
            .where(Sale.advertiser_id == owner.id, Sale.created_at >= _local_day_start())
        )
    ).one()
    return {"count": row[0], "total": float(row[1])}


DEFAULT_QUICK_AMOUNTS = [20, 50, 100, 200]


async def shortcuts(db: AsyncSession, owner: User, recent_limit: int = 5) -> dict:
    """Atajos de la pantalla Cobrar: los 4 montos que más cobra (o los de
    siempre si aún no hay ventas) y los últimos clientes a los que les cobró."""
    since = datetime.now(timezone.utc) - timedelta(days=60)
    top = (
        await db.execute(
            select(Sale.amount, func.count().label("n"))
            .where(Sale.advertiser_id == owner.id, Sale.source == "counter", Sale.created_at >= since)
            .group_by(Sale.amount)
            .order_by(func.count().desc(), Sale.amount)
            .limit(4)
        )
    ).all()
    amounts = [float(a) for a, _ in top]
    for default in DEFAULT_QUICK_AMOUNTS:
        if len(amounts) >= 4:
            break
        if default not in amounts:
            amounts.append(float(default))

    last_sale = (
        select(Sale.contact_id, func.max(Sale.created_at).label("at"))
        .where(Sale.advertiser_id == owner.id, Sale.contact_id.is_not(None))
        .group_by(Sale.contact_id)
        .subquery()
    )
    recent = (
        await db.execute(
            select(Contact)
            .join(last_sale, last_sale.c.contact_id == Contact.id)
            .where(Contact.advertiser_id == owner.id, Contact.status != "blocked")
            .order_by(last_sale.c.at.desc())
            .limit(recent_limit)
        )
    ).scalars().all()
    return {"amounts": sorted(amounts), "recent": list(recent)}
