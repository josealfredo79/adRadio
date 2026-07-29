"""
Campaign operations helpers — extracted from schedule_campaign.
"""
import json
import logging
import random
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import select

logger = logging.getLogger(__name__)

_ACTIVE_CUTOFF_DAYS = 90
_MIN_ENGAGEMENT_SCORE = 10
_CAMPAIGN_COOLDOWN_HOURS = 48
_MAX_FAILED_SENDS = 3
_SUPPRESSION_DAYS = 30
_AUTO_PAUSE_THRESHOLD = 0.5  # pause campaign if >50% contacts fail


def _is_contact_active(contact) -> bool:
    """Skip inactive contacts to reduce ban risk.
    New contacts (never interacted) are always considered active.
    """
    now = datetime.now(timezone.utc)

    if contact.status != "active":
        return False

    # Suppressed due to repeated failures
    if contact.suppressed_until and now < contact.suppressed_until:
        return False
    # Reset suppression after period expires
    if contact.suppressed_until and now >= contact.suppressed_until:
        contact.failed_send_count = 0
        contact.suppressed_until = None

    # Cooldown: no campaigns to same contact within 48h
    if contact.last_campaign_sent_at:
        hours_since = (now - contact.last_campaign_sent_at).total_seconds() / 3600
        if hours_since < _CAMPAIGN_COOLDOWN_HOURS:
            return False

    # New contact: no interaction history yet, allow through
    if contact.last_interaction is None:
        return True
    if (contact.engagement_score or 0) >= _MIN_ENGAGEMENT_SCORE:
        return True
    cutoff = now - timedelta(days=_ACTIVE_CUTOFF_DAYS)
    if contact.last_interaction < cutoff:
        return False
    return True


