"""
Laboratorio — trigger and inspect self-test runs of the bot against 6
simulated personas, judged by an independent LLM. Never touches real
WhatsApp — see app/services/lab/simulator.py for the sandbox guarantee.
"""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.database import get_db
from app.models.lab import LabRun
from app.models.user import User
from app.schemas.lab import LabRunDetailOut, LabRunOut, LabRunStarted

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lab", tags=["lab"])


@router.post("/run", response_model=LabRunStarted, status_code=202)
async def start_lab_run(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lab_run = LabRun(advertiser_id=current_user.id, status="running")
    db.add(lab_run)
    await db.commit()
    await db.refresh(lab_run)

    from app.workers.tasks import run_lab_task
    run_lab_task.apply_async(args=[str(lab_run.id)], queue="processing")

    return LabRunStarted(id=str(lab_run.id), status=lab_run.status)


@router.get("/runs", response_model=list[LabRunOut])
async def list_lab_runs(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(LabRun)
        .where(LabRun.advertiser_id == current_user.id)
        .order_by(LabRun.created_at.desc())
        .limit(min(limit, 100))
    )
    runs = result.scalars().all()
    return [
        LabRunOut(
            id=str(r.id), status=r.status, overall_score=r.overall_score,
            error_message=r.error_message, created_at=r.created_at, completed_at=r.completed_at,
        )
        for r in runs
    ]


@router.get("/runs/{run_id}", response_model=LabRunDetailOut)
async def get_lab_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Corrida no encontrada")

    result = await db.execute(
        select(LabRun)
        .options(selectinload(LabRun.conversations))
        .where(LabRun.id == run_uuid, LabRun.advertiser_id == current_user.id)
    )
    lab_run = result.scalar_one_or_none()
    if not lab_run:
        raise HTTPException(status_code=404, detail="Corrida no encontrada")

    return LabRunDetailOut(
        id=str(lab_run.id),
        status=lab_run.status,
        overall_score=lab_run.overall_score,
        error_message=lab_run.error_message,
        created_at=lab_run.created_at,
        completed_at=lab_run.completed_at,
        conversations=[
            {
                "id": str(c.id),
                "persona_key": c.persona_key,
                "persona_label": c.persona_label,
                "transcript": c.transcript,
                "score": c.score,
                "findings": c.findings,
            }
            for c in lab_run.conversations
        ],
    )
