"""
Celery tasks — background jobs for IaRadio.
"""
import asyncio
import logging
import random
import re
import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from app.workers.celery_app import celery_app


def run_async(coro):
    """Helper to run async code in sync Celery task."""
    return asyncio.run(coro)


async def _get_advertiser_whatsapp_number(db: AsyncSession, advertiser_id: uuid.UUID) -> str | None:
    from app.models.user import User
    from sqlalchemy import select
    result = await db.execute(select(User).where(User.id == advertiser_id))
    advertiser = result.scalar_one_or_none()
    return advertiser.whatsapp_number if advertiser else None


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def send_whatsapp_message(self, message_id: str, to: str, body: str):
    """Send a WhatsApp message via Twilio with retry logic."""
    async def _send():
        from app.database import AsyncSessionLocal
        from app.models.message import Message
        from app.services.twilio_service import send_whatsapp
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Message).where(Message.id == uuid.UUID(message_id)))
            msg = result.scalar_one_or_none()

            from_number = None
            if msg:
                from_number = await _get_advertiser_whatsapp_number(db, msg.advertiser_id)

            sid = await send_whatsapp(to, body, from_number=from_number)

            if msg:
                msg.status = "sent" if sid else "failed"
                msg.twilio_sid = sid
                msg.sent_at = datetime.now(timezone.utc)
                await db.commit()

    try:
        run_async(_send())
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def send_whatsapp_voice_note(self, message_id: str, to: str, audio_url: str, caption: str = ""):
    """Send a WhatsApp voice note (audio cuña) via Twilio media message."""
    async def _send():
        from app.database import AsyncSessionLocal
        from app.models.message import Message
        from app.services.twilio_service import send_whatsapp_media
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Message).where(Message.id == uuid.UUID(message_id)))
            msg = result.scalar_one_or_none()

            from_number = None
            if msg:
                from_number = await _get_advertiser_whatsapp_number(db, msg.advertiser_id)

            sid = await send_whatsapp_media(to, audio_url, body=caption, from_number=from_number)

            if msg:
                msg.status = "sent" if sid else "failed"
                msg.twilio_sid = sid
                msg.sent_at = datetime.now(timezone.utc)
                await db.commit()

    try:
        run_async(_send())
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=2)
def send_welcome_cuna(self, advertiser_id: str, to: str, business_name: str, from_number: str | None = None):
    """Generate a radio cuña and send it as a WhatsApp voice note to a new lead.

    Triggered automatically on first contact — no keyword required.
    """
    async def _run():
        from app.services.radio_service import generate_radio_ad
        from app.config import settings
        from app.services.twilio_service import send_whatsapp_media

        # Generate the cuña audio and upload to R2
        r2_url = await generate_radio_ad(
            business_name=business_name,
            message_or_intent=f"Bienvenido a {business_name}. Descubre nuestras ofertas.",
            country="mx",
            mode="classic",
        )
        if not r2_url:
            return

        # Build a publicly-accessible proxy URL through this backend
        # Extract the R2 object key from the full URL (everything after /radio/)
        key = r2_url.split("/radio/", 1)[-1]
        audio_url = f"{settings.BASE_URL.rstrip('/')}/api/v1/radio/audio/{key}"

        await send_whatsapp_media(
            to,
            audio_url,
            body="",
            from_number=from_number,
        )

    try:
        run_async(_run())
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=2)
def schedule_campaign(self, campaign_id: str):
    """Process and send all messages for a scheduled campaign.

    Supports 4 campaign types via campaign.ab_test['campaign_mode']:
      - 'regular'  : single personalized message (default)
      - 'sequence' : 3 messages sent on days 1, 3, 5
      - 'saga'     : 4 episodic messages sent weekly
      - 'radio'    : pre-generated audio cuña sent as WhatsApp voice note
    """
    async def _process():
        from app.database import AsyncSessionLocal
        from app.models.campaign import Campaign
        from app.models.contact import Contact
        from app.models.coupon import Coupon
        from app.models.message import Message
        from app.models.user import User
        from app.services.twilio_service import anti_ban_delay, send_whatsapp_media
        from app.services.claude_service import personalize_message
        from app.services.coupon_service import (
            generate_coupon_code, format_coupon_in_message, default_expiry
        )
        from sqlalchemy import select

        SECONDS_PER_DAY = 86_400

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Campaign).where(Campaign.id == uuid.UUID(campaign_id))
            )
            campaign = result.scalar_one_or_none()
            if not campaign or campaign.status not in ("scheduled", "running"):
                return

            adv_result = await db.execute(
                select(User).where(User.id == campaign.advertiser_id)
            )
            advertiser = adv_result.scalar_one_or_none()
            if not advertiser or advertiser.messages_remaining <= 0:
                campaign.status = "paused"
                await db.commit()
                return

            # Determine campaign mode and messages list
            ab = campaign.ab_test or {}
            mode = ab.get("campaign_mode", "regular")
            messages_list: list[str] = ab.get("messages", [campaign.message_text])
            has_coupon: bool = ab.get("has_coupon", False)
            coupon_description: str = ab.get("coupon_description", "")
            coupon_hours: int = ab.get("coupon_hours", 72)

            # Interval between messages in days
            interval_days = ab.get("interval_days", 2 if mode == "sequence" else 7)
            interval_seconds = interval_days * SECONDS_PER_DAY

            # Get contacts by segment
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

            advertiser_data = {
                "business_name": advertiser.business_name,
                "city": advertiser.city,
            }

            ban_delay = 0  # accumulates anti-ban spacing between contacts

            # ── Radio / Comunitaria mode: send pre-generated audio cuña ─────────
            if mode in ("radio", "comunitaria"):
                audio_url = ab.get("audio_url", "")
                radio_script = ab.get("radio_script", campaign.message_text)
                if not audio_url:
                    campaign.status = "paused"
                    await db.commit()
                    return

                for contact in contacts:
                    if advertiser.messages_remaining <= 0:
                        break

                    msg = Message(
                        campaign_id=campaign.id,
                        contact_id=contact.id,
                        advertiser_id=campaign.advertiser_id,
                        direction="outbound",
                        content=f"[AUDIO] {audio_url}",
                        status="queued",
                        scheduled_for=datetime.now(timezone.utc),
                    )
                    db.add(msg)
                    await db.flush()

                    send_whatsapp_voice_note.apply_async(
                        args=[str(msg.id), contact.phone, audio_url, radio_script],
                        countdown=ban_delay,
                        queue="whatsapp",
                    )
                    advertiser.messages_remaining -= 1
                    ban_delay += anti_ban_delay()

                await db.commit()
                return
            # ─────────────────────────────────────────────────────────────────

            for contact in contacts:
                if advertiser.messages_remaining <= 0:
                    break

                contact_data = {
                    "name": contact.name,
                    "city": getattr(contact, "city", None),
                }

                # Select one random message variant per contact (anti-spam)
                raw_template = random.choice(messages_list) if messages_list else campaign.message_text

                # Personalize message
                body = personalize_message(raw_template, contact_data, advertiser_data)

                # Attach coupon to message (only if has_coupon enabled)
                if has_coupon:
                    code = generate_coupon_code()
                    expires_at = default_expiry(hours=coupon_hours)
                    coupon = Coupon(
                        advertiser_id=campaign.advertiser_id,
                        campaign_id=campaign.id,
                        contact_id=contact.id,
                        code=code,
                        description=coupon_description or None,
                        expires_at=expires_at,
                    )
                    db.add(coupon)
                    await db.flush()
                    body = format_coupon_in_message(body, code, expires_at, coupon_description)

                msg = Message(
                    campaign_id=campaign.id,
                    contact_id=contact.id,
                    advertiser_id=campaign.advertiser_id,
                    direction="outbound",
                    content=body,
                    status="queued",
                    scheduled_for=datetime.now(timezone.utc),
                )
                db.add(msg)
                await db.flush()

                send_whatsapp_message.apply_async(
                    args=[str(msg.id), contact.phone, body],
                    countdown=ban_delay,
                    queue="whatsapp",
                )
                advertiser.messages_remaining -= 1
                ban_delay += anti_ban_delay()

            await db.commit()

    try:
        run_async(_process())
    except Exception as exc:
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

        # Delay entre llamadas al API de embeddings (seg).
        # Free tier de Voyage AI admite ~3 RPM → 22 s entre llamadas.
        # Con un plan de pago baja a 0-1 s. Configura VOYAGE_EMBEDDING_DELAY_S en .env.
        embed_delay: float = getattr(settings, "VOYAGE_EMBEDDING_DELAY_S", 22.0)

        # Extract text based on file type
        text = _extract_text(file_content, file_type)
        if not text:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(KnowledgeBase).where(KnowledgeBase.id == uuid.UUID(kb_id))
                )
                kb = result.scalar_one_or_none()
                if kb:
                    kb.processing_status = "error"
                    await db.commit()
            return

        chunks = chunk_text(text, chunk_size=500, overlap=50)
        total_chunks = len(chunks)
        logger.info("[KB %s] Procesando %d chunks (delay=%.1fs entre embeddings)", kb_id, total_chunks, embed_delay)

        async with AsyncSessionLocal() as db:
            # Update original record with raw text
            result = await db.execute(
                select(KnowledgeBase).where(KnowledgeBase.id == uuid.UUID(kb_id))
            )
            original = result.scalar_one_or_none()
            if not original:
                return

            original.raw_text = text
            original.chunk_text = chunks[0] if chunks else text

            # Create additional records for each chunk
            for i, chunk in enumerate(chunks[1:], 1):
                logger.info("[KB %s] Chunk %d/%d — esperando %.1fs", kb_id, i, total_chunks - 1, embed_delay)
                if embed_delay > 0:
                    await asyncio.sleep(embed_delay)
                embedding = await get_embedding(chunk)
                kb_chunk = KnowledgeBase(
                    advertiser_id=original.advertiser_id,
                    filename=f"{original.filename}#chunk{i}",
                    file_type=file_type,
                    chunk_text=chunk,
                    embedding=embedding,
                    version=original.version,
                )
                db.add(kb_chunk)

            # Embed first chunk too
            if chunks:
                original.embedding = await get_embedding(chunks[0])

            original.processing_status = "done"
            await db.commit()
            logger.info("[KB %s] Procesamiento completado (%d chunks)", kb_id, total_chunks)

    try:
        run_async(_process())
    except Exception as exc:
        # Mark as error in DB before retrying
        async def _mark_error():
            from app.database import AsyncSessionLocal
            from app.models.knowledge_base import KnowledgeBase
            from sqlalchemy import select
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(KnowledgeBase).where(KnowledgeBase.id == uuid.UUID(kb_id))
                )
                kb = result.scalar_one_or_none()
                if kb:
                    kb.processing_status = "error"
                    await db.commit()
        try:
            run_async(_mark_error())
        except Exception:
            pass
        raise self.retry(exc=exc)


