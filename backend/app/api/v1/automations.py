"""Automation flows — /api/v1/automations"""
import logging
from datetime import datetime, timezone, timedelta
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db
from app.models.automation import AutomationFlow, AutomationStep, AutomationEnrollment
from app.models.contact import Contact
from app.models.user import User

router = APIRouter(prefix="/automations", tags=["automations"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class StepIn(BaseModel):
    position: int = 0
    delay_minutes: int = 0
    message: str = ""
    use_ai: bool = False
    ai_prompt: str | None = None


class FlowCreate(BaseModel):
    name: str
    trigger: str = "new_contact"
    trigger_value: str | None = None
    steps: List[StepIn] = []


class StepOut(BaseModel):
    id: UUID
    position: int
    delay_minutes: int
    message: str
    use_ai: bool = False
    ai_prompt: str | None = None

    class Config:
        from_attributes = True


class FlowOut(BaseModel):
    id: UUID
    name: str
    trigger: str
    trigger_value: str | None
    is_active: bool
    created_at: datetime
    steps: List[StepOut] = []

    class Config:
        from_attributes = True


logger = logging.getLogger(__name__)

# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=List[FlowOut])
async def list_flows(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> list[FlowOut]:
    result = await db.execute(
        select(AutomationFlow)
        .options(selectinload(AutomationFlow.steps))
        .where(AutomationFlow.advertiser_id == current_user.id)
        .order_by(AutomationFlow.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return result.scalars().all()


@router.post("", response_model=FlowOut, status_code=201)
async def create_flow(
    body: FlowCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FlowOut:
    if body.trigger not in ("new_contact", "keyword", "tag_added"):
        raise HTTPException(status_code=400, detail="trigger inválido")

    flow = AutomationFlow(
        advertiser_id=current_user.id,
        name=body.name,
        trigger=body.trigger,
        trigger_value=body.trigger_value,
    )
    db.add(flow)
    await db.flush()

    for s in body.steps:
        db.add(AutomationStep(
            flow_id=flow.id,
            position=s.position,
            delay_minutes=s.delay_minutes,
            message=s.message or "",
            use_ai=s.use_ai,
            ai_prompt=s.ai_prompt,
        ))

    await db.commit()
    await db.refresh(flow)

    result = await db.execute(
        select(AutomationFlow).options(selectinload(AutomationFlow.steps)).where(AutomationFlow.id == flow.id)
    )
    return result.scalar_one()


@router.patch("/{flow_id}/toggle", response_model=FlowOut)
async def toggle_flow(
    flow_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FlowOut:
    result = await db.execute(
        select(AutomationFlow)
        .options(selectinload(AutomationFlow.steps))
        .where(AutomationFlow.id == flow_id, AutomationFlow.advertiser_id == current_user.id)
    )
    flow = result.scalar_one_or_none()
    if not flow:
        raise HTTPException(status_code=404, detail="Flujo no encontrado")
    flow.is_active = not flow.is_active
    await db.commit()
    await db.refresh(flow)
    logger.info("Flow %s toggled to %s by user %s", flow.id, flow.is_active, current_user.id)
    return flow


@router.delete("/{flow_id}", status_code=204)
async def delete_flow(
    flow_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    result = await db.execute(
        select(AutomationFlow).where(AutomationFlow.id == flow_id, AutomationFlow.advertiser_id == current_user.id)
    )
    flow = result.scalar_one_or_none()
    if not flow:
        raise HTTPException(status_code=404, detail="Flujo no encontrado")
    await db.delete(flow)
    await db.commit()


@router.post("/{flow_id}/enroll/{contact_id}", status_code=201)
async def enroll_contact(
    flow_id: UUID,
    contact_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, bool]:
    """Manually enroll a contact into a flow."""
    flow_res = await db.execute(
        select(AutomationFlow)
        .options(selectinload(AutomationFlow.steps))
        .where(AutomationFlow.id == flow_id, AutomationFlow.advertiser_id == current_user.id)
    )
    flow = flow_res.scalar_one_or_none()
    if not flow:
        raise HTTPException(status_code=404, detail="Flujo no encontrado")

    contact_res = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.advertiser_id == current_user.id)
    )
    contact = contact_res.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contacto no encontrado")

    # Avoid re-enrolling if already active
    existing = await db.execute(
        select(AutomationEnrollment).where(
            AutomationEnrollment.flow_id == flow_id,
            AutomationEnrollment.contact_id == contact_id,
            AutomationEnrollment.status == "active",
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="El contacto ya está en este flujo")

    first_step = sorted(flow.steps, key=lambda s: s.position)[0] if flow.steps else None
    next_send = datetime.now(timezone.utc) + timedelta(minutes=first_step.delay_minutes) if first_step else None

    enrollment = AutomationEnrollment(
        flow_id=flow_id,
        contact_id=contact_id,
        advertiser_id=current_user.id,
        current_step=0,
        next_send_at=next_send,
    )
    db.add(enrollment)
    await db.commit()
    return {"enrolled": True}
