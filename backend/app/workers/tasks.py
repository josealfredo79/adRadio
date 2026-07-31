"""
Celery tasks — background jobs for IaRadio.
"""
import logging
import uuid
from datetime import datetime, timezone, timedelta

from app.workers.celery_app import celery_app
from app.workers.task_helpers import (
    run_async, _extract_text,
    send_regular_messages, send_banner_messages, send_radio_messages,
    send_parrilla_messages, notify_campaign_failed, run_parrilla_generation,
    send_24h_reminders, send_1h_reminders,
    segment_fingerprint, is_segment_on_cooldown, record_segment_send,
    get_recipient_cap_state,
)
from app.workers.task_helpers.common import suppress_contact_on_error

logger = logging.getLogger(__name__)

# Meta WhatsApp Cloud API codes for rate-limit/throughput errors — worth a
# retry, unlike a permanent failure. Source: Meta's official error code
# reference (developers.facebook.com/.../whatsapp/support/error-codes).
# Meta formats error messages as "(#<code>) <description>" — match on that
# parenthesized form, not the bare digits, since a bare "4" would false-match
# almost any error string.
_RATE_LIMIT_ERROR_CODES = ("(#4)", "80007", "130429", "131048", "131056", "131064", "rate")


@celery_app.task(bind=True, max_retries=5, default_retry_delay=120)
def send_whatsapp_message(self, message_id: str, to: str, body: str):
    """Send a WhatsApp message via Meta Cloud API with retry logic."""
    async def _send():
        from app.database import CeleryAsyncSessionLocal as AsyncSessionLocal
        from app.models.message import Message
        from app.models.user import User
        from app.services.meta_service import send_whatsapp
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Message).where(Message.id == uuid.UUID(message_id)))
            msg = result.scalar_one_or_none()

            advertiser = None
            if msg:
                adv_res = await db.execute(select(User).where(User.id == msg.advertiser_id))
                advertiser = adv_res.scalar_one_or_none()
                if not advertiser or advertiser.messages_remaining <= 0:
                    msg.status = "failed"
                    msg.error_code = "quota_exceeded"
                    msg.sent_at = None
                    await db.commit()
                    logger.warning("[QUOTA] %s — no messages remaining, message %s dropped", msg.advertiser_id, message_id)
                    return

            sid, error = await send_whatsapp(to, body, advertiser=advertiser)

            if msg:
                msg.status = "sent" if sid else "failed"
                msg.wa_message_id = sid
                msg.error_code = error
                msg.sent_at = datetime.now(timezone.utc) if sid else None
                if sid and advertiser:
                    advertiser.messages_remaining -= 1
                await db.commit()

                # Auto-suppress contact on permanent delivery errors
                if not sid and msg.contact_id and error:
                    await suppress_contact_on_error(db, msg.contact_id, error)
                    await db.commit()

                # Capa 13: un error de riesgo de baneo a nivel de cuenta
                # (ver is_ban_risk_error) pausa toda campaña activa del
                # advertiser — pause_active_campaigns ya es un no-op sobre
                # campañas que otra tarea concurrente dejó en 'paused'.
                if not sid and error and advertiser:
                    from app.services.meta_quality_service import is_ban_risk_error, pause_active_campaigns
                    if is_ban_risk_error(error):
                        await pause_active_campaigns(db, advertiser.id)
                        await db.commit()
                        logger.warning(
                            "[BAN RISK] advertiser=%s error=%s — campañas activas auto-pausadas",
                            advertiser.id, error,
                        )

            if error and any(code in str(error) for code in _RATE_LIMIT_ERROR_CODES):
                raise RuntimeError(f"WhatsApp rate limit: {error}")

    try:
        run_async(_send())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=120 * (2 ** self.request.retries))