logger = logging.getLogger(__name__)


def _extract_text(content: bytes, file_type: str) -> str:
    """Extract text from file content in a sandboxed manner."""
    try:
        if file_type == "pdf":
            import fitz  # PyMuPDF
            doc = fitz.open(stream=content, filetype="pdf")
            return "\n".join(page.get_text() for page in doc)
        elif file_type == "docx":
            import io
            from docx import Document
            doc = Document(io.BytesIO(content))
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        elif file_type == "xlsx":
            import io
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True)
            texts = []
            for ws in wb.worksheets:
                for row in ws.iter_rows(values_only=True):
                    texts.append(" ".join(str(c) for c in row if c is not None))
            return "\n".join(texts)
        elif file_type == "txt":
            return content.decode("utf-8", errors="ignore")
        elif file_type == "audio":
            from app.config import settings
            if not settings.OPENAI_API_KEY:
                logger.warning("OPENAI_API_KEY not set — skipping Whisper transcription")
                return ""
            import io
            from openai import OpenAI
            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            audio_file = io.BytesIO(content)
            audio_file.name = "audio.mp3"
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="es",
            )
            return transcript.text
        else:
            return ""
    except Exception as e:
        logger.error("[EXTRACT ERROR] file_type=%s error=%s", file_type, e)
        return ""


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

                # Skip duplicates
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
                    name=name or phone,
                    phone=phone,
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
        from sqlalchemy import select, cast, DateTime
        from sqlalchemy.dialects.postgresql import JSONB

        async with AsyncSessionLocal() as db:
            now = datetime.now(timezone.utc)
            result = await db.execute(
                select(Campaign).where(
                    Campaign.status == "scheduled",
                )
            )
            campaigns = result.scalars().all()
            for campaign in campaigns:
                start_date = campaign.schedule.get("start_date")
                if start_date:
                    try:
                        scheduled_dt = datetime.fromisoformat(start_date)
                        if scheduled_dt <= now:
                            schedule_campaign.delay(str(campaign.id))
                    except ValueError:
                        pass

    run_async(_check())


