"""
Celery tasks — background jobs for IaRadio.
"""
import logging
import uuid
from datetime import datetime, timezone, timedelta

from app.workers.celery_app import celery_app
from app.workers.task_helpers import (
    run_async, _get_advertiser_whatsapp_number, _extract_text,
    send_regular_messages, send_banner_messages, send_radio_messages,
    send_parrilla_messages, notify_campaign_failed,
    send_24h_reminders, send_1h_reminders,
)

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=5, default_retry_delay=120)
def send_whatsapp_message(self, message_id: str, to: str, body: str):
    """Send a WhatsApp message via Twilio with retry logic."""
    async def _send():
        from app.database import AsyncSessionLocal
        from app.models.message import Message
        from app.models.user import User
        from app.services.twilio_service import send_whatsapp
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Message).where(Message.id == uuid.UUID(message_id)))
            msg = result.scalar_one_or_none()

            from_number = None
            if msg:
                from_number = await _get_advertiser_whatsapp_number(db, msg.advertiser_id)

                adv_res = await db.execute(select(User).where(User.id == msg.advertiser_id))
                advertiser = adv_res.scalar_one_or_none()
                if not advertiser or advertiser.messages_remaining <= 0:
                    msg.status = "failed"
                    msg.error_code = "quota_exceeded"
                    msg.sent_at = None
                    await db.commit()
                    logger.warning("[QUOTA] %s — no messages remaining, message %s dropped", msg.advertiser_id, message_id)
                    return

            sid, error = await send_whatsapp(to, body, from_number=from_number)

            if msg:
                msg.status = "sent" if sid else "failed"
                msg.twilio_sid = sid
                msg.error_code = error
                msg.sent_at = datetime.now(timezone.utc) if sid else None
                if sid and advertiser:
                    advertiser.messages_remaining -= 1
                await db.commit()

            if error and any(code in str(error) for code in ("63006", "63007", "63016", "rate")):
                raise RuntimeError(f"Twilio rate limit: {error}")

    try:
        run_async(_send())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=120 * (2 ** self.request.retries))


@celery_app.task(bind=True, max_retries=5, default_retry_delay=120)
def send_whatsapp_voice_note(self, message_id: str, to: str, audio_url: str, caption: str = ""):
    """Send a WhatsApp voice note (audio cuña) via Twilio media message."""
    async def _send():
        from app.database import AsyncSessionLocal
        from app.models.message import Message
        from app.models.user import User
        from app.services.twilio_service import send_whatsapp_media
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Message).where(Message.id == uuid.UUID(message_id)))
            msg = result.scalar_one_or_none()

            from_number = None
            advertiser = None
            if msg:
                from_number = await _get_advertiser_whatsapp_number(db, msg.advertiser_id)
                adv_res = await db.execute(select(User).where(User.id == msg.advertiser_id))
                advertiser = adv_res.scalar_one_or_none()
                if not advertiser or advertiser.messages_remaining <= 0:
                    msg.status = "failed"
                    msg.error_code = "quota_exceeded"
                    msg.sent_at = None
                    await db.commit()
                    logger.warning("[QUOTA] %s — no messages remaining, voice note %s dropped", msg.advertiser_id, message_id)
                    return

            sid, error = await send_whatsapp_media(to, audio_url, body=caption, from_number=from_number)

            if msg:
                msg.status = "sent" if sid else "failed"
                msg.twilio_sid = sid
                msg.error_code = error
                msg.sent_at = datetime.now(timezone.utc) if sid else None
                if sid and advertiser:
                    advertiser.messages_remaining -= 1
                await db.commit()

            if error and any(code in str(error) for code in ("63006", "63007", "63016", "rate")):
                raise RuntimeError(f"Twilio rate limit: {error}")

    try:
        run_async(_send())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=120 * (2 ** self.request.retries))


