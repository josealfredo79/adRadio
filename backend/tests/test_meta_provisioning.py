"""Tests for app.services.meta_provisioning (Fase A: configure_app_webhook)."""
from unittest.mock import AsyncMock, patch

import pytest

from app.services.meta_client import MetaApiError
from app.services.meta_provisioning import WEBHOOK_FIELDS, configure_app_webhook


class TestConfigureAppWebhook:
    @pytest.mark.asyncio
    async def test_success_posts_subscription_with_app_access_token(self):
        with patch(
            "app.services.meta_provisioning.graph_request",
            new=AsyncMock(return_value={"success": True}),
        ) as mock_gr, patch("app.services.meta_provisioning.settings") as mock_settings:
            mock_settings.BASE_URL = "https://api.iaradio.online"
            mock_settings.META_WEBHOOK_VERIFY_TOKEN = "verify-tok"

            result = await configure_app_webhook("111222333", "the-secret")

            assert result.ok is True
            path, kwargs = mock_gr.call_args.args[0], mock_gr.call_args.kwargs
            assert path == "111222333/subscriptions"
            assert kwargs["token"] == "111222333|the-secret"
            assert kwargs["method"] == "POST"
            assert kwargs["params"]["object"] == "whatsapp_business_account"
            assert kwargs["params"]["callback_url"] == "https://api.iaradio.online/api/v1/webhooks/meta"
            assert kwargs["params"]["verify_token"] == "verify-tok"
            assert kwargs["params"]["fields"] == WEBHOOK_FIELDS

    @pytest.mark.asyncio
    async def test_bad_credentials_maps_to_invalid_credentials(self):
        with patch(
            "app.services.meta_provisioning.graph_request",
            new=AsyncMock(side_effect=MetaApiError("bad", status=401, code=190, error_type="OAuthException")),
        ), patch("app.services.meta_provisioning.settings") as mock_settings:
            mock_settings.BASE_URL = "https://api.iaradio.online"
            mock_settings.META_WEBHOOK_VERIFY_TOKEN = "v"
            result = await configure_app_webhook("app", "wrong")
            assert result.ok is False
            assert result.code == "invalid_credentials"

    @pytest.mark.asyncio
    async def test_network_failure_maps_to_meta_unavailable(self):
        with patch(
            "app.services.meta_provisioning.graph_request",
            new=AsyncMock(side_effect=MetaApiError("boom", status=0)),
        ), patch("app.services.meta_provisioning.settings") as mock_settings:
            mock_settings.BASE_URL = "https://api.iaradio.online"
            mock_settings.META_WEBHOOK_VERIFY_TOKEN = "v"
            result = await configure_app_webhook("app", "sec")
            assert result.ok is False
            assert result.code == "meta_unavailable"

    @pytest.mark.asyncio
    async def test_success_false_in_response_is_meta_error(self):
        with patch(
            "app.services.meta_provisioning.graph_request",
            new=AsyncMock(return_value={"success": False}),
        ), patch("app.services.meta_provisioning.settings") as mock_settings:
            mock_settings.BASE_URL = "https://api.iaradio.online"
            mock_settings.META_WEBHOOK_VERIFY_TOKEN = "v"
            result = await configure_app_webhook("app", "sec")
            assert result.ok is False
            assert result.code == "meta_error"