@celery_app.task(bind=True, max_retries=5, default_retry_delay=120)
def send_whatsapp_voice_note(self, message_id: str, to: str, audio_url: str, caption: str = ""):
    """Send a WhatsApp voice note (audio cuña) via Meta Cloud API media message."""
    async def _send():
        from app.database import CeleryAsyncSessionLocal as AsyncSessionLocal
        from app.models.message import Message
        from app.models.user import User
        from app.services.meta_service import send_whatsapp_media
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Message).where(Message.id == uuid.UUID(message_id)))
            msg = result.scalar_one_or_none()

            advertiser = None
            if msg:
                adv_res = await db.execute(select(User).where(User.id == msg.advertiser_id))
                advertiser = adv_res.scalar_one_or_none()
                if not advertiser or advertiser.messages_remaining <= 0:
                    msg.status = "failed"
                    msg.error_code = "quota_exceeded"
                    msg.sent_at = None
                    await db.commit()
                    logger.warning("[QUOTA] %s — no messages remaining, voice note %s dropped", msg.advertiser_id, message_id)
                    return

            sid, error = await send_whatsapp_media(to, audio_url, body=caption, advertiser=advertiser)

            if msg:
                msg.status = "sent" if sid else "failed"
                msg.wa_message_id = sid
                msg.error_code = error
                msg.sent_at = datetime.now(timezone.utc) if sid else None
                if sid and advertiser:
                    advertiser.messages_remaining -= 1
                await db.commit()

                # Auto-suppress contact on permanent delivery errors
                if not sid and msg.contact_id and error:
                    await suppress_contact_on_error(db, msg.contact_id, error)
                    await db.commit()

                # Capa 13: un error de riesgo de baneo a nivel de cuenta
                # (ver is_ban_risk_error) pausa toda campaña activa del
                # advertiser — pause_active_campaigns ya es un no-op sobre
                # campañas que otra tarea concurrente dejó en 'paused'.
                if not sid and error and advertiser:
                    from app.services.meta_quality_service import is_ban_risk_error, pause_active_campaigns
                    if is_ban_risk_error(error):
                        await pause_active_campaigns(db, advertiser.id)
                        await db.commit()
                        logger.warning(
                            "[BAN RISK] advertiser=%s error=%s — campañas activas auto-pausadas",
                            advertiser.id, error,
                        )

            if error and any(code in str(error) for code in _RATE_LIMIT_ERROR_CODES):
                raise RuntimeError(f"WhatsApp rate limit: {error}")

    try:
        run_async(_send())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=120 * (2 ** self.request.retries))


