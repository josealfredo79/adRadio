"""
Contacts router — /api/v1/contacts
"""
import csv
import io
import logging
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, UploadFile, File, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.rate_limiter import limiter
from app.database import get_db
from app.models.contact import Contact
from app.models.user import User
from app.schemas.contact import ContactCreate, ContactListResponse, ContactOut, ContactUpdate
from app.workers.tasks import import_contacts_csv
from app.services.analytics_service import capture_event

class BulkTagRequest(BaseModel):
    contact_ids: list[str]
    tags: list[str]
    action: str  # "add" | "remove"


class BulkDeleteRequest(BaseModel):
    contact_ids: list[str]


class BulkStatusRequest(BaseModel):
    contact_ids: list[str]
    status: str


class BulkSendCampaignRequest(BaseModel):
    contact_ids: list[str]
    campaign_id: str


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/contacts", tags=["contacts"])

@router.get("", response_model=ContactListResponse)
async def list_contacts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
    tag: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ContactListResponse:
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


@router.get("/pipeline", response_model=list[ContactOut])
async def list_pipeline_contacts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ContactOut]:
    """All active contacts for the kanban board — unpaginated (capped) since
    the board wants every card, not a page."""
    result = await db.execute(
        select(Contact)
        .where(Contact.advertiser_id == current_user.id, Contact.status == "active")
        .order_by(Contact.created_at.desc())
        .limit(500)
    )
    return [ContactOut.model_validate(c) for c in result.scalars().all()]


@router.post("", response_model=ContactOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def create_contact(
    request: Request,
    body: ContactCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ContactOut:
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

    logger.info("Contact created: %s (%s) by user %s", contact.name, contact.phone, current_user.id)
    capture_event("contact_created", user_id=current_user.id)

    from app.services.webhook_dispatcher import dispatch_webhook_event
    await dispatch_webhook_event(
        "contact.created",
        {"id": str(contact.id), "name": contact.name, "phone": contact.phone},
        db,
        advertiser_id=current_user.id,
    )

    return ContactOut.model_validate(contact)


@router.patch("/{contact_id}", response_model=ContactOut)
async def update_contact(
    contact_id: uuid.UUID,
    body: ContactUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ContactOut:
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
) -> None:
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
@limiter.limit("5/minute")
async def import_csv(
    request: Request,
    file: UploadFile = File(...),
    consent_confirmed: bool = Form(...),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
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

    # Dispatch to Celery — consent_confirmed decides whether these contacts can
    # later be reached via a cold-window template reopen in campaigns, or only
    # while they have an open window (i.e. they wrote in first).
    import_contacts_csv.delay(str(current_user.id), rows, consent_confirmed)

    return {"message": f"Importando {len(rows)} contactos en segundo plano"}


@router.post("/bulk/tag", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def bulk_tag_contacts(
    request: Request,
    body: BulkTagRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    result = await db.execute(
        select(Contact).where(
            Contact.id.in_(body.contact_ids),
            Contact.advertiser_id == current_user.id,
        )
    )
    contacts = result.scalars().all()
    tags_set = set(body.tags)
    for c in contacts:
        if body.action == "add":
            existing = set(c.tags or [])
            existing.update(tags_set)
            c.tags = list(existing)
        elif body.action == "remove":
            c.tags = [t for t in (c.tags or []) if t not in tags_set]
    await db.commit()
    return {"message": f"Etiquetas actualizadas en {len(contacts)} contactos"}


@router.post("/bulk/delete", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def bulk_delete_contacts(
    request: Request,
    body: BulkDeleteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    result = await db.execute(
        select(Contact).where(
            Contact.id.in_(body.contact_ids),
            Contact.advertiser_id == current_user.id,
        )
    )
    contacts = result.scalars().all()
    for c in contacts:
        await db.delete(c)
    await db.commit()
    return {"message": f"{len(contacts)} contactos eliminados"}


@router.post("/bulk/status", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def bulk_status_contacts(
    request: Request,
    body: BulkStatusRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    result = await db.execute(
        select(Contact).where(
            Contact.id.in_(body.contact_ids),
            Contact.advertiser_id == current_user.id,
        )
    )
    contacts = result.scalars().all()
    for c in contacts:
        c.status = body.status
    await db.commit()
    return {"message": f"Estado actualizado en {len(contacts)} contactos"}


@router.post("/bulk/send-campaign", status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")
async def bulk_send_campaign(
    request: Request,
    body: BulkSendCampaignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    from app.models.campaign import Campaign
    result = await db.execute(
        select(Campaign).where(
            Campaign.id == body.campaign_id,
            Campaign.advertiser_id == current_user.id,
        )
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaña no encontrada")

    from app.workers.tasks import schedule_campaign
    campaign.segment = {
        **campaign.segment,
        "specific_contacts": body.contact_ids,
    }
    campaign.status = "scheduled"
    await db.commit()

    schedule_campaign.delay(str(campaign.id))
    return {"message": f"Campaña programada para {len(body.contact_ids)} contactos"}


@router.get("/export-csv")
async def export_contacts_csv(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
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
