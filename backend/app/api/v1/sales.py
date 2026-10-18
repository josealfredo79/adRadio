"""Ventas del mostrador — /api/v1/sales (spec docs/specs/2026-10-17-cobre.md)."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.contact import validate_phone_e164
from app.services import sales_service
from app.services.sales_service import SaleError

router = APIRouter(prefix="/sales", tags=["sales"])


class NewCustomer(BaseModel):
    name: str
    phone: str

    @field_validator("phone")
    @classmethod
    def phone_format(cls, v: str) -> str:
        return validate_phone_e164(v)


class SaleCreate(BaseModel):
    # Texto o número: el dueño puede escribir "85", "$85" o "1,200".
    amount: str | float
    contact_id: uuid.UUID | None = None
    new_customer: NewCustomer | None = None


def _customer_out(c) -> dict:
    return {"id": str(c.id), "name": c.name, "phone_last4": (c.phone or "")[-4:]}


@router.get("/customers")
async def search_customers(
    q: str = Query("", max_length=60),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Buscar al cliente en el mostrador por nombre o últimos dígitos."""
    return [_customer_out(c) for c in await sales_service.find_customers(db, current_user, q)]


@router.get("/shortcuts")
async def sales_shortcuts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Montos rápidos y clientes recientes de la pantalla Cobrar."""
    data = await sales_service.shortcuts(db, current_user)
    return {"amounts": data["amounts"], "recent": [_customer_out(c) for c in data["recent"]]}


@router.get("/today")
async def sales_today(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    return await sales_service.today_summary(db, current_user)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_sale(
    body: SaleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """"Cobré $85": con cliente (le pone su sello), cliente nuevo o sin cliente."""
    from app.services.loyalty_service import notify_stamp

    try:
        amount = sales_service.parse_amount(body.amount)
        customer = None
        if body.new_customer is not None:
            customer = await sales_service.find_or_create_customer(
                db, current_user, body.new_customer.name, body.new_customer.phone
            )
        elif body.contact_id is not None:
            customer = await sales_service.own_contact(db, current_user, body.contact_id)
        sale, stamped = await sales_service.record_counter_sale(
            db, current_user, amount, customer.id if customer else None
        )
    except SaleError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except LookupError:
        raise HTTPException(status_code=404, detail="Cliente no encontrado") from None
    await db.commit()
    if stamped:
        await notify_stamp(db, current_user, customer.id)
    return {
        "id": str(sale.id),
        "amount": float(sale.amount),
        "customer": _customer_out(customer) if customer else None,
        "stamped": stamped,
        "today": await sales_service.today_summary(db, current_user),
    }


@router.delete("/{sale_id}")
async def delete_sale(
    sale_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Deshacer un cobro mal capturado (solo en los primeros minutos)."""
    try:
        await sales_service.undo_sale(db, current_user, sale_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Venta no encontrada") from None
    except SaleError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    await db.commit()
    return {"today": await sales_service.today_summary(db, current_user)}
