"""
Contacts router — /api/v1/contacts
"""
import csv
import io
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.contact import Contact
from app.models.user import User
from app.schemas.contact import ContactCreate, ContactListResponse, ContactOut, ContactUpdate
from app.workers.tasks import import_contacts_csv

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.get("", response_model=ContactListResponse)
async def list_contacts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
    tag: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(Contact).where(Contact.advertiser_id == current_user.id)
    if status_filter:
        q = q.where(Contact.status == status_filter)
    if tag:
        q = q.where(Contact.tags.any(tag))

    count_result = await db.execute(select(func.count()).select_from(q.subquery()))
    total = count_result.scalar_one()

    q = q.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(q)
    contacts = result.scalars().all()

    return ContactListResponse(
        items=[ContactOut.model_validate(c) for c in contacts],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=ContactOut, status_code=status.HTTP_201_CREATED)
async def create_contact(
    body: ContactCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Check for duplicate phone for this advertiser
    existing = await db.execute(
        select(Contact).where(
            Contact.advertiser_id == current_user.id,
            Contact.phone == body.phone,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Ya existe un contacto con ese número")

    contact = Contact(
        advertiser_id=current_user.id,
        **body.model_dump(),
    )
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    return ContactOut.model_validate(contact)


@router.patch("/{contact_id}", response_model=ContactOut)
async def update_contact(
    contact_id: uuid.UUID,
    body: ContactUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Contact).where(
            Contact.id == contact_id,
            Contact.advertiser_id == current_user.id,
        )
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contacto no encontrado")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(contact, field, value)

    await db.commit()
    await db.refresh(contact)
    return ContactOut.model_validate(contact)


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Contact).where(
            Contact.id == contact_id,
            Contact.advertiser_id == current_user.id,
        )
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contacto no encontrado")

    await db.delete(contact)
    await db.commit()


@router.post("/import-csv")
async def import_csv(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    if file.content_type not in ("text/csv", "application/vnd.ms-excel"):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos CSV")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10MB limit for CSV
        raise HTTPException(status_code=413, detail="El archivo es demasiado grande (máx 10MB)")

    # Basic validation: check it's parseable
    try:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8")))
        rows = list(reader)
    except Exception:
        raise HTTPException(status_code=400, detail="El archivo CSV no es válido")

    if len(rows) > 10_000:
        raise HTTPException(status_code=400, detail="Máximo 10,000 registros por importación")

    # Dispatch to Celery
    import_contacts_csv.delay(str(current_user.id), rows)

    return {"message": f"Importando {len(rows)} contactos en segundo plano"}


@router.get("/export-csv")
async def export_contacts_csv(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export all contacts for the current advertiser as a UTF-8 CSV download."""
    result = await db.execute(
        select(Contact)
        .where(Contact.advertiser_id == current_user.id)
        .order_by(Contact.created_at.desc())
    )
    contacts = result.scalars().all()

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=["name", "phone", "email", "city", "status", "tags", "engagement_score", "created_at"],
    )
    writer.writeheader()
    for c in contacts:
        writer.writerow({
            "name": c.name,
            "phone": c.phone,
            "email": c.email or "",
            "city": c.city or "",
            "status": c.status,
            "tags": ",".join(c.tags or []),
            "engagement_score": c.engagement_score,
            "created_at": c.created_at.isoformat() if c.created_at else "",
        })

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=contactos_iaradio.csv"},
    )