@celery_app.task(bind=True, max_retries=2)
def send_welcome_cuna(self, advertiser_id: str, to: str, business_name: str, from_number: str | None = None):
    """Generate a radio cuña and send it as a WhatsApp voice note to a new lead."""
    async def _run():
        from app.services.radio_service import generate_radio_ad
        from app.config import settings
        from app.services.twilio_service import send_whatsapp_media

        r2_url = await generate_radio_ad(
            business_name=business_name,
            message_or_intent=f"Bienvenido a {business_name}. Descubre nuestras ofertas.",
            country="mx",
            mode="classic",
        )
        if not r2_url:
            return

        key = r2_url.split("/radio/", 1)[-1]
        audio_url = f"{settings.BASE_URL.rstrip('/')}/api/v1/radio/audio/{key}"
        await send_whatsapp_media(to, audio_url, body="", from_number=from_number)

    try:
        run_async(_run())
    except Exception:
        logger.warning("[WELCOME-CUÑA] Failed to send welcome cuña for contact", exc_info=True)


@celery_app.task
def auto_tag_contact_from_conversation(contact_id: str):
    """Use Claude Haiku to detect intent from last 10 messages and add auto-tags."""
    async def _run():
        from app.database import AsyncSessionLocal
        from app.models.contact import Contact
        from app.models.message import Message
        from app.services.claude_service import detect_intent_tags
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            c_uuid = uuid.UUID(contact_id)
            msg_result = await db.execute(
                select(Message).where(Message.contact_id == c_uuid)
                .order_by(Message.created_at.desc()).limit(10)
            )
            messages = list(msg_result.scalars().all())
            messages.reverse()
            if not messages:
                return

            conv_text = "\n".join(
                f"{'cliente' if m.direction == 'inbound' else 'bot'}: {m.content}"
                for m in messages
            )
            new_tags = await detect_intent_tags(conv_text)
            if not new_tags:
                return

            contact_res = await db.execute(select(Contact).where(Contact.id == c_uuid))
            contact = contact_res.scalar_one_or_none()
            if not contact:
                return

            existing = set(contact.tags or [])
            contact.tags = list(existing | set(new_tags))
            await db.commit()
            logger.info("[AUTO-TAG] Contact %s tagged: %s", contact_id, new_tags)

    try:
        run_async(_run())
    except Exception:
        logger.warning("[AUTO-TAG] Failed to auto-tag contact %s", contact_id, exc_info=True)