@celery_app.task(bind=True, max_retries=5, default_retry_delay=120)
def send_whatsapp_image_message(self, message_id: str, to: str, image_url: str, caption: str = ""):
    """Send a WhatsApp image (banner) via Meta Cloud API media message."""
    async def _send():
        from app.database import CeleryAsyncSessionLocal as AsyncSessionLocal
        from app.models.message import Message
        from app.models.user import User
        from app.services.meta_service import send_whatsapp_image
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Message).where(Message.id == uuid.UUID(message_id)))
            msg = result.scalar_one_or_none()

            advertiser = None
            if msg:
                adv_res = await db.execute(select(User).where(User.id == msg.advertiser_id))
                advertiser = adv_res.scalar_one_or_none()
                if not advertiser or advertiser.messages_remaining <= 0:
                    msg.status = "failed"
                    msg.error_code = "quota_exceeded"
                    msg.sent_at = None
                    await db.commit()
                    logger.warning("[QUOTA] %s — no messages remaining, image %s dropped", msg.advertiser_id, message_id)
                    return

            sid, error = await send_whatsapp_image(to, image_url, caption=caption, advertiser=advertiser)

            if msg:
                msg.status = "sent" if sid else "failed"
                msg.wa_message_id = sid
                msg.error_code = error
                msg.sent_at = datetime.now(timezone.utc) if sid else None
                if sid and advertiser:
                    advertiser.messages_remaining -= 1
                await db.commit()

                # Auto-suppress contact on permanent delivery errors
                if not sid and msg.contact_id and error:
                    await suppress_contact_on_error(db, msg.contact_id, error)
                    await db.commit()

                # Capa 13: un error de riesgo de baneo a nivel de cuenta
                # (ver is_ban_risk_error) pausa toda campaña activa del
                # advertiser — pause_active_campaigns ya es un no-op sobre
                # campañas que otra tarea concurrente dejó en 'paused'.
                if not sid and error and advertiser:
                    from app.services.meta_quality_service import is_ban_risk_error, pause_active_campaigns
                    if is_ban_risk_error(error):
                        await pause_active_campaigns(db, advertiser.id)
                        await db.commit()
                        logger.warning(
                            "[BAN RISK] advertiser=%s error=%s — campañas activas auto-pausadas",
                            advertiser.id, error,
                        )

            if error and any(code in str(error) for code in _RATE_LIMIT_ERROR_CODES):
                raise RuntimeError(f"WhatsApp rate limit: {error}")

    try:
        run_async(_send())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=120 * (2 ** self.request.retries))


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def send_welcome_cuna(self, advertiser_id: str, to: str, business_name: str):
    """Generate a radio cuña and send it as a WhatsApp voice note to a new lead."""
    async def _run():
        from app.database import CeleryAsyncSessionLocal as AsyncSessionLocal
        from app.models.user import User
        from app.services.radio_service import generate_radio_ad
        from app.config import settings
        from app.services.meta_service import send_whatsapp_media
        from sqlalchemy import select

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

        # ORM rows can't cross the Celery broker — re-fetch the advertiser here.
        async with AsyncSessionLocal() as db:
            adv_res = await db.execute(select(User).where(User.id == uuid.UUID(advertiser_id)))
            advertiser = adv_res.scalar_one_or_none()
            if not advertiser:
                return
            await send_whatsapp_media(to, audio_url, body="", advertiser=advertiser)

    try:
        run_async(_run())
    except Exception as exc:
        logger.warning("[WELCOME-CUÑA] Failed for %s, retrying: %s", to, exc)
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=2, default_retry_delay=30)
def auto_tag_contact_from_conversation(self, contact_id: str):
    """Use Claude Haiku to detect intent from last 10 messages and add auto-tags."""
    async def _run():
        from app.database import CeleryAsyncSessionLocal as AsyncSessionLocal
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
    except Exception as exc:
        logger.warning("[AUTO-TAG] Failed for contact %s, retrying: %s", contact_id, exc)
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=2)
def schedule_campaign(self, campaign_id: str):
    """Process and send all messages for a scheduled campaign."""
    async def _process():
        from app.database import CeleryAsyncSessionLocal as AsyncSessionLocal
        from app.models.campaign import Campaign
        from app.models.contact import Contact
        from app.models.user import User
        from app.services.messaging_throttle import is_human_hour, next_human_hour_utc
        from sqlalchemy import select

        if not is_human_hour(timezone_offset=-6):
            now_utc = datetime.now(timezone.utc)
            next_slot = next_human_hour_utc(timezone_offset=-6)
            delay_secs = max(60, int((next_slot - now_utc).total_seconds()))
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

            fingerprint = segment_fingerprint(campaign.segment or {})
            if await is_segment_on_cooldown(db, campaign.advertiser_id, fingerprint):
                campaign.status = "paused"
                await db.commit()
                logger.warning(
                    "[CAMPAIGN] Auto-paused %s — same list relaunched within the cooldown window",
                    campaign.id,
                )
                return

            cap_state = await get_recipient_cap_state(db, advertiser)
            if cap_state.limit is not None and cap_state.count >= cap_state.limit:
                campaign.status = "paused"
                await db.commit()
                logger.warning(
                    "[CAMPAIGN] Auto-paused %s — advertiser=%s ya está en el tope messaging_limit_tier (%d/%d)",
                    campaign.id, campaign.advertiser_id, cap_state.count, cap_state.limit,
                )
                return

            ab = campaign.ab_test or {}
            mode = ab.get("campaign_mode", "regular")
            messages_list: list[str] = ab.get("messages", [campaign.message_text])

            q = select(Contact).where(
                Contact.advertiser_id == campaign.advertiser_id,
                Contact.status == "active",
            )
            segment_tags = campaign.segment.get("tags", [])
            specific_ids = campaign.segment.get("specific_contacts", [])

            if specific_ids:
                q = q.where(Contact.id.in_([uuid.UUID(c) for c in specific_ids]))
            elif segment_tags:
                q = q.where(Contact.tags.overlap(segment_tags))

            contacts_result = await db.execute(q)
            contacts = contacts_result.scalars().all()

            campaign.status = "running"
            await record_segment_send(db, campaign.advertiser_id, fingerprint)
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

            campaign.status = "completed"
            await db.commit()

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
        from app.database import CeleryAsyncSessionLocal as AsyncSessionLocal
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
            from app.database import CeleryAsyncSessionLocal as AsyncSessionLocal
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


