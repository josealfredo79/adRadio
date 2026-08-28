"""
Meta WhatsApp Cloud API webhook — handshake (GET) + events (POST).

Replaces twilio_incoming.py + twilio_status.py: Meta sends both inbound
messages and delivery status updates in the same payload shape (unlike
Twilio's separate status callback URL), routed to the right advertiser by
`phone_number_id` rather than by a per-advertiser webhook token, because
this is one central app serving every advertiser's own WABA (each
advertiser calls POST /{waba_id}/subscribed_apps to route their webhooks
here — see meta_connect_service.subscribe_app_to_waba).
"""
import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.crypto import EncryptedValue, decrypt_secret
from app.core.rate_limiter import limiter
from app.database import get_db
from app.models.user import User
from app.services.inbound_pipeline import InboundMessage, process_inbound_message
from app.services.message_status_service import apply_status_update
from app.services.meta_client import download_media
from app.services.meta_quality_service import apply_quality_signal
from app.services.meta_service import send_typing_indicator, send_whatsapp
from app.services.storage_service import upload_bytes
from app.services.whisper_service import transcribe_audio_bytes

logger = logging.getLogger(__name__)

router = APIRouter()


async def meta_webhook_verify(
    hub_mode: str = Query("", alias="hub.mode"),
    hub_verify_token: str = Query("", alias="hub.verify_token"),
    hub_challenge: str = Query("", alias="hub.challenge"),
) -> Response:
    """Meta's one-time webhook handshake."""
    if hub_mode == "subscribe" and hub_verify_token and hmac.compare_digest(
        hub_verify_token, settings.META_WEBHOOK_VERIFY_TOKEN
    ):
        return Response(content=hub_challenge, media_type="text/plain")
    logger.warning("[META WEBHOOK] Handshake failed — mode=%s", hub_mode)
    return Response(status_code=403)


def _hmac_matches(secret: str, raw_body: bytes, header: str) -> bool:
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(header[7:], expected)


async def _advertiser_app_secret(db: AsyncSession, payload: dict) -> str | None:
    """The App Secret of the advertiser's OWN Meta App, for events that come
    from an app connected via the self-service manual flow (not IaRadio's
    central app). Resolved by the WABA id / phone_number_id in the payload."""
    waba_ids: set[str] = set()
    phone_number_ids: set[str] = set()
    for entry in payload.get("entry", []):
        if entry.get("id"):
            waba_ids.add(str(entry["id"]))
        for change in entry.get("changes", []):
            pn = change.get("value", {}).get("metadata", {}).get("phone_number_id")
            if pn:
                phone_number_ids.add(str(pn))
    if not waba_ids and not phone_number_ids:
        return None

    from sqlalchemy import or_
    conds = []
    if waba_ids:
        conds.append(User.meta_waba_id.in_(waba_ids))
    if phone_number_ids:
        conds.append(User.meta_phone_number_id.in_(phone_number_ids))
    result = await db.execute(
        select(User).where(or_(*conds), User.meta_app_secret_cipher.is_not(None))
    )
    advertiser = result.scalars().first()
    if not advertiser or not advertiser.meta_app_secret_cipher:
        return None
    try:
        return decrypt_secret(EncryptedValue(
            cipher=advertiser.meta_app_secret_cipher,
            iv=advertiser.meta_app_secret_iv,
            tag=advertiser.meta_app_secret_tag,
        ))
    except Exception:
        logger.error("[META WEBHOOK] app secret decrypt failed for advertiser=%s", advertiser.id)
        return None


async def _validate_signature(db: AsyncSession, raw_body: bytes, header: str, payload: dict) -> bool:
    """Validate X-Hub-Signature-256 against every secret that could have signed
    this: the advertiser's own App Secret (manual flow) and/or the global
    META_APP_SECRET (central app / Embedded Signup). If neither is available,
    fall back to trusting the URL being unlisted (legacy behavior)."""
    # Central app / Embedded Signup: the global secret signs everything —
    # check it first and skip the DB lookup on the common path.
    if settings.META_APP_SECRET and _hmac_matches(settings.META_APP_SECRET, raw_body, header):
        return True

    # Manual self-service flow: the event is signed with the advertiser's own
    # App Secret. Only worth the DB lookup when there's a signature to check.
    per_advertiser = await _advertiser_app_secret(db, payload) if header else None
    if per_advertiser and _hmac_matches(per_advertiser, raw_body, header):
        return True

    # No secret we can check against — neither the global one nor a stored
    # per-advertiser one — fall back to trusting the URL being unlisted
    # (unchanged legacy behavior; Railway runs with META_APP_SECRET empty).
    if not settings.META_APP_SECRET and per_advertiser is None:
        return True

    return False


def _extract_body_text(msg: dict) -> tuple[str, str | None]:
    """Return (body_text, media_id) for supported message types."""
    msg_type = msg.get("type", "")
    if msg_type == "text":
        return msg.get("text", {}).get("body", "").strip(), None
    if msg_type == "audio":
        return "", msg.get("audio", {}).get("id")
    if msg_type == "button":
        btn = msg.get("button", {})
        return (btn.get("text") or btn.get("payload") or "").strip(), None
    if msg_type == "interactive":
        interactive = msg.get("interactive", {})
        itype = interactive.get("type")
        if itype == "button_reply":
            return interactive.get("button_reply", {}).get("title", "").strip(), None
        if itype == "list_reply":
            return interactive.get("list_reply", {}).get("title", "").strip(), None
        return f"[interactive:{itype}]", None
    return f"[media:{msg_type}]", None


