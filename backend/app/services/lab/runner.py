"""
Orchestrates a full Laboratorio run: all 6 personas, sequentially (one
shared AsyncSession isn't safe for concurrent use), each followed by the
judge, persisting results and updating the LabRun's overall status/score.
"""
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lab import LabConversation, LabRun
from app.models.user import User
from app.services.lab.judge import evaluate_transcript
from app.services.lab.personas import PERSONAS
from app.services.lab.simulator import run_persona_conversation

logger = logging.getLogger(__name__)


async def run_lab(lab_run_id: str, db: AsyncSession) -> None:
    result = await db.execute(select(LabRun).where(LabRun.id == uuid.UUID(lab_run_id)))
    lab_run = result.scalar_one_or_none()
    if not lab_run:
        logger.warning("[LAB] run_lab called with unknown lab_run_id=%s", lab_run_id)
        return

    adv_result = await db.execute(select(User).where(User.id == lab_run.advertiser_id))
    advertiser = adv_result.scalar_one_or_none()
    if not advertiser:
        lab_run.status = "error"
        lab_run.error_message = "Anunciante no encontrado"
        lab_run.completed_at = datetime.now(timezone.utc)
        await db.commit()
        return

    try:
        scores: list[int] = []
        for persona in PERSONAS:
            transcript = await run_persona_conversation(persona, advertiser, db)
            evaluation = await evaluate_transcript(persona, transcript, advertiser, db)

            db.add(LabConversation(
                lab_run_id=lab_run.id,
                persona_key=persona.key,
                persona_label=persona.label,
                transcript=transcript,
                score=evaluation["score"],
                findings=evaluation["findings"],
            ))
            scores.append(evaluation["score"])
            await db.flush()

        lab_run.overall_score = round(sum(scores) / len(scores)) if scores else 0
        lab_run.status = "completed"
        lab_run.completed_at = datetime.now(timezone.utc)
        await db.commit()
        logger.info("[LAB] Run %s completed, overall_score=%s", lab_run_id, lab_run.overall_score)
    except Exception as e:
        logger.exception("[LAB] Run %s failed", lab_run_id)
        await db.rollback()
        # Re-fetch — the failed transaction rolled back any pending changes,
        # but the LabRun row itself was already committed as "running".
        result = await db.execute(select(LabRun).where(LabRun.id == uuid.UUID(lab_run_id)))
        lab_run = result.scalar_one_or_none()
        if lab_run:
            lab_run.status = "error"
            lab_run.error_message = str(e)[:500]
            lab_run.completed_at = datetime.now(timezone.utc)
            await db.commit()