@celery_app.task(bind=True, max_retries=2, default_retry_delay=30)
def import_contacts_csv(self, advertiser_id: str, rows: list[dict], consent_confirmed: bool = False):
    """Bulk import contacts from CSV rows.

    consent_confirmed reflects the advertiser's explicit checkbox at upload
    time ("I confirm these contacts agreed to receive WhatsApp"). When False,
    new contacts are stored as consent_status='unconfirmed' — they can still
    receive messages while their conversation window is open (e.g. they wrote
    in first), but campaign sends can't use an approved template to reopen a
    closed window for them (see _ensure_conversation_window). This is the
    guard against blasting cold, unverified lists.
    """
    async def _import():
        import re
        from app.database import CeleryAsyncSessionLocal as AsyncSessionLocal
        from app.models.contact import Contact
        from sqlalchemy import select

        consent_status = "confirmed" if consent_confirmed else "unconfirmed"

        async with AsyncSessionLocal() as db:
            imported = 0
            skipped = 0
            for row in rows:
                try:
                    phone = str(row.get("phone", row.get("telefono", ""))).strip()
                    name = str(row.get("name", row.get("nombre", ""))).strip()
                    if not phone or not re.match(r"^\+\d{7,15}$", phone):
                        skipped += 1
                        continue
                    existing = await db.execute(
                        select(Contact).where(
                            Contact.advertiser_id == uuid.UUID(advertiser_id),
                            Contact.phone == phone,
                        )
                    )
                    if existing.scalar_one_or_none():
                        skipped += 1
                        continue
                    contact = Contact(
                        advertiser_id=uuid.UUID(advertiser_id),
                        name=name or phone, phone=phone,
                        email=str(row.get("email", "")).strip() or None,
                        city=str(row.get("city", row.get("ciudad", ""))).strip() or None,
                        source="csv",
                        consent_status=consent_status,
                    )
                    db.add(contact)
                    imported += 1
                except Exception as row_err:
                    logger.warning("[CSV-IMPORT] Skipping row: %s", row_err)
                    skipped += 1
            await db.commit()
            logger.info("[CSV-IMPORT] %s: %d imported, %d skipped", advertiser_id, imported, skipped)

    try:
        run_async(_import())
    except Exception as exc:
        logger.warning("[CSV-IMPORT] Failed, retrying: %s", exc)
        raise self.retry(exc=exc)


@celery_app.task
def check_scheduled_campaigns():
    """Celery Beat: trigger campaigns scheduled for now."""
    async def _check():
        from app.database import CeleryAsyncSessionLocal as AsyncSessionLocal
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
        from app.database import CeleryAsyncSessionLocal as AsyncSessionLocal
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
        from app.database import CeleryAsyncSessionLocal as AsyncSessionLocal
        from app.models.user import User
        from app.config import settings
        from app.core.email import send_trial_expiring_email
        from app.services.meta_service import send_whatsapp
        from sqlalchemy import select

        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as db:
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
                                f"👉 {settings.FRONTEND_PUBLIC_URL or 'https://app.iaradio.app'}/app/plans"
                            )
                            await send_whatsapp(to=user.whatsapp_number, body=msg, advertiser=user)
                        except Exception as e:
                            logger.error("[TRIAL REMINDER] WhatsApp failed for %s: %s", user.email, e)

    run_async(_remind())


@celery_app.task
def send_appointment_reminders():
    """Celery Beat: send WhatsApp reminders for upcoming appointments."""
    async def _remind():
        from app.database import CeleryAsyncSessionLocal as AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            now = datetime.now(timezone.utc)
            await send_24h_reminders(db, now)
            await send_1h_reminders(db, now)
            await db.commit()

    run_async(_remind())


@celery_app.task
def poll_meta_quality_ratings():
    """Celery Beat: refresh the real quality_rating (GREEN/YELLOW/RED) from
    Meta's Graph API for every connected advertiser. The webhook
    (meta_incoming.py, field phone_number_quality_update) only ever carries
    FLAGGED/UNFLAGGED — this poll is the only way to catch a number cooling
    into YELLOW before Meta fully flags it."""
    async def _poll():
        from sqlalchemy import select

        from app.database import CeleryAsyncSessionLocal as AsyncSessionLocal
        from app.models.user import User
        from app.services.meta_client import MetaApiError, graph_request
        from app.services.meta_quality_service import apply_quality_signal
        from app.services.meta_service import _connection

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(User).where(User.meta_connection_status == "connected"))
            for advertiser in result.scalars().all():
                conn = _connection(advertiser)
                if conn is None:
                    continue
                phone_number_id, token = conn
                try:
                    data = await graph_request(
                        f"{phone_number_id}?fields=quality_rating,messaging_limit_tier", token=token
                    )
                except MetaApiError as e:
                    logger.warning("[META QUALITY POLL] advertiser=%s failed: %s", advertiser.id, e)
                    continue
                rating = data.get("quality_rating")
                tier = data.get("messaging_limit_tier")
                if rating or tier:
                    await apply_quality_signal(db, advertiser, rating, tier)

    run_async(_poll())