@celery_app.task(bind=True, max_retries=2)
def schedule_campaign(self, campaign_id: str):
    """Process and send all messages for a scheduled campaign."""
    async def _process():
        from app.database import AsyncSessionLocal
        from app.models.campaign import Campaign
        from app.models.contact import Contact
        from app.models.user import User
        from app.services.twilio_service import is_human_hour
        from sqlalchemy import select

        if not is_human_hour(timezone_offset=-6):
            now_utc = datetime.now(timezone.utc)
            next_8am = now_utc.replace(hour=14, minute=0, second=0, microsecond=0)
            if now_utc.hour >= 14:
                next_8am += timedelta(days=1)
            delay_secs = int((next_8am - now_utc).total_seconds())
            logger.info("[CAMPAIGN] Outside human hours — rescheduling in %ds", delay_secs)
            schedule_campaign.apply_async(args=[campaign_id], countdown=delay_secs, queue="whatsapp")
            return

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Campaign).where(Campaign.id == uuid.UUID(campaign_id)))
            campaign = result.scalar_one_or_none()
            if not campaign or campaign.status not in ("scheduled", "running"):
                return

            adv_result = await db.execute(select(User).where(User.id == campaign.advertiser_id))
            advertiser = adv_result.scalar_one_or_none()
            if not advertiser or advertiser.messages_remaining <= 0:
                campaign.status = "paused"
                await db.commit()
                return

            ab = campaign.ab_test or {}
            mode = ab.get("campaign_mode", "regular")
            messages_list: list[str] = ab.get("messages", [campaign.message_text])

            q = select(Contact).where(
                Contact.advertiser_id == campaign.advertiser_id,
                Contact.status == "active",
            )
            segment_tags = campaign.segment.get("tags", [])
            if segment_tags:
                q = q.where(Contact.tags.overlap(segment_tags))

            contacts_result = await db.execute(q)
            contacts = contacts_result.scalars().all()

            campaign.status = "running"
            await db.commit()

            if mode == "banner":
                await send_banner_messages(db, campaign, contacts, advertiser, ab, ban_delay=0)
            elif mode in ("radio", "comunitaria"):
                audio_url = ab.get("audio_url", "")
                if not audio_url:
                    campaign.status = "paused"
                    await db.commit()
                    return
                await send_radio_messages(db, campaign, contacts, advertiser, ab, ban_delay=0)
            else:
                await send_regular_messages(db, campaign, contacts, advertiser, ab, messages_list, ban_delay=0)

    try:
        run_async(_process())
    except Exception as exc:
        from app.workers.task_helpers.campaign_ops import notify_campaign_failed
        run_async(notify_campaign_failed(campaign_id, exc))
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=2)
def process_knowledge_base_file(self, kb_id: str, file_content: bytes, file_type: str):
    """Extract text, chunk, generate embeddings and store in pgvector."""
    async def _process():
        from app.database import AsyncSessionLocal
        from app.models.knowledge_base import KnowledgeBase
        from app.services.embedding_service import get_embedding, chunk_text
        from app.config import settings
        from sqlalchemy import select

        embed_delay: float = 0.0 if settings.OPENAI_API_KEY else getattr(settings, "VOYAGE_EMBEDDING_DELAY_S", 22.0)

        text = _extract_text(file_content, file_type)
        if not text:
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == uuid.UUID(kb_id)))
                kb = result.scalar_one_or_none()
                if kb:
                    kb.processing_status = "error"
                    await db.commit()
            return

        chunks = chunk_text(text, chunk_size=500, overlap=50)
        total_chunks = len(chunks)
        logger.info("[KB %s] Procesando %d chunks (delay=%.1fs)", kb_id, total_chunks, embed_delay)

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == uuid.UUID(kb_id)))
            original = result.scalar_one_or_none()
            if not original:
                return

            original.raw_text = text
            original.chunk_text = chunks[0] if chunks else text

            for i, chunk in enumerate(chunks[1:], 1):
                logger.info("[KB %s] Chunk %d/%d", kb_id, i, total_chunks - 1)
                if embed_delay > 0:
                    import asyncio as _asyncio
                    await _asyncio.sleep(embed_delay)
                embedding = await get_embedding(chunk)
                kb_chunk = KnowledgeBase(
                    advertiser_id=original.advertiser_id,
                    filename=f"{original.filename}#chunk{i}",
                    file_type=file_type, chunk_text=chunk,
                    embedding=embedding, version=original.version,
                )
                db.add(kb_chunk)

            if chunks:
                original.embedding = await get_embedding(chunks[0])
            original.processing_status = "done"
            await db.commit()
            logger.info("[KB %s] Procesamiento completado (%d chunks)", kb_id, total_chunks)

    try:
        run_async(_process())
    except Exception as exc:
        async def _mark_error():
            from app.database import AsyncSessionLocal
            from app.models.knowledge_base import KnowledgeBase
            from sqlalchemy import select
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == uuid.UUID(kb_id)))
                kb = result.scalar_one_or_none()
                if kb:
                    kb.processing_status = "error"
                    await db.commit()
        try:
            run_async(_mark_error())
        except Exception:
            logger.warning("[KB] Failed to mark error", exc_info=True)
        raise self.retry(exc=exc)


@celery_app.task
def import_contacts_csv(advertiser_id: str, rows: list[dict]):
    """Bulk import contacts from CSV rows."""
    async def _import():
        import re
        from app.database import AsyncSessionLocal
        from app.models.contact import Contact
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            for row in rows:
                phone = str(row.get("phone", row.get("telefono", ""))).strip()
                name = str(row.get("name", row.get("nombre", ""))).strip()
                if not phone or not re.match(r"^\+\d{7,15}$", phone):
                    continue
                existing = await db.execute(
                    select(Contact).where(
                        Contact.advertiser_id == uuid.UUID(advertiser_id),
                        Contact.phone == phone,
                    )
                )
                if existing.scalar_one_or_none():
                    continue
                contact = Contact(
                    advertiser_id=uuid.UUID(advertiser_id),
                    name=name or phone, phone=phone,
                    email=str(row.get("email", "")).strip() or None,
                    city=str(row.get("city", row.get("ciudad", ""))).strip() or None,
                    source="csv",
                )
                db.add(contact)
            await db.commit()

    run_async(_import())


