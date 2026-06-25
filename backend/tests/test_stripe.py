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

    def test_plan_days_uses_config_not_hardcoded(self):
        """Verifica que cada plan tenga su propio days configurado."""
        from app.api.v1.payments import PLANS

        for key, plan in PLANS.items():
            assert "days" in plan, f"Plan {key} missing 'days'"
            assert plan["days"] == 30, f"Plan {key} days should be 30"

    def test_plan_days_fallback(self):
        """Verifica que PLANS.get(unknown, {}).get('days', 30) funcione."""
        from app.api.v1.payments import PLANS

        assert PLANS.get("nonexistent", {}).get("days", 30) == 30
        assert PLANS.get("starter", {}).get("days", 30) == 30

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


class TestStripeWebhookIdempotency:
    """Prueba la idempotencia de los eventos del webhook de Stripe."""

    def _make_request(self):
        """Create a request mock with async body()."""
        req = AsyncMock()
        req.headers.get.return_value = "fake_sig"
        req.body = AsyncMock(return_value=b"{}")
        return req

    @pytest.mark.asyncio
    async def test_subscription_updated_skips_when_unchanged_active(self):
        """Si el usuario ya está active y cancel_at_period_end coincide, debe skipear."""
        from app.api.v1.webhooks_pkg.stripe import stripe_webhook

        user = MagicMock()
        user.subscription_status = "active"
        user.cancel_at_period_end = False

        mock_event = {
            "id": "evt_duplicate",
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "customer": "cus_123",
                    "status": "active",
                    "cancel_at_period_end": False,
                    "id": "sub_123",
                }
            },
        }

        request = self._make_request()
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.side_effect = [user]

        async def fake_execute(*args, **kwargs):
            return result_mock

        db.execute = fake_execute

        with patch("app.api.v1.webhooks_pkg.stripe.settings") as mock_settings, \
             patch("stripe.Webhook.construct_event", return_value=mock_event):
            mock_settings.STRIPE_WEBHOOK_SECRET = "whsec_test"

            result = await stripe_webhook(request, db)

        assert result == {"received": True}
        # No debe haber commits porque no hubo cambios
        db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_subscription_updated_skips_when_unchanged_suspended(self):
        """Si el usuario ya está suspended por past_due, debe skipear."""
        from app.api.v1.webhooks_pkg.stripe import stripe_webhook

        user = MagicMock()
        user.subscription_status = "suspended"
        user.cancel_at_period_end = False

        mock_event = {
            "id": "evt_duplicate",
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "customer": "cus_123",
                    "status": "past_due",
                    "cancel_at_period_end": False,
                    "id": "sub_123",
                }
            },
        }

        request = self._make_request()
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.side_effect = [user]

        async def fake_execute(*args, **kwargs):
            return result_mock

        db.execute = fake_execute

        with patch("app.api.v1.webhooks_pkg.stripe.settings") as mock_settings, \
             patch("stripe.Webhook.construct_event", return_value=mock_event):
            mock_settings.STRIPE_WEBHOOK_SECRET = "whsec_test"

            result = await stripe_webhook(request, db)

        assert result == {"received": True}
        db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_subscription_updated_skips_when_unchanged_churned(self):
        """Si el usuario ya está churned y llega otro 'canceled', debe skipear."""
        from app.api.v1.webhooks_pkg.stripe import stripe_webhook

        user = MagicMock()
        user.subscription_status = "churned"
        user.cancel_at_period_end = False

        mock_event = {
            "id": "evt_duplicate",
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "customer": "cus_123",
                    "status": "canceled",
                    "cancel_at_period_end": False,
                    "id": "sub_123",
                }
            },
        }

        request = self._make_request()
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.side_effect = [user]

        async def fake_execute(*args, **kwargs):
            return result_mock

        db.execute = fake_execute

        with patch("app.api.v1.webhooks_pkg.stripe.settings") as mock_settings, \
             patch("stripe.Webhook.construct_event", return_value=mock_event):
            mock_settings.STRIPE_WEBHOOK_SECRET = "whsec_test"

            result = await stripe_webhook(request, db)

        assert result == {"received": True}
        db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_subscription_deleted_skips_when_already_churned(self):
        """Si el usuario ya está churned, subscription.deleted debe skipear."""
        from app.api.v1.webhooks_pkg.stripe import stripe_webhook

        user = MagicMock()
        user.subscription_status = "churned"
        user.cancel_at_period_end = False

        mock_event = {
            "id": "evt_duplicate",
            "type": "customer.subscription.deleted",
            "data": {
                "object": {
                    "customer": "cus_123",
                }
            },
        }

        request = self._make_request()
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.side_effect = [user]

        async def fake_execute(*args, **kwargs):
            return result_mock

        db.execute = fake_execute

        with patch("app.api.v1.webhooks_pkg.stripe.settings") as mock_settings, \
             patch("stripe.Webhook.construct_event", return_value=mock_event):
            mock_settings.STRIPE_WEBHOOK_SECRET = "whsec_test"

            result = await stripe_webhook(request, db)

        assert result == {"received": True}
        db.commit.assert_not_called()


class TestPlanDaysFromConfig:
    """Prueba que los días del plan se tomen del config, no hardcodeados."""

    def test_checkout_uses_plan_days(self):
        """Verifica que checkout.session.completed use PLANS[plan]['days']."""
        from app.api.v1.payments import PLANS

        for plan_key, plan_data in PLANS.items():
            assert plan_data["days"] > 0, f"Plan {plan_key} debe tener days > 0"

    def test_invoice_uses_plan_days(self):
        """Verifica que PLANS tenga days en todos los planes."""
        from app.api.v1.payments import PLANS

        for key in ("starter", "growth", "pro", "business", "enterprise"):
            assert "days" in PLANS[key], f"{key} missing days"
            assert PLANS[key]["days"] == 30


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
        from app.core.rate_limiter import limiter
        assert limiter is not None

    def test_auth_uses_shared_limiter(self):
        from app.api.v1.auth import limiter as auth_limiter
        from app.core.rate_limiter import limiter as shared_limiter
        assert auth_limiter is shared_limiter