async def _ensure_conversation_window(
    db,
    advertiser,
    contact,
    _convs: dict[str, object] | None = None,
) -> int | None:
    """Send the advertiser's approved utility template if the 24h window is closed.
    Returns extra delay (seconds) if it's safe to send now (window open, or an
    approved template just reopened it), or None if the send must be SKIPPED —
    window closed and no approved template available. This is a hard block:
    WhatsApp policy prohibits free-text outside the window, so unlike before
    there is no silent fallback to plain text here.
    Accepts optional preloaded conversations dict {contact_id: conv} to avoid N+1.
    """
    from app.models.conversation import Conversation
    from app.services.meta_service import send_whatsapp_template
    from app.services.whatsapp_window import is_window_open

    if _convs is not None:
        conv = _convs.get(str(contact.id))
    else:
        result = await db.execute(
            select(Conversation).where(
                Conversation.advertiser_id == advertiser.id,
                Conversation.contact_id == contact.id,
                Conversation.status == "active",
            )
        )
        conv = result.scalar_one_or_none()
    if is_window_open(conv):
        return 0

    template_name = advertiser.meta_utility_template_name
    if not template_name:
        # No approved utility template configured yet for this advertiser —
        # can't reopen the window outside it. Known limitation until they
        # set one in Configuración → WhatsApp.
        logger.info("[TEMPLATE] No meta_utility_template_name for advertiser=%s — blocking send, window closed", advertiser.id)
        return None

    contact_name = (contact.name or "Cliente").split()[0] if contact.name else "Cliente"
    business_name = advertiser.business_name or "IARadio"

    sid, error = await send_whatsapp_template(
        to=contact.phone,
        template_name=template_name,
        components=[{
            "type": "body",
            "parameters": [
                {"type": "text", "text": contact_name},
                {"type": "text", "text": business_name},
            ],
        }],
        advertiser=advertiser,
    )
    if not sid:
        logger.warning("[TEMPLATE] Utility template failed for %s: %s — blocking send", contact.phone, error)
        return None

    if not conv:
        conv = Conversation(advertiser_id=advertiser.id, contact_id=contact.id, messages=[], lead_score="cold")
        db.add(conv)
        await db.flush()
    entry = {
        "role": "assistant",
        "content": f"[TEMPLATE:{template_name}] Hola {contact_name}, …",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    conv.messages = (conv.messages + [entry])[-40:]
    conv.last_activity = datetime.now(timezone.utc)
    conv.status = "active"
    return random.randint(10, 20)


async def _preload_conversations(db, advertiser_id: uuid.UUID, contacts) -> dict[str, object]:
    """Preload conversations for all contacts to avoid N+1 queries."""
    from app.models.conversation import Conversation
    contact_ids = [c.id for c in contacts]
    if not contact_ids:
        return {}
    result = await db.execute(
        select(Conversation).where(
            Conversation.advertiser_id == advertiser_id,
            Conversation.contact_id.in_(contact_ids),
            Conversation.status == "active",
        )
    )
    convs = result.scalars().all()
    return {str(c.contact_id): c for c in convs}


async def send_banner_messages(db, campaign, contacts, advertiser, ab, ban_delay):
    """Send banner-style campaign messages."""
    from app.services.banner_service import (
        generate_banner_png, generate_banner_copy_with_claude, select_design,
    )
    from app.services.storage_service import upload_bytes
    from app.models.message import Message
    from app.workers.tasks import send_whatsapp_image_message
    from app.services.messaging_throttle import anti_ban_delay

    promo_description = ab.get("promo_description", campaign.message_text)
    palette = ab.get("banner_palette", "")  # vacío = auto según negocio
    caption = ab.get("banner_caption", "")
    layout_override = ab.get("banner_layout", "")
    MAX_PER_HOUR = 60

    # Preload conversations to avoid N+1
    _convs = await _preload_conversations(db, campaign.advertiser_id, contacts)

    # Selección de diseño según negocio y tipo de campaña
    design = select_design(advertiser.business_category, campaign.type)
    palette = palette or design.palette
    layout = layout_override or design.layout

    sent_count = 0
    skipped_count = 0

    for idx_b, contact in enumerate(contacts):
        if advertiser.messages_remaining <= 0:
            break

        if not _is_contact_active(contact):
            skipped_count += 1
            logger.info("[CAMPAIGN] Skipping inactive contact %s", contact.id)
            continue

        if idx_b > 0 and idx_b % MAX_PER_HOUR == 0:
            ban_delay = int(idx_b / MAX_PER_HOUR) * 3600

        extra = await _ensure_conversation_window(db, advertiser, contact, _convs=_convs)
        if extra is None:
            skipped_count += 1
            logger.info("[CAMPAIGN] Skipping contact %s — 24h window closed, no approved template", contact.id)
            continue
        ban_delay += extra

        contact_name = (contact.name or "").split()[0] if contact.name else "Cliente"

        copy = await generate_banner_copy_with_claude(
            business_name=advertiser.business_name or "Tu negocio",
            contact_name=contact_name,
            promo_description=promo_description,
            business_category=advertiser.business_category,
            campaign_type=campaign.type,
        )

        png_bytes = generate_banner_png(copy, palette, layout, contact_id=str(contact.id))

        key = f"banners/{campaign.id}/{contact.id}_{uuid.uuid4().hex[:8]}.png"
        banner_url = await upload_bytes(png_bytes, key, "image/png")

        if not banner_url:
            logger.error("[BANNER] Upload failed for contact %s", contact.id)
            continue

        body_text = caption or f"¡Hola {contact_name}! Mira lo que tenemos para ti 👆"

        msg = Message(
            campaign_id=campaign.id,
            contact_id=contact.id,
            advertiser_id=campaign.advertiser_id,
            direction="outbound",
            content=f"[BANNER] {banner_url}",
            status="queued",
            scheduled_for=datetime.now(timezone.utc),
        )
        db.add(msg)
        await db.flush()

        send_whatsapp_image_message.apply_async(
            args=[str(msg.id), contact.phone, banner_url, body_text],
            countdown=ban_delay,
            queue="whatsapp",
        )
        contact.last_campaign_sent_at = datetime.now(timezone.utc)
        advertiser.messages_remaining -= 1
        ban_delay += anti_ban_delay()
        sent_count += 1

    # Auto-pause if failure rate is too high
    total_attempted = sent_count + skipped_count
    if total_attempted > 10 and skipped_count / max(total_attempted, 1) > _AUTO_PAUSE_THRESHOLD:
        campaign.status = "paused"
        logger.warning("[CAMPAIGN] Auto-paused %s: %.0f%% failure rate (%d/%d)",
                       campaign.id, skipped_count / total_attempted * 100, skipped_count, total_attempted)

    await db.commit()


async def send_radio_messages(db, campaign, contacts, advertiser, ab, ban_delay):
    """Send radio/comunitaria campaign messages."""
    from app.models.message import Message
    from app.workers.tasks import send_whatsapp_voice_note
    from app.services.messaging_throttle import anti_ban_delay

    audio_url = ab.get("audio_url", "")
    radio_script = ab.get("radio_script", campaign.message_text)
    MAX_PER_HOUR = 60

    _convs = await _preload_conversations(db, campaign.advertiser_id, contacts)

    sent_count = 0
    skipped_count = 0

    for idx_r, contact in enumerate(contacts):
        if advertiser.messages_remaining <= 0:
            break

        if not _is_contact_active(contact):
            skipped_count += 1
            logger.info("[CAMPAIGN] Skipping inactive contact %s", contact.id)
            continue

        if idx_r > 0 and idx_r % MAX_PER_HOUR == 0:
            ban_delay = int(idx_r / MAX_PER_HOUR) * 3600

        extra = await _ensure_conversation_window(db, advertiser, contact, _convs=_convs)
        if extra is None:
            skipped_count += 1
            logger.info("[CAMPAIGN] Skipping contact %s — 24h window closed, no approved template", contact.id)
            continue
        ban_delay += extra

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
        contact.last_campaign_sent_at = datetime.now(timezone.utc)
        advertiser.messages_remaining -= 1
        ban_delay += anti_ban_delay()
        sent_count += 1

    # Auto-pause if failure rate is too high
    total_attempted = sent_count + skipped_count
    if total_attempted > 10 and skipped_count / max(total_attempted, 1) > _AUTO_PAUSE_THRESHOLD:
        campaign.status = "paused"
        logger.warning("[CAMPAIGN] Auto-paused %s: %.0f%% failure rate (%d/%d)",
                       campaign.id, skipped_count / total_attempted * 100, skipped_count, total_attempted)

    await db.commit()


async def send_regular_messages(db, campaign, contacts, advertiser, ab, messages_list, ban_delay):
    """Send regular campaign messages as audio voice notes with personalization and coupons."""
    from app.models.coupon import Coupon
    from app.models.message import Message
    from app.workers.tasks import send_whatsapp_voice_note
    from app.services.claude_service import personalize_message
    from app.services.coupon_service import (
        generate_coupon_code, format_coupon_in_message, default_expiry
    )
    from app.services.storage_service import upload_bytes
    from app.services.radio.tts import text_to_speech, LOCUTOR_VOICES
    from app.services.messaging_throttle import anti_ban_delay

    MAX_PER_HOUR = 60
    _convs = await _preload_conversations(db, campaign.advertiser_id, contacts)

    ab_enabled = ab.get("enabled", False)
    ab_variant_b = ab.get("variant_b", "")
    ab_stats_a = ab.get("stats_a", {"sent": 0, "replied": 0})
    ab_stats_b = ab.get("stats_b", {"sent": 0, "replied": 0})
    has_coupon: bool = ab.get("has_coupon", False)
    coupon_description: str = ab.get("coupon_description", "")
    coupon_hours: int = ab.get("coupon_hours", 72)

    advertiser_data = {
        "business_name": advertiser.business_name,
        "city": advertiser.city,
    }

    sent_count = 0
    skipped_count = 0

    for i, contact in enumerate(contacts):
        if advertiser.messages_remaining <= 0:
            break

        if not _is_contact_active(contact):
            skipped_count += 1
            logger.info("[CAMPAIGN] Skipping inactive contact %s", contact.id)
            continue

        if i > 0 and i % MAX_PER_HOUR == 0:
            ban_delay = int(i / MAX_PER_HOUR) * 3600

        extra = await _ensure_conversation_window(db, advertiser, contact, _convs=_convs)
        if extra is None:
            skipped_count += 1
            logger.info("[CAMPAIGN] Skipping contact %s — 24h window closed, no approved template", contact.id)
            continue
        ban_delay += extra

        contact_data = {
            "name": contact.name,
            "city": getattr(contact, "city", None),
        }

        if ab_enabled and ab_variant_b and i % 2 == 1:
            raw_template = ab_variant_b
            ab_variant = "b"
        else:
            raw_template = random.choice(messages_list) if messages_list else campaign.message_text
            ab_variant = "a"

        body = personalize_message(raw_template, contact_data, advertiser_data)

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

        voice = LOCUTOR_VOICES.get("mx", LOCUTOR_VOICES["default"])
        audio_url = None
        try:
            mp3_bytes = await text_to_speech(body, voice)
            key = f"tts/{campaign.id}/{contact.id}_{uuid.uuid4().hex[:8]}.mp3"
            audio_url = await upload_bytes(mp3_bytes, key, "audio/mpeg")
        except Exception as tts_err:
            logger.error("[CAMPAIGN] TTS failed for contact %s: %s", contact.id, tts_err)

        if audio_url:
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
                args=[str(msg.id), contact.phone, audio_url, body],
                countdown=ban_delay,
                queue="whatsapp",
            )
        else:
            from app.workers.tasks import send_whatsapp_message
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

        if ab_enabled and ab_variant == "b":
            ab_stats_b["sent"] = ab_stats_b.get("sent", 0) + 1
        else:
            ab_stats_a["sent"] = ab_stats_a.get("sent", 0) + 1

        contact.last_campaign_sent_at = datetime.now(timezone.utc)
        advertiser.messages_remaining -= 1
        ban_delay += anti_ban_delay()
        sent_count += 1

    # Auto-pause if failure rate is too high
    total_attempted = sent_count + skipped_count
    if total_attempted > 10 and skipped_count / max(total_attempted, 1) > _AUTO_PAUSE_THRESHOLD:
        campaign.status = "paused"
        logger.warning("[CAMPAIGN] Auto-paused %s: %.0f%% failure rate (%d/%d)",
                       campaign.id, skipped_count / total_attempted * 100, skipped_count, total_attempted)

    if ab_enabled:
        new_ab = dict(campaign.ab_test)
        new_ab["stats_a"] = ab_stats_a
        new_ab["stats_b"] = ab_stats_b
        campaign.ab_test = new_ab

    await db.commit()

    # Notifications
    try:
        adv_email = advertiser.email
        if adv_email:
            from app.core.email import send_campaign_sent_email
            await send_campaign_sent_email(
                to=adv_email,
                business_name=advertiser.business_name or "Mi negocio",
                campaign_name=campaign.name,
                sent_count=len(contacts),
            )
    except Exception as email_err:
        logger.warning("[CAMPAIGN-EMAIL] Failed to send notification: %s", email_err)

    try:
        from app.services.webhook_dispatcher import dispatch_webhook_event
        await dispatch_webhook_event(
            "campaign.sent",
            {"id": str(campaign.id), "name": campaign.name, "status": "running"},
            db,
        )
        await dispatch_webhook_event(
            "campaign.completed",
            {"id": str(campaign.id), "name": campaign.name, "status": "completed"},
            db,
        )
    except Exception as wh_err:
        logger.warning("[CAMPAIGN-WEBHOOK] Failed to dispatch campaign events: %s", wh_err)