@celery_app.task
def check_scheduled_campaigns():
    """Celery Beat: trigger campaigns scheduled for now."""
    async def _check():
        from app.database import AsyncSessionLocal
        from app.models.campaign import Campaign
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            now = datetime.now(timezone.utc)
            result = await db.execute(select(Campaign).where(Campaign.status == "scheduled"))
            for campaign in result.scalars().all():
                start_date = campaign.schedule.get("start_date")
                if start_date:
                    try:
                        if datetime.fromisoformat(start_date) <= now:
                            schedule_campaign.delay(str(campaign.id))
                    except ValueError:
                        logger.warning("[CAMPAIGN] Invalid date for campaign %s", campaign.id)

    run_async(_check())


@celery_app.task
def cleanup_expired_data():
    """Remove messages older than 12 months and expired subscriptions."""
    async def _cleanup():
        from app.database import AsyncSessionLocal
        from app.models.message import Message
        from app.models.user import User
        from sqlalchemy import delete, update

        cutoff = datetime.now(timezone.utc) - timedelta(days=365)
        now = datetime.now(timezone.utc)

        async with AsyncSessionLocal() as db:
            await db.execute(delete(Message).where(Message.created_at < cutoff))
            await db.execute(
                update(User).where(
                    User.plan_expires_at != None, User.plan_expires_at < now,
                    User.subscription_status == "active",
                ).values(subscription_status="churned", messages_remaining=0)
            )
            await db.commit()

    run_async(_cleanup())


@celery_app.task
def send_trial_expiry_reminders():
    """Celery Beat: send reminders to expiring users."""
    async def _remind():
        from app.database import AsyncSessionLocal
        from app.models.user import User
        from app.core.email import send_trial_expiring_email
        from app.services.twilio_service import send_whatsapp
        from sqlalchemy import select

        now = datetime.now(timezone.utc)
        for days_left in (1, 3):
            window_start = now + timedelta(days=days_left)
            result = await db.execute(
                select(User).where(
                    User.subscription_status.in_(["trial", "active"]),
                    User.plan_expires_at >= window_start,
                    User.plan_expires_at < window_start + timedelta(hours=2),
                )
            )
            for user in result.scalars().all():
                biz_name = user.business_name or user.email
                try:
                    await send_trial_expiring_email(to=user.email, business_name=biz_name, days_left=days_left)
                    logger.info("[TRIAL REMINDER] Email sent to %s — %d day(s) left", user.email, days_left)
                except Exception as e:
                    logger.error("[TRIAL REMINDER] Email failed for %s: %s", user.email, e)

                if user.whatsapp_number:
                    try:
                        msg = (
                            f"⏰ Hola {biz_name}, tu prueba gratuita termina en {days_left} día{'s' if days_left != 1 else ''}. "
                            f"👉 https://app.iaradio.app/app/plans"
                        )
                        send_whatsapp(to=user.whatsapp_number, body=msg)
                    except Exception as e:
                        logger.error("[TRIAL REMINDER] WhatsApp failed for %s: %s", user.email, e)

    run_async(_remind())


@celery_app.task
def send_appointment_reminders():
    """Celery Beat: send WhatsApp reminders for upcoming appointments."""
    async def _remind():
        from app.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            now = datetime.now(timezone.utc)
            await send_24h_reminders(db, now)
            await send_1h_reminders(db, now)
            await db.commit()

    run_async(_remind())


