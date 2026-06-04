"""
Campaign operations helpers — extracted from schedule_campaign.
"""
import logging
import random
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import select

logger = logging.getLogger(__name__)


async def send_banner_messages(db, campaign, contacts, advertiser, ab, ban_delay):
    """Send banner-style campaign messages."""
    from app.services.banner_service import generate_banner_png, generate_banner_copy_with_claude
    from app.services.storage_service import upload_bytes
    from app.models.message import Message
    from app.workers.tasks import send_whatsapp_voice_note
    from app.services.twilio_service import anti_ban_delay

    promo_description = ab.get("promo_description", campaign.message_text)
    palette = ab.get("banner_palette", "promo")
    caption = ab.get("banner_caption", "")
    MAX_PER_HOUR = 60

    for idx_b, contact in enumerate(contacts):
        if advertiser.messages_remaining <= 0:
            break

        if idx_b > 0 and idx_b % MAX_PER_HOUR == 0:
            ban_delay = int(idx_b / MAX_PER_HOUR) * 3600

        contact_name = (contact.name or "").split()[0] if contact.name else "Cliente"

        copy = await generate_banner_copy_with_claude(
            business_name=advertiser.business_name or "Tu negocio",
            contact_name=contact_name,
            promo_description=promo_description,
        )

        png_bytes = generate_banner_png(copy, palette)

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

    for idx_r, contact in enumerate(contacts):
        if advertiser.messages_remaining <= 0:
            break

        if idx_r > 0 and idx_r % MAX_PER_HOUR == 0:
            ban_delay = int(idx_r / MAX_PER_HOUR) * 3600

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
    """Send regular campaign messages with personalization and coupons."""
    from app.models.coupon import Coupon
    from app.models.message import Message
    from app.workers.tasks import send_whatsapp_message
    from app.services.claude_service import personalize_message
    from app.services.coupon_service import (
        generate_coupon_code, format_coupon_in_message, default_expiry
    )
    from app.services.twilio_service import anti_ban_delay

    MAX_PER_HOUR = 60

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

        if i > 0 and i % MAX_PER_HOUR == 0:
            ban_delay = int(i / MAX_PER_HOUR) * 3600

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

        if ab_enabled and ab_variant == "b":
            ab_stats_b["sent"] = ab_stats_b.get("sent", 0) + 1
        else:
            ab_stats_a["sent"] = ab_stats_a.get("sent", 0) + 1

        send_whatsapp_message.apply_async(
            args=[str(msg.id), contact.phone, body],
            countdown=ban_delay,
            queue="whatsapp",
        )
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
        from app.database import AsyncSessionLocal
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

    for contact in contacts:
        if advertiser.messages_remaining <= 0:
            break

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
