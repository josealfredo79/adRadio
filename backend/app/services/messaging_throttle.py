"""
Channel-agnostic outbound pacing helpers (used by campaign/appointment jobs
to stay under WhatsApp rate limits regardless of which API sends the message).
"""
import random


def anti_ban_delay() -> int:
    """Return a human-paced random delay in seconds to stay under WhatsApp rate limits.

    Strategy:
    - 70% of the time: 45-90s (normal human typing pace)
    - 20% of the time: 90-180s (longer pause, feels more natural)
    - 10% of the time: 180-300s (extra-long gap to break patterns)
    This keeps us well under 60 msgs/hour on average.
    """
    roll = random.random()
    if roll < 0.70:
        return random.randint(45, 90)
    elif roll < 0.90:
        return random.randint(90, 180)
    else:
        return random.randint(180, 300)


def is_human_hour(timezone_offset: int = -6) -> bool:
    """Check if current time is within 8am-9pm in given UTC offset."""
    from datetime import datetime, timezone, timedelta
    tz = timezone(timedelta(hours=timezone_offset))
    now = datetime.now(tz)
    return 8 <= now.hour < 21
