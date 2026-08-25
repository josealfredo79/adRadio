"""
Shared pytest fixtures for IaRadio backend tests.
Provides mock DB sessions, test settings, and test user factories
that work WITHOUT a real PostgreSQL database.
"""
from pathlib import Path

from dotenv import load_dotenv

# Real-DB tests must never touch production — .env.test points DATABASE_URL at a
# dedicated Neon branch instead. Loaded here, before any app.* import anywhere in
# the test session, so it overrides whatever backend/.env (production) would set.
load_dotenv(Path(__file__).resolve().parent.parent / ".env.test", override=True)

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone


@pytest.fixture
def mock_db():
    """Returns a mock AsyncSession for service-layer tests."""
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture
def test_user():
    """Returns a mock advertiser User for use in service tests."""
    from app.models.user import User

    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.email = "test@example.com"
    user.business_name = "Test Business"
    user.business_category = "restaurant"
    user.city = "Test City"
    user.country = "MX"
    user.role = "advertiser"
    user.email_verified = True
    user.subscription_status = "active"
    user.current_plan = "growth"
    user.messages_remaining = 500
    user.whatsapp_number = "+525511111111"
    user.whatsapp_number_source = "shared"
    user.language = "es"
    user.bot_personality = "professional"
    user.bot_name = "Asistente"
    user.bot_instructions = None
    user.widget_color = "#25D366"
    user.widget_greeting = "¡Hola!"
    user.widget_position = "right"
    user.white_label = {}
    user.logo_url = None
    user.phone = None
    user.stripe_customer_id = None
    user.cancel_at_period_end = False
    user.google_refresh_token = None
    user.google_calendar_connected = False
    user.plan_expires_at = None
    user.meta_waba_id = None
    user.meta_phone_number_id = None
    user.meta_display_phone_number = None
    user.meta_verified_name = None
    user.meta_token_cipher = None
    user.meta_token_iv = None
    user.meta_token_tag = None
    user.meta_connection_status = "not_connected"
    user.meta_utility_template_status = "not_configured"
    user.meta_utility_template_name = None
    user.meta_appointment_template_name = None
    user.meta_radio_invite_template_name = None
    user.meta_quality_rating = None
    user.meta_messaging_tier = None
    user.meta_send_throttle_per_hour = 60
    user.meta_connected_at = None
    return user


@pytest.fixture
def test_admin():
    """Returns a mock admin User."""
    from app.models.user import User

    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.email = "admin@iaradio.app"
    user.role = "admin"
    user.subscription_status = "active"
    user.current_plan = "enterprise"
    return user


@pytest.fixture
def mock_redis():
    """Returns a mock async Redis client."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.setex = AsyncMock()
    redis.set = AsyncMock()
    redis.delete = AsyncMock()
    redis.ping = AsyncMock(return_value=True)
    redis.keys = AsyncMock(return_value=[])
    return redis


@pytest.fixture(autouse=True)
def no_posthog():
    """Disable PostHog during tests by clearing the API key."""
    import app.services.analytics_service  # ensure module is imported before patch (Python 3.12)
    with patch("app.services.analytics_service.settings") as mock:
        mock.POSTHOG_API_KEY = ""
        yield