# Meta no manda el color (GREEN/YELLOW/RED) en este webhook, solo el evento
# que lo causó — YELLOW solo se puede saber vía polling del Graph API (ver
# tasks.poll_meta_quality_ratings). FLAGGED es la señal de riesgo real.
_QUALITY_EVENT_TO_RATING = {"FLAGGED": "RED", "UNFLAGGED": "GREEN"}


async def _handle_quality_update(db: AsyncSession, waba_id: str | None, value: dict) -> None:
    if not waba_id:
        return
    result = await db.execute(select(User).where(User.meta_waba_id == waba_id))
    advertiser = result.scalar_one_or_none()
    if not advertiser:
        logger.warning("[META WEBHOOK] phone_number_quality_update for unknown WABA=%s", waba_id)
        return

    event = value.get("event", "")
    current_limit = value.get("current_limit")
    logger.warning(
        "[META WEBHOOK] Quality update advertiser=%s event=%s current_limit=%s",
        advertiser.id, event, current_limit,
    )
    await apply_quality_signal(db, advertiser, _QUALITY_EVENT_TO_RATING.get(event), current_limit)


async def _handle_account_alert(db: AsyncSession, waba_id: str | None, value: dict) -> None:
    logger.warning(
        "[META WEBHOOK] account_alerts waba=%s alert_type=%s description=%s",
        waba_id, value.get("alert_type"), value.get("alert_description"),
    )


@limiter.limit("60/minute")
async def meta_incoming(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        # Meta disables the subscription after repeated non-200s — always ack.
        logger.warning("[META WEBHOOK] Malformed JSON payload")
        return {"received": True}

    if not await _validate_signature(db, raw_body, signature, payload):
        logger.warning("[META WEBHOOK] Invalid signature")
        return {"received": True}

    for entry in payload.get("entry", []):
        waba_id = entry.get("id")
        for change in entry.get("changes", []):
            field = change.get("field")

            if field == "phone_number_quality_update":
                try:
                    await _handle_quality_update(db, waba_id, change.get("value", {}))
                except Exception:
                    logger.exception("[META WEBHOOK] Failed to process quality update")
                continue

            if field == "account_alerts":
                try:
                    await _handle_account_alert(db, waba_id, change.get("value", {}))
                except Exception:
                    logger.exception("[META WEBHOOK] Failed to process account alert")
                continue

            if field != "messages":
                continue
            value = change.get("value", {})
            phone_number_id = value.get("metadata", {}).get("phone_number_id")
            if not phone_number_id:
                continue

            for status_evt in value.get("statuses", []):
                error_code = None
                errors = status_evt.get("errors") or []
                if errors:
                    error_code = str(errors[0].get("code", ""))
                try:
                    await apply_status_update(
                        db, status_evt.get("id", ""), status_evt.get("status", ""), error_code
                    )
                except Exception:
                    logger.warning("[META WEBHOOK] Failed to apply status update", exc_info=True)

            messages = value.get("messages", [])
            if not messages:
                continue

            result = await db.execute(select(User).where(User.meta_phone_number_id == phone_number_id))
            advertiser = result.scalar_one_or_none()
            if not advertiser:
                logger.warning("[META WEBHOOK] Unknown phone_number_id=%s — dropping %d message(s)", phone_number_id, len(messages))
                continue

            token = None
            if advertiser.meta_token_cipher:
                try:
                    token = decrypt_secret(
                        EncryptedValue(
                            cipher=advertiser.meta_token_cipher,
                            iv=advertiser.meta_token_iv,
                            tag=advertiser.meta_token_tag,
                        )
                    )
                except Exception:
                    # Broad catch is deliberate: any decrypt failure should
                    # degrade to "no media download", never crash the webhook.
                    logger.error("[META WEBHOOK] Token decrypt failed for advertiser=%s", advertiser.id)

            for msg in messages:
                from_number = f"+{msg.get('from', '')}"
                wamid = msg.get("id")

                if wamid:
                    # Fired as early as possible (before the potentially-slow
                    # media download/transcription and RAG/Claude call below)
                    # to maximize how much of Meta's 25s typing-indicator
                    # window is actually visible to the customer.
                    try:
                        await send_typing_indicator(wamid, advertiser=advertiser)
                    except Exception:
                        logger.warning("[META WEBHOOK] Failed to send typing indicator", exc_info=True)

                body_text, media_id = _extract_body_text(msg)
                audio_transcription: str | None = None
                media_url: str | None = None

                if media_id and token:
                    downloaded = await download_media(media_id, token)
                    if downloaded:
                        audio_bytes, mime_type = downloaded
                        audio_transcription = await transcribe_audio_bytes(audio_bytes, mime_type)
                        # Re-host to a permanent URL — Meta's resolved media
                        # URL expires in minutes, too short-lived to store
                        # for later playback (e.g. Voces del Barrio).
                        ext = "ogg" if "ogg" in mime_type else "mp3" if "mpeg" in mime_type else "m4a"
                        media_url = await upload_bytes(
                            audio_bytes, f"wa_media/{advertiser.id}/{media_id}.{ext}", mime_type
                        )
                    body_text = audio_transcription or "[audio: transcripción no disponible]"

                inbound = InboundMessage(
                    advertiser=advertiser,
                    from_number=from_number,
                    body_text=body_text,
                    audio_transcription=audio_transcription,
                    media_url=media_url,
                    external_message_id=wamid,
                )

                async def _send(to: str, body: str) -> tuple[str | None, str | None]:
                    return await send_whatsapp(to, body, advertiser=advertiser)

                try:
                    await process_inbound_message(db, inbound, send=_send, send_owner=_send)
                except Exception:
                    logger.exception("[META WEBHOOK] Pipeline failed for advertiser=%s wamid=%s", advertiser.id, wamid)

    return {"received": True}