@celery_app.task(bind=True, max_retries=2)
def send_parrilla_day(self, advertiser_id: str, audio_url: str, script: str, day_name: str, mode: str):
    """Sends the daily cuña from the weekly parrilla to all active contacts."""
    async def _send():
        from app.database import AsyncSessionLocal
        from app.models.contact import Contact
        from app.models.user import User
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            adv_result = await db.execute(select(User).where(User.id == uuid.UUID(advertiser_id)))
            advertiser = adv_result.scalar_one_or_none()
            if not advertiser or advertiser.messages_remaining <= 0:
                logger.warning("[PARRILLA] %s — sin mensajes", advertiser_id)
                return

            contacts_result = await db.execute(
                select(Contact).where(
                    Contact.advertiser_id == uuid.UUID(advertiser_id), Contact.status == "active",
                )
            )
            contacts = contacts_result.scalars().all()
            sent = await send_parrilla_messages(db, advertiser, contacts, audio_url, script, day_name, mode)
            await db.commit()
            logger.info("[PARRILLA] %s — %s enviado a %d contactos", day_name, mode, sent)

    try:
        run_async(_send())
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task
def update_contact_engagement_score(contact_id: str):
    """Update contact engagement_score and lead_score using Claude."""
    async def _update():
        import json
        from app.database import AsyncSessionLocal
        from app.models.contact import Contact
        from app.models.conversation import Conversation
        from app.models.message import Message
        from app.services.claude_service import _get_client
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            c_uuid = uuid.UUID(contact_id)
            result = await db.execute(select(Contact).where(Contact.id == c_uuid))
            contact = result.scalar_one_or_none()
            if not contact:
                return

            msg_result = await db.execute(
                select(Message).where(Message.contact_id == c_uuid)
                .order_by(Message.created_at.desc()).limit(20)
            )
            messages = list(msg_result.scalars().all())
            messages.reverse()
            if not messages:
                return

            chat_str = "\n".join(
                f"{'usuario' if m.direction == 'inbound' else 'asistente'}: {m.content}"
                for m in messages
            )

            system_prompt = (
                "Eres un analista de ventas. Califica el interés del cliente en escala 0-100.\n"
                "Responde SOLO con JSON: {\"score\": 85, \"summary\": \"...\"}\n"
                "0-30: sin interés, 31-60: frío, 61-85: alto interés, 86-100: listo para comprar."
            )

            client = _get_client()
            try:
                response = await client.messages.create(
                    model="claude-sonnet-4-6", max_tokens=150, temperature=0.0,
                    system=system_prompt,
                    messages=[{"role": "user", "content": f"Conversación:\n{chat_str}"}],
                )
                raw_text = response.content[0].text.strip()

                if raw_text.startswith("```json"):
                    raw_text = raw_text.replace("```json", "").replace("```", "").strip()
                elif raw_text.startswith("```"):
                    raw_text = raw_text.replace("```", "").strip()

                data = json.loads(raw_text)
                score = max(0, min(100, int(data.get("score", 0))))

                contact.engagement_score = score
                summary = data.get("summary", "")
                if summary:
                    contact.notes = f"Interés: {summary} (IA)"

                lead_score = "hot" if score >= 80 else "warm" if score >= 40 else "cold"
                conv_result = await db.execute(
                    select(Conversation).where(
                        Conversation.contact_id == c_uuid, Conversation.status == "active"
                    )
                )
                conv = conv_result.scalar_one_or_none()
                if conv:
                    conv.lead_score = lead_score

                await db.commit()
                logger.info("Updated contact %s score to %d (%s)", contact_id, score, lead_score)

            except Exception as e:
                logger.error("Error scoring contact %s: %s", contact_id, str(e))

    try:
        run_async(_update())
    except Exception as exc:
        logger.error("Error in update_contact_engagement_score: %s", str(exc))