@celery_app.task
def cleanup_expired_data():
    """Remove messages older than 12 months and expired plan subscriptions."""
    async def _cleanup():
        from datetime import datetime, timezone, timedelta
        from app.database import AsyncSessionLocal
        from app.models.message import Message
        from app.models.user import User
        from sqlalchemy import delete, update

        cutoff = datetime.now(timezone.utc) - timedelta(days=365)
        now = datetime.now(timezone.utc)

        async with AsyncSessionLocal() as db:
            # Delete messages older than 12 months
            await db.execute(
                delete(Message).where(Message.created_at < cutoff)
            )

            # Mark users whose plan has expired as churned
            await db.execute(
                update(User)
                .where(
                    User.plan_expires_at != None,  # noqa: E711
                    User.plan_expires_at < now,
                    User.subscription_status == "active",
                )
                .values(subscription_status="churned", messages_remaining=0)
            )

            await db.commit()

    run_async(_cleanup())


@celery_app.task
def send_appointment_reminders():
    """Celery Beat: send WhatsApp reminders for upcoming appointments.

    Runs every 5 minutes. Sends:
      - 24h reminder (once, when appointment is 23-25h away)
      - 1h reminder (once, when appointment is 50-70 min away)
    """
    async def _remind():
        from datetime import timedelta
        from app.database import AsyncSessionLocal
        from app.models.appointment import Appointment
        from app.models.user import User
        from app.models.contact import Contact
        from app.services.twilio_service import send_whatsapp
        from sqlalchemy import select, and_

        now = datetime.now(timezone.utc)

        async with AsyncSessionLocal() as db:
            # ── 24h reminders ────────────────────────────────────────────
            window_24h_start = now + timedelta(hours=23)
            window_24h_end = now + timedelta(hours=25)

            result = await db.execute(
                select(Appointment).where(
                    Appointment.reminder_24h_sent == False,  # noqa: E712
                    Appointment.status.in_(["pending", "confirmed"]),
                    Appointment.scheduled_at >= window_24h_start,
                    Appointment.scheduled_at <= window_24h_end,
                )
            )
            for appt in result.scalars().all():
                # Get advertiser's WhatsApp number
                user_result = await db.execute(select(User).where(User.id == appt.advertiser_id))
                advertiser = user_result.scalar_one_or_none()
                from_number = advertiser.whatsapp_number if advertiser else None

                phone = appt.customer_phone
                if not phone and appt.contact_id:
                    c_result = await db.execute(select(Contact).where(Contact.id == appt.contact_id))
                    contact = c_result.scalar_one_or_none()
                    if contact:
                        phone = contact.phone

                if phone:
                    hora = appt.scheduled_at.strftime("%I:%M %p").lstrip("0")
                    fecha = appt.scheduled_at.strftime("%A %d de %B")
                    biz_name = advertiser.business_name if advertiser else "tu cita"
                    msg = (
                        f"📅 *Recordatorio de cita*\n\n"
                        f"Hola {appt.customer_name.split()[0]} 👋, tienes cita mañana:\n"
                        f"📌 *{appt.service}*\n"
                        f"🕐 {fecha} a las {hora}\n"
                        f"🏪 {biz_name}\n\n"
                        f"¿Puedes confirmar tu asistencia?\n"
                        f"Responde *1* para confirmar ✅\n"
                        f"Responde *2* para cancelar ❌"
                    )
                    await send_whatsapp(phone, msg, from_number=from_number)
                    appt.awaiting_confirmation = True

                appt.reminder_24h_sent = True

            # ── 1h reminders ─────────────────────────────────────────────
            window_1h_start = now + timedelta(minutes=50)
            window_1h_end = now + timedelta(minutes=70)

            result = await db.execute(
                select(Appointment).where(
                    Appointment.reminder_1h_sent == False,  # noqa: E712
                    Appointment.status.in_(["pending", "confirmed"]),
                    Appointment.scheduled_at >= window_1h_start,
                    Appointment.scheduled_at <= window_1h_end,
                )
            )
            for appt in result.scalars().all():
                user_result = await db.execute(select(User).where(User.id == appt.advertiser_id))
                advertiser = user_result.scalar_one_or_none()
                from_number = advertiser.whatsapp_number if advertiser else None

                phone = appt.customer_phone
                if not phone and appt.contact_id:
                    c_result = await db.execute(select(Contact).where(Contact.id == appt.contact_id))
                    contact = c_result.scalar_one_or_none()
                    if contact:
                        phone = contact.phone

                if phone:
                    hora = appt.scheduled_at.strftime("%I:%M %p").lstrip("0")
                    biz_name = advertiser.business_name if advertiser else "tu cita"
                    status_emoji = "✅" if appt.status == "confirmed" else "📅"
                    msg = (
                        f"⏰ *Tu cita es en 1 hora*\n\n"
                        f"{status_emoji} {appt.service} a las {hora}\n"
                        f"🏪 {biz_name}\n\n"
                        f"¡Te esperamos! 😊"
                    )
                    await send_whatsapp(phone, msg, from_number=from_number)
                    # Ya no preguntamos a 1h — solo recordamos
                    appt.awaiting_confirmation = False

                appt.reminder_1h_sent = True

            await db.commit()

    run_async(_remind())


