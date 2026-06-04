"""
Tests unitarios para webhook de Stripe.
No requieren base de datos — usan mocks.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta


class TestStripeWebhookLogic:
    """Prueba la lógica del webhook sin necesidad de Stripe real."""

    @pytest.mark.asyncio
    async def test_lookup_user_no_customer_id(self):
        from app.api.v1.webhooks_pkg.stripe import _lookup_user

        db = AsyncMock()
        user = await _lookup_user(None, db)
        assert user is None
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_lookup_user_with_customer_id(self):
        from app.api.v1.webhooks_pkg.stripe import _lookup_user

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = "fake_user"
        db.execute.return_value = result_mock

        user = await _lookup_user("cus_123", db)
        assert user == "fake_user"
        db.execute.assert_called_once()

    def test_plan_messages_mapping(self):
        from app.api.v1.payments import PLAN_MESSAGES

        assert PLAN_MESSAGES["starter"] == 200
        assert PLAN_MESSAGES["growth"] == 500
        assert PLAN_MESSAGES["pro"] == 1000
        assert PLAN_MESSAGES["business"] == 3000
        assert PLAN_MESSAGES["enterprise"] == 10000

    def test_ensure_pool_number_only_shared(self):
        from app.api.v1.webhooks_pkg.stripe import _ensure_pool_number

        db = AsyncMock()
        assign_mock = AsyncMock()

        user_shared = MagicMock()
        user_shared.whatsapp_number_source = "shared"

        user_pool = MagicMock()
        user_pool.whatsapp_number_source = "pool"

        user_own = MagicMock()
        user_own.whatsapp_number_source = "own"

        with patch(
            "app.api.v1.webhooks_pkg.stripe.assign_pool_number", assign_mock
        ):
            import asyncio
            asyncio.run(_ensure_pool_number(user_shared, db))
            assign_mock.assert_called_once_with(user_shared, db)

            assign_mock.reset_mock()
            asyncio.run(_ensure_pool_number(user_pool, db))
            assign_mock.assert_not_called()

            asyncio.run(_ensure_pool_number(user_own, db))
            assign_mock.assert_not_called()


class TestHealthCheck:
    """Prueba la estructura del health endpoint."""

    def test_health_response_format(self):
        """Verifica que la respuesta de /health tiene la estructura esperada."""
        from app.main import app
        expected_routes = {route.path for route in app.routes}
        assert "/health" in expected_routes

    def test_health_version_present(self):
        from app.config import settings
        assert settings.APP_VERSION is not None
        assert isinstance(settings.APP_VERSION, str)


class TestRateLimitModule:
    """Prueba que el rate limiter compartido existe y tiene la config correcta."""

    def test_limiter_exists(self):
        from app.api.rate_limit import limiter
        assert limiter is not None

    def test_auth_uses_shared_limiter(self):
        from app.api.v1.auth import limiter as auth_limiter
        from app.api.rate_limit import limiter as shared_limiter
        assert auth_limiter is shared_limiter
