"""
WhatsApp 24h customer-service window check.

Approximation note: this uses `Conversation.last_activity` (updated on both
inbound and outbound activity) as the window proxy, matching the existing
convention already used throughout this codebase — it is not a strict
implementation of Meta's rule (which only extends the window on
customer-initiated messages). Redesigning window tracking to track last
*inbound* activity separately is a larger change, out of scope here; this
module only centralizes the existing check so it can be enforced as a hard
gate instead of silently ignored.
"""
from datetime import datetime, timedelta, timezone

WINDOW_HOURS = 24


def is_window_open(conversation) -> bool:
    """True if `conversation` had activity within the last 24h."""
    if not conversation or not conversation.last_activity:
        return False
    return datetime.now(timezone.utc) - conversation.last_activity < timedelta(hours=WINDOW_HOURS)