async def notify_campaign_failed(campaign_id, exc):
    """Send failure notifications for campaign."""
    try:
        from app.database import CeleryAsyncSessionLocal as AsyncSessionLocal
        from app.models.campaign import Campaign
        from app.models.user import User
        from app.core.email import send_campaign_failed_email
        from app.services.webhook_dispatcher import dispatch_webhook_event
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Campaign).where(Campaign.id == uuid.UUID(campaign_id))
            )
            c = result.scalar_one_or_none()
            if c:
                adv_res = await db.execute(select(User).where(User.id == c.advertiser_id))
                adv = adv_res.scalar_one_or_none()
                if adv and adv.email:
                    await send_campaign_failed_email(
                        to=adv.email,
                        business_name=adv.business_name or "Mi negocio",
                        campaign_name=c.name,
                        error=str(exc)[:500],
                    )
                try:
                    await dispatch_webhook_event(
                        "campaign.failed",
                        {"id": str(c.id), "name": c.name, "error": str(exc)[:500]},
                        db,
                    )
                except Exception as wh_err:
                    logger.warning("[CAMPAIGN-WEBHOOK] Failed to dispatch campaign.failed: %s", wh_err)
    except Exception as email_err:
        logger.warning("[CAMPAIGN-EMAIL] Failed to send failure notification: %s", email_err)