@celery_app.task
def process_automation_enrollments():
    """Celery beat — send next drip message to all due enrollments."""
    async def _run():
        from app.database import AsyncSessionLocal
        from app.models.automation import AutomationEnrollment, AutomationFlow
        from app.models.contact import Contact
        from app.models.conversation import Conversation
        from app.models.message import Message
        from app.models.user import User
        from app.services.twilio_service import send_whatsapp
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        now = datetime.now(timezone.utc)

        async with AsyncSessionLocal() as db:
            enrollments = (await db.execute(
                select(AutomationEnrollment).where(
                    AutomationEnrollment.status == "active",
                    AutomationEnrollment.next_send_at <= now,
                )
            )).scalars().all()

            for enrollment in enrollments:
                flow = (await db.execute(
                    select(AutomationFlow).options(selectinload(AutomationFlow.steps))
                    .where(AutomationFlow.id == enrollment.flow_id)
                )).scalar_one_or_none()

                if not flow or not flow.is_active:
                    enrollment.status = "cancelled"
                    continue

                steps = sorted(flow.steps, key=lambda s: s.position)
                if enrollment.current_step >= len(steps):
                    enrollment.status = "completed"
                    continue

                step = steps[enrollment.current_step]
                contact = (await db.execute(
                    select(Contact).where(Contact.id == enrollment.contact_id)
                )).scalar_one_or_none()

                if not contact or contact.status != "active":
                    enrollment.status = "cancelled"
                    continue

                advertiser = (await db.execute(
                    select(User).where(User.id == enrollment.advertiser_id)
                )).scalar_one_or_none()

                if not advertiser or advertiser.messages_remaining <= 0:
                    enrollment.status = "cancelled"
                    continue

                # Generate message content
                if step.use_ai and step.ai_prompt:
                    from app.services.rag_service import answer_with_rag

                    conv_result = await db.execute(
                        select(Conversation).where(
                            Conversation.advertiser_id == enrollment.advertiser_id,
                            Conversation.contact_id == contact.id,
                            Conversation.status == "active",
                        )
                    )
                    conv = conv_result.scalar_one_or_none()
                    history = conv.messages[-40:] if conv and conv.messages else []

                    message_content = await answer_with_rag(
                        advertiser_id=str(enrollment.advertiser_id),
                        query=step.ai_prompt,
                        conversation_history=history,
                        db=db,
                        business_name=advertiser.business_name or "el negocio",
                        bot_name=advertiser.bot_name or "Asistente",
                        bot_personality=advertiser.bot_personality or "amigable y profesional",
                    )
                else:
                    message_content = step.message

                from_number = advertiser.whatsapp_number
                sid, error = await send_whatsapp(contact.phone, message_content, from_number=from_number)

                if sid:
                    advertiser.messages_remaining -= 1

                db.add(Message(
                    advertiser_id=enrollment.advertiser_id, contact_id=contact.id,
                    direction="outbound", content=message_content,
                    status="sent" if sid else "failed",
                    twilio_sid=sid, error_code=error, sent_at=now if sid else None,
                ))

                enrollment.current_step += 1
                if enrollment.current_step >= len(steps):
                    enrollment.status = "completed"
                    enrollment.next_send_at = None
                else:
                    enrollment.next_send_at = now + timedelta(minutes=steps[enrollment.current_step].delay_minutes)

            await db.commit()

    run_async(_run())


@celery_app.task
def trigger_automation_for_contact(contact_id: str, advertiser_id: str, trigger: str, trigger_value: str = ""):
    """Enroll a contact in all matching active flows."""
    async def _run():
        from app.database import AsyncSessionLocal
        from app.models.automation import AutomationFlow, AutomationEnrollment
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        async with AsyncSessionLocal() as db:
            flows = (await db.execute(
                select(AutomationFlow).options(selectinload(AutomationFlow.steps))
                .where(
                    AutomationFlow.advertiser_id == uuid.UUID(advertiser_id),
                    AutomationFlow.trigger == trigger,
                    AutomationFlow.is_active == True,
                )
            )).scalars().all()

            for flow in flows:
                if trigger == "keyword" and flow.trigger_value:
                    if flow.trigger_value.lower() not in trigger_value.lower():
                        continue

                already = await db.execute(
                    select(AutomationEnrollment).where(
                        AutomationEnrollment.flow_id == flow.id,
                        AutomationEnrollment.contact_id == uuid.UUID(contact_id),
                        AutomationEnrollment.status == "active",
                    )
                )
                if already.scalar_one_or_none():
                    continue

                steps = sorted(flow.steps, key=lambda s: s.position)
                first = steps[0] if steps else None
                next_send = now + timedelta(minutes=first.delay_minutes) if first else None

                db.add(AutomationEnrollment(
                    flow_id=flow.id, contact_id=uuid.UUID(contact_id),
                    advertiser_id=uuid.UUID(advertiser_id),
                    current_step=0, next_send_at=next_send,
                ))

            await db.commit()

    now = datetime.now(timezone.utc)
    run_async(_run())
