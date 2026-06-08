"""
Campaign operations helpers — extracted from schedule_campaign.
"""
import logging
import random
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import select

logger = logging.getLogger(__name__)

_ACTIVE_CUTOFF_DAYS = 90
_MIN_ENGAGEMENT_SCORE = 10


def _is_contact_active(contact) -> bool:
    """Skip inactive contacts to reduce ban risk.
    New contacts (never interacted) are always considered active.
    """
    if contact.status != "active":
        return False
    # New contact: no interaction history yet, allow through
    if contact.last_interaction is None and (contact.engagement_score or 0) == 0:
        return True
    if (contact.engagement_score or 0) < _MIN_ENGAGEMENT_SCORE:
        return False
    if contact.last_interaction is None:
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(days=_ACTIVE_CUTOFF_DAYS)
    if contact.last_interaction < cutoff:
        return False
    return True


async def _ensure_conversation_window(
    db,
    advertiser_id: uuid.UUID,
    contact,
    from_number: str | None = None,
    business_name: str | None = None,
) -> int:
    """Send the invitacion_radio template if the 24h window is closed.
    Returns extra delay (seconds) to add before sending the campaign message.
    """
    from app.models.conversation import Conversation
    from app.services.twilio_service import send_whatsapp_template
    from app.config import settings

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    result = await db.execute(
        select(Conversation).where(
            Conversation.advertiser_id == advertiser_id,
            Conversation.contact_id == contact.id,
            Conversation.status == "active",
        )
    )
    conv = result.scalar_one_or_none()
    if conv and conv.last_activity and conv.last_activity > cutoff:
        return 0

    contact_name = (contact.name or "Cliente").split()[0] if contact.name else "Cliente"
    business_name = business_name or "IARadio"

    # Try UTILITY (notificacion_audio_v2) first — can open window outside 24h, fall back to MARKETING (notificacion_informativa)
    used_sid = ""
    sid, error = await send_whatsapp_template(
        to=contact.phone,
        template_sid=settings.TWILIO_UTILITY_TEMPLATE_SID,
        variables={"1": contact_name, "2": business_name, "3": "aqui"},
        from_number=from_number,
    )
    if sid:
        used_sid = settings.TWILIO_UTILITY_TEMPLATE_SID
    else:
        sid, error = await send_whatsapp_template(
            to=contact.phone,
            template_sid=settings.TWILIO_INVITACION_TEMPLATE_SID,
            variables={"1": contact_name},
            from_number=from_number,
        )
        if sid:
            used_sid = settings.TWILIO_INVITACION_TEMPLATE_SID
    if not sid:
        logger.warning("[TEMPLATE] All templates failed for %s: %s", contact.phone, error)
        return 0

    if not conv:
        conv = Conversation(advertiser_id=advertiser_id, contact_id=contact.id, messages=[], lead_score="cold")
        db.add(conv)
        await db.flush()
    entry = {
        "role": "assistant",
        "content": f"[TEMPLATE:{used_sid}] Hola {contact_name}, …",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    conv.messages = (conv.messages + [entry])[-40:]
    conv.last_activity = datetime.now(timezone.utc)
    conv.status = "active"
    return random.randint(10, 20)


async def send_banner_messages(db, campaign, contacts, advertiser, ab, ban_delay):
    """Send banner-style campaign messages."""
    from app.services.banner_service import (
        generate_banner_png, generate_banner_copy_with_claude, select_design,
    )
    from app.services.storage_service import upload_bytes
    from app.models.message import Message
    from app.workers.tasks import send_whatsapp_voice_note
    from app.services.twilio_service import anti_ban_delay

    promo_description = ab.get("promo_description", campaign.message_text)
    palette = ab.get("banner_palette", "")  # vacío = auto según negocio
    caption = ab.get("banner_caption", "")
    layout_override = ab.get("banner_layout", "")
    MAX_PER_HOUR = 60
    from_number = getattr(advertiser, "whatsapp_number", None)

    # Selección de diseño según negocio y tipo de campaña
    design = select_design(advertiser.business_category, campaign.type)
    palette = palette or design.palette
    layout = layout_override or design.layout

    for idx_b, contact in enumerate(contacts):
        if advertiser.messages_remaining <= 0:
            break

        if not _is_contact_active(contact):
            logger.info("[CAMPAIGN] Skipping inactive contact %s", contact.id)
            continue

        if idx_b > 0 and idx_b % MAX_PER_HOUR == 0:
            ban_delay = int(idx_b / MAX_PER_HOUR) * 3600

        extra = await _ensure_conversation_window(
            db, campaign.advertiser_id, contact, from_number,
            business_name=advertiser.business_name,
        )
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

        send_whatsapp_voice_note.apply_async(
            args=[str(msg.id), contact.phone, banner_url, body_text],
            countdown=ban_delay,
            queue="whatsapp",
        )
        advertiser.messages_remaining -= 1
        ban_delay += anti_ban_delay()

    await db.commit()


async def send_radio_messages(db, campaign, contacts, advertiser, ab, ban_delay):
    """Send radio/comunitaria campaign messages."""
    from app.models.message import Message
    from app.workers.tasks import send_whatsapp_voice_note
    from app.services.twilio_service import anti_ban_delay

    audio_url = ab.get("audio_url", "")
    radio_script = ab.get("radio_script", campaign.message_text)
    MAX_PER_HOUR = 60
    from_number = getattr(advertiser, "whatsapp_number", None)

    for idx_r, contact in enumerate(contacts):
        if advertiser.messages_remaining <= 0:
            break

        if not _is_contact_active(contact):
            logger.info("[CAMPAIGN] Skipping inactive contact %s", contact.id)
            continue

        if idx_r > 0 and idx_r % MAX_PER_HOUR == 0:
            ban_delay = int(idx_r / MAX_PER_HOUR) * 3600

        extra = await _ensure_conversation_window(
            db, campaign.advertiser_id, contact, from_number,
            business_name=advertiser.business_name,
        )
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
        advertiser.messages_remaining -= 1
        ban_delay += anti_ban_delay()

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
    from app.services.twilio_service import anti_ban_delay

    MAX_PER_HOUR = 60
    from_number = getattr(advertiser, "whatsapp_number", None)

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

    for i, contact in enumerate(contacts):
        if advertiser.messages_remaining <= 0:
            break

        if not _is_contact_active(contact):
            logger.info("[CAMPAIGN] Skipping inactive contact %s", contact.id)
            continue

        if i > 0 and i % MAX_PER_HOUR == 0:
            ban_delay = int(i / MAX_PER_HOUR) * 3600

        extra = await _ensure_conversation_window(
            db, campaign.advertiser_id, contact, from_number,
            business_name=advertiser.business_name,
        )
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

        advertiser.messages_remaining -= 1
        ban_delay += anti_ban_delay()

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


async def send_parrilla_messages(db, advertiser, contacts, audio_url, script, day_name, mode):
    """Send parrilla day messages to all active contacts."""
    from app.models.message import Message
    from app.workers.tasks import send_whatsapp_voice_note
    from app.services.twilio_service import anti_ban_delay

    ban_delay = 0
    sent = 0
    from_number = getattr(advertiser, "whatsapp_number", None)

    for contact in contacts:
        if advertiser.messages_remaining <= 0:
            break

        if not _is_contact_active(contact):
            logger.info("[CAMPAIGN] Skipping inactive contact %s", contact.id)
            continue

        extra = await _ensure_conversation_window(
            db, advertiser.id, contact, from_number,
            business_name=advertiser.business_name,
        )
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
        advertiser.messages_remaining -= 1
        ban_delay += anti_ban_delay()
        sent += 1

    return sent