async def send_parrilla_messages(db, advertiser, contacts, audio_url, script, day_name, mode, campaign=None):
    """Send parrilla day messages to all active contacts."""
    from app.models.message import Message
    from app.workers.tasks import send_whatsapp_voice_note
    from app.services.messaging_throttle import anti_ban_delay

    MAX_PER_HOUR = 60
    ban_delay = 0
    sent = 0
    skipped_count = 0
    _convs = await _preload_conversations(db, advertiser.id, contacts)

    for idx, contact in enumerate(contacts):
        if advertiser.messages_remaining <= 0:
            break

        if not _is_contact_active(contact):
            skipped_count += 1
            logger.info("[CAMPAIGN] Skipping inactive contact %s", contact.id)
            continue

        if idx > 0 and idx % MAX_PER_HOUR == 0:
            ban_delay = int(idx / MAX_PER_HOUR) * 3600

        extra = await _ensure_conversation_window(db, advertiser, contact, _convs=_convs)
        if extra is None:
            skipped_count += 1
            logger.info("[CAMPAIGN] Skipping contact %s — 24h window closed, no approved template", contact.id)
            continue
        ban_delay += extra

        msg = Message(
            advertiser_id=advertiser.id,
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
        contact.last_campaign_sent_at = datetime.now(timezone.utc)
        advertiser.messages_remaining -= 1
        ban_delay += anti_ban_delay()
        sent += 1

    # Auto-pause if failure rate is too high
    total_attempted = sent + skipped_count
    if total_attempted > 10 and skipped_count / max(total_attempted, 1) > _AUTO_PAUSE_THRESHOLD:
        if campaign:
            campaign.status = "paused"
            logger.warning("[CAMPAIGN] Auto-paused %s: %.0f%% failure rate (%d/%d)",
                           campaign.id, skipped_count / total_attempted * 100, skipped_count, total_attempted)

    return sent


# ─── Generación de parrilla semanal (job asíncrono) ───────────────────────────
# Orden estratégico: valor primero, oferta al final de semana
# Cada tupla: (day_num, day_name, mode, emoji, format)
# format = "audio" | "banner"
_PARRILLA_ALL = [
    (0, "Lunes",     "comunitaria", "🌿", "audio"),
    (1, "Martes",    "capsula",     "💡", "banner"),
    (2, "Miércoles", "trivia",      "🧠", "audio"),
    (3, "Jueves",    "historia",    "📖", "banner"),
    (4, "Viernes",   "classic",     "🎙️", "audio"),
    (5, "Sábado",    "alerta",      "🚨", "banner"),
    (6, "Domingo",   "estacional",  "🗓️", "audio"),
]

# Starter: solo audio (sin banner)
_PARRILLA_STARTER = [
    (0, "Lunes",     "classic", "🎙️", "audio"),
    (1, "Martes",    "classic", "🎙️", "audio"),
    (2, "Miércoles", "classic", "🎙️", "audio"),
    (3, "Jueves",    "classic", "🎙️", "audio"),
    (4, "Viernes",   "classic", "🎙️", "audio"),
    (5, "Sábado",    "classic", "🎙️", "audio"),
    (6, "Domingo",   "classic", "🎙️", "audio"),
]

# Growth: mezcla audio + banner (sin alerta ni estacional)
_PARRILLA_GROWTH = [
    (0, "Lunes",     "comunitaria", "🌿", "audio"),
    (1, "Martes",    "capsula",     "💡", "banner"),
    (2, "Miércoles", "trivia",      "🧠", "audio"),
    (3, "Jueves",    "historia",    "📖", "banner"),
    (4, "Viernes",   "classic",     "🎙️", "audio"),
    (5, "Sábado",    "classic",     "🎙️", "banner"),
    (6, "Domingo",   "classic",     "🎙️", "audio"),
]


async def run_parrilla_generation(job_id: str, advertiser_id: str, body_dict: dict) -> None:
    """
    Genera la parrilla semanal de radio (7 cuñas/banners) en background y
    reporta progreso en Redis (`parrilla_job:{job_id}`) después de cada día,
    para que el frontend pueda hacer polling en vez de sostener un solo
    request HTTP de varios minutos.

    Se ejecuta dentro de un task de Celery — a diferencia del request HTTP
    original, si el cliente se desconecta el job sigue corriendo y el
    resultado queda disponible al consultar el estado.
    """
    import asyncio
    import redis.asyncio as aioredis
    from app.config import settings
    from app.database import CeleryAsyncSessionLocal as AsyncSessionLocal
    from app.models.user import User
    from app.models.campaign import Campaign
    from app.schemas.campaign import ParrillaDayOut
    from app.services.analytics_service import capture_event
    from app.services.banner_service import generate_banner_png, generate_banner_copy_with_claude, select_design
    from app.services.radio_service import generate_radio_ad, generate_radio_script
    from app.services.storage_service import upload_bytes
    from app.workers.tasks import schedule_campaign

    key = f"parrilla_job:{job_id}"
    redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

    async def _update_state(**kwargs):
        raw = await redis_client.get(key)
        state = json.loads(raw) if raw else {"advertiser_id": advertiser_id}
        state.update(kwargs)
        await redis_client.set(key, json.dumps(state), ex=3600)

    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(User).where(User.id == uuid.UUID(advertiser_id)))
            advertiser = result.scalar_one_or_none()
            if not advertiser:
                await _update_state(status="error", error="Usuario no encontrado")
                return

            plan = advertiser.current_plan or "starter"
            if plan in ("pro", "business", "enterprise"):
                schedule_table = _PARRILLA_ALL
            elif plan == "growth":
                schedule_table = _PARRILLA_GROWTH
            else:  # starter / trial
                schedule_table = _PARRILLA_STARTER

            can_auto = plan in ("growth", "pro", "business", "enterprise")
            auto_scheduled = bool(body_dict.get("auto_schedule")) and can_auto

            try:
                hour, minute = (int(x) for x in body_dict.get("send_time", "10:00").split(":"))
            except Exception:
                hour, minute = 10, 0

            now = datetime.now(timezone.utc)
            days_out: list[dict] = []

            await _update_state(status="running", total_days=len(schedule_table), plan=plan, auto_scheduled=auto_scheduled)

            for day_num, day_name, mode, emoji, fmt in schedule_table:
                try:
                    day_context = f"Haz este mensaje específico para el día {day_name}, dale un ángulo único."
                    extra_context = body_dict.get("extra_context")
                    combined_context = f"{extra_context} - {day_context}" if extra_context else day_context

                    script = await generate_radio_script(
                        business_name=body_dict["business_name"],
                        message_or_intent=body_dict["intent"],
                        country=body_dict.get("country", "mx"),
                        mode=mode,
                        business_category=body_dict.get("business_category"),
                        extra_context=combined_context,
                    )

                    audio_url = None
                    banner_url = None
                    banner_ab = {}

                    if fmt == "banner":
                        design = select_design(body_dict.get("business_category"), "promo")
                        palette = body_dict.get("banner_palette") or design.palette
                        layout = body_dict.get("banner_layout") or design.layout

                        copy = await generate_banner_copy_with_claude(
                            business_name=body_dict["business_name"],
                            contact_name="Cliente",
                            promo_description=body_dict["intent"],
                            business_category=body_dict.get("business_category"),
                            campaign_type="promo",
                        )
                        png_bytes = generate_banner_png(copy, palette, layout, contact_id=None)
                        storage_key = f"parrilla/{advertiser_id}/{day_num}_{uuid.uuid4().hex[:8]}.png"
                        banner_url = await upload_bytes(png_bytes, storage_key, "image/png")

                        banner_ab = {
                            "banner_promo": body_dict["intent"],
                            "banner_palette": palette,
                            "banner_layout": layout,
                            "banner_headline": copy.headline,
                            "banner_subheadline": copy.subheadline,
                            "banner_cta": copy.cta,
                        }
                    else:
                        try:
                            audio_url = await generate_radio_ad(
                                business_name=body_dict["business_name"],
                                message_or_intent=body_dict["intent"],
                                country=body_dict.get("country", "mx"),
                                _script=script,
                                mode=mode,
                                business_category=body_dict.get("business_category"),
                                day_variant=day_num,
                            )
                        except Exception as audio_err:
                            logger.warning("[PARRILLA] Audio day %d failed: %s", day_num, audio_err)
                            audio_url = None

                    days_out.append(ParrillaDayOut(
                        day=day_num,
                        day_name=day_name,
                        mode=mode,
                        mode_emoji=emoji,
                        format=fmt,
                        script=script,
                        audio_url=audio_url,
                        banner_url=banner_url,
                    ).model_dump())

                    # Guardar campaña en DB
                    has_content = bool(audio_url or banner_url)
                    if has_content:
                        days_ahead = (day_num - now.weekday()) % 7
                        send_dt_today = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                        if days_ahead == 0 and now > send_dt_today:
                            days_ahead += 7
                        send_dt = (now + timedelta(days=days_ahead)).replace(
                            hour=hour, minute=minute, second=0, microsecond=0
                        )

                        ab_payload = {
                            "campaign_mode": "banner" if fmt == "banner" else "radio",
                            "radio_script": script,
                        }
                        if fmt == "banner":
                            ab_payload["audio_url"] = ""  # no audio
                            ab_payload.update(banner_ab)
                        else:
                            ab_payload["audio_url"] = audio_url or ""

                        campaign = Campaign(
                            advertiser_id=advertiser.id,
                            name=f"Parrilla: {day_name}",
                            type="promo",
                            message_text=script,
                            status="scheduled" if auto_scheduled else "draft",
                            ab_test=ab_payload,
                            schedule={"start_date": send_dt.isoformat().replace("+00:00", "Z")},
                        )
                        db.add(campaign)
                        await db.commit()
                        await db.refresh(campaign)

                        if auto_scheduled:
                            countdown = max(60, int((send_dt - now).total_seconds()))
                            schedule_campaign.apply_async(args=[str(campaign.id)], countdown=countdown)

                    await asyncio.sleep(0.5)

                except Exception as e:
                    logger.error("[PARRILLA] Day %d failed: %s", day_num, e)
                    days_out.append(ParrillaDayOut(
                        day=day_num,
                        day_name=day_name,
                        mode=mode,
                        mode_emoji=emoji,
                        format=fmt,
                        script=f"[Error generando: {e}]",
                        audio_url=None,
                        banner_url=None,
                    ).model_dump())

                await _update_state(current_day=day_num + 1, days=days_out)

            capture_event("parrilla_generated", user_id=advertiser.id, properties={
                "plan": plan,
                "days_count": len(days_out),
                "auto_scheduled": auto_scheduled,
            })
            await _update_state(status="done", days=days_out)

    except Exception as exc:
        logger.exception("[PARRILLA] job %s failed: %s", job_id, exc)
        await _update_state(status="error", error=str(exc))
    finally:
        await redis_client.aclose()
