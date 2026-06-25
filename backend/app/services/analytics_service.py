"""
PostHog analytics tracking service.
Captures key business events for product analytics.
"""
import logging
from typing import Any
from uuid import UUID

import posthog

from app.config import settings

logger = logging.getLogger(__name__)

_initialized = False


def _ensure_init():
    global _initialized
    if not _initialized and settings.POSTHOG_API_KEY:
        posthog.project_api_key = settings.POSTHOG_API_KEY
        posthog.host = "https://app.posthog.com"
        _initialized = True


def capture_event(
    event: str,
    user_id: str | UUID | None = None,
    properties: dict[str, Any] | None = None,
    distinct_id: str | None = None,
):
    if not settings.POSTHOG_API_KEY:
        return
    _ensure_init()
    try:
        pid = distinct_id or (str(user_id) if user_id else "anonymous")
        posthog.capture(
            distinct_id=pid,
            event=event,
            properties=properties or {},
        )
    except Exception:
        logger.debug("PostHog capture failed for event=%s", event, exc_info=True)


def identify_user(user_id: str | UUID, traits: dict[str, Any] | None = None):
    if not settings.POSTHOG_API_KEY:
        return
    _ensure_init()
    try:
        posthog.identify(distinct_id=str(user_id), properties=traits or {})
    except Exception:
        logger.debug("PostHog identify failed for user=%s", user_id, exc_info=True)


def flush():
    if _initialized:
        try:
            posthog.flush()
        except Exception:
            pass
