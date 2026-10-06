"""Tests for app.services.meta_provisioning (Fase A: configure_app_webhook)."""
from unittest.mock import AsyncMock, patch

import pytest

from app.services.meta_client import MetaApiError
from app.services.meta_provisioning import (
    PIN_MISMATCH_CODE,
    WEBHOOK_FIELDS,
    configure_app_webhook,
    new_registration_pin,
    register_phone_number,
)


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


class TestRegisterPhoneNumber:
    @pytest.mark.asyncio
    async def test_posts_register_with_pin(self):
        with patch(
            "app.services.meta_provisioning.graph_request",
            new=AsyncMock(return_value={"success": True}),
        ) as mock_gr:
            result = await register_phone_number("phone-1", "tok", "123456")

        assert result.ok is True
        assert mock_gr.call_args.args[0] == "phone-1/register"
        kwargs = mock_gr.call_args.kwargs
        assert kwargs["token"] == "tok"
        assert kwargs["method"] == "POST"
        assert kwargs["body"] == {"messaging_product": "whatsapp", "pin": "123456"}

    @pytest.mark.asyncio
    async def test_pin_mismatch_means_already_registered(self):
        with patch(
            "app.services.meta_provisioning.graph_request",
            new=AsyncMock(side_effect=MetaApiError("Two step verification PIN mismatch", status=400, code=PIN_MISMATCH_CODE)),
        ):
            result = await register_phone_number("phone-1", "tok", "123456")
        assert result.ok is True
        assert result.data == {"already_registered": True}

    @pytest.mark.asyncio
    async def test_other_error_fails(self):
        with patch(
            "app.services.meta_provisioning.graph_request",
            new=AsyncMock(side_effect=MetaApiError("Account not verified", status=400, code=133000)),
        ):
            result = await register_phone_number("phone-1", "tok", "123456")
        assert result.ok is False
        assert result.code == "meta_error"

    @pytest.mark.asyncio
    async def test_meta_down_is_unavailable(self):
        with patch(
            "app.services.meta_provisioning.graph_request",
            new=AsyncMock(side_effect=MetaApiError("timeout", status=0)),
        ):
            result = await register_phone_number("phone-1", "tok", "123456")
        assert result.code == "meta_unavailable"

    def test_pin_is_six_digits(self):
        pins = {new_registration_pin() for _ in range(50)}
        assert all(len(p) == 6 and p.isdigit() for p in pins)
        assert len(pins) > 1