@celery_app.task(bind=True, max_retries=2)
def send_parrilla_day(self, advertiser_id: str, audio_url: str, script: str, day_name: str, mode: str):
    """Sends the daily cuña from the weekly parrilla to all active contacts."""
    async def _send():
        from app.database import CeleryAsyncSessionLocal as AsyncSessionLocal
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


@celery_app.task(bind=True, soft_time_limit=600, time_limit=900)
def generate_parrilla_task(self, job_id: str, advertiser_id: str, body_dict: dict):
    """
    Genera la parrilla semanal completa (7 días de guiones + audio/banners)
    en background. Límite de tiempo más alto que el default (5/10 min) porque
    son 7 pasos secuenciales de LLM+TTS/banner que pueden acercarse a eso.

    No se reintenta automáticamente ante fallo: repetir todo el job
    duplicaría llamadas pagadas a Claude/TTS por los días que ya salieron
    bien; el estado queda marcado "error" en Redis para que el usuario
    decida si reintentar desde la UI.
    """
    try:
        run_async(run_parrilla_generation(job_id, advertiser_id, body_dict))
    except Exception:
        logger.exception("[PARRILLA] job %s crashed", job_id)


@celery_app.task(bind=True, soft_time_limit=1500, time_limit=1800)
def run_lab_task(self, lab_run_id: str):
    """
    Corre el Laboratorio (6 personas simuladas + juez) en background. Límite
    de tiempo alto (25/30 min) porque son hasta 6 personas x varios turnos
    de LLM cada una, más el juez por persona — y cada turno de RAG puede
    pegarle al rate limit gratuito de Voyage AI (VOYAGE_EMBEDDING_DELAY_S,
    ~22-44s de reintento por llamada), medido en vivo durante el desarrollo.

    No se reintenta automáticamente: el estado queda marcado "error" en la
    fila lab_runs para que el usuario decida si reintenta desde la UI.
    """
    async def _run():
        from app.database import CeleryAsyncSessionLocal as AsyncSessionLocal
        from app.services.lab.runner import run_lab

        async with AsyncSessionLocal() as db:
            await run_lab(lab_run_id, db)

    try:
        run_async(_run())
    except Exception:
        logger.exception("[LAB] job %s crashed", lab_run_id)


@celery_app.task
def update_contact_engagement_score(contact_id: str):
    """Update contact engagement_score and lead_score using Claude."""
    async def _update():
        import json
        from app.database import CeleryAsyncSessionLocal as AsyncSessionLocal
        from app.models.contact import Contact
        from app.models.conversation import Conversation
        from app.models.message import Message
        from app.config import settings
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
                    model=settings.ANTHROPIC_MODEL, max_tokens=150, temperature=0.0,
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
        from app.database import CeleryAsyncSessionLocal as AsyncSessionLocal
        from app.models.automation import AutomationEnrollment, AutomationFlow
        from app.models.contact import Contact
        from app.models.conversation import Conversation
        from app.models.message import Message
        from app.models.user import User
        from app.services.meta_service import send_whatsapp
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

                sid, error = await send_whatsapp(contact.phone, message_content, advertiser=advertiser)

                if sid:
                    advertiser.messages_remaining -= 1

                db.add(Message(
                    advertiser_id=enrollment.advertiser_id, contact_id=contact.id,
                    direction="outbound", content=message_content,
                    status="sent" if sid else "failed",
                    wa_message_id=sid, error_code=error, sent_at=now if sid else None,
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
        from datetime import datetime, timezone, timedelta
        from app.database import CeleryAsyncSessionLocal as AsyncSessionLocal
        from app.models.automation import AutomationFlow, AutomationEnrollment
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        now = datetime.now(timezone.utc)

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

    run_async(_run())