@celery_app.task(bind=True, max_retries=2)
def send_parrilla_day(
    self,
    advertiser_id: str,
    audio_url: str,
    script: str,
    day_name: str,
    mode: str,
):
    """Envía la cuña del día de la parrilla semanal a todos los contactos activos.

    Programado automáticamente por generate_parrilla cuando auto_schedule=True.
    Respeta el anti-ban delay y el quota de mensajes del plan.
    """
    async def _send():
        from app.database import AsyncSessionLocal
        from app.models.contact import Contact
        from app.models.user import User
        from app.models.message import Message
        from app.services.twilio_service import anti_ban_delay, send_whatsapp_media
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            adv_result = await db.execute(
                select(User).where(User.id == uuid.UUID(advertiser_id))
            )
            advertiser = adv_result.scalar_one_or_none()
            if not advertiser or advertiser.messages_remaining <= 0:
                logger.warning("[PARRILLA] %s — sin mensajes disponibles, día %s omitido", advertiser_id, day_name)
                return

            contacts_result = await db.execute(
                select(Contact).where(
                    Contact.advertiser_id == uuid.UUID(advertiser_id),
                    Contact.status == "active",
                )
            )
            contacts = contacts_result.scalars().all()

            ban_delay = 0
            sent = 0

            for contact in contacts:
                if advertiser.messages_remaining <= 0:
                    break

                msg = Message(
                    advertiser_id=uuid.UUID(advertiser_id),
                    contact_id=contact.id,
                    direction="outbound",
                    content=f"[PARRILLA:{day_name}:{mode}] {audio_url}",
                    status="queued",
                    scheduled_for=datetime.now(timezone.utc),
                )
                db.add(msg)
                await db.flush()

                send_whatsapp_voice_note.apply_async(
                    args=[str(msg.id), contact.phone, audio_url, script[:200]],
                    countdown=ban_delay,
                    queue="whatsapp",
                )
                advertiser.messages_remaining -= 1
                ban_delay += anti_ban_delay()
                sent += 1

            await db.commit()
            logger.info("[PARRILLA] %s — %s enviado a %d contactos", day_name, mode, sent)

    try:
        run_async(_send())
    except Exception as exc:
        raise self.retry(exc=exc)
