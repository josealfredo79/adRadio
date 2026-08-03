"""Tests for app.services.meta_oauth_service (Embedded Signup code exchange)."""
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.services.meta_connect_service import ConnectionCheck
from app.services.meta_oauth_service import exchange_embedded_code


def _resp(status: int, payload: dict) -> Mock:
    r = Mock()
    r.status_code = status
    r.is_error = status >= 400
    r.json.return_value = payload
    return r


@pytest.fixture
def oauth_settings():
    with patch("app.services.meta_oauth_service.settings") as mock_settings:
        mock_settings.META_APP_ID = "123456"
        mock_settings.META_APP_SECRET = "secret123"
        mock_settings.META_GRAPH_BASE_URL = "https://graph.facebook.com"
        mock_settings.META_GRAPH_API_VERSION = "v21.0"
        yield mock_settings


@pytest.mark.asyncio
async def test_missing_app_config_returns_missing_config(oauth_settings):
    oauth_settings.META_APP_ID = ""
    result = await exchange_embedded_code("code", "waba-1", "phone-1")
    assert result.ok is False
    assert result.code == "missing_config"


@pytest.mark.asyncio
async def test_meta_error_on_exchange_returns_exchange_failed(oauth_settings):
    with patch("app.services.meta_oauth_service.httpx.AsyncClient") as mock_client_cls:
        mock_client = mock_client_cls.return_value.__aenter__.return_value
        mock_client.get.return_value = _resp(
            400, {"error": {"message": "Error validating verification code", "code": 400}}
        )
        result = await exchange_embedded_code("bad-code", "waba-1", "phone-1")
        assert result.ok is False
        assert result.code == "exchange_failed"
        assert "Error validating" in result.message


@pytest.mark.asyncio
async def test_success_exchanges_and_validates(oauth_settings):
    with patch("app.services.meta_oauth_service.httpx.AsyncClient") as mock_client_cls, \
            patch("app.services.meta_connect_service.test_connection", new=AsyncMock(return_value=ConnectionCheck(
                ok=True, display_phone_number="+521234567890", verified_name="Mi Negocio",
            ))):
        mock_client = mock_client_cls.return_value.__aenter__.return_value
        mock_client.get.return_value = _resp(200, {"access_token": "EAAGlongtoken"})

        result = await exchange_embedded_code("code", "waba-1", "phone-1")

        assert result.ok is True
        assert result.token == "EAAGlongtoken"
        assert result.display_phone_number == "+521234567890"

        # Must call the token endpoint with app credentials + code.
        call_kwargs = mock_client.get.call_args
        assert call_kwargs[1]["params"]["client_id"] == "123456"
        assert call_kwargs[1]["params"]["client_secret"] == "secret123"
        assert call_kwargs[1]["params"]["code"] == "code"


@pytest.mark.asyncio
async def test_validated_number_rejected_propagates(oauth_settings):
    with patch("app.services.meta_oauth_service.httpx.AsyncClient") as mock_client_cls, \
            patch("app.services.meta_connect_service.test_connection", new=AsyncMock(return_value=ConnectionCheck(
                ok=False, code="invalid_token", message="El token no es válido",
            ))):
        mock_client = mock_client_cls.return_value.__aenter__.return_value
        mock_client.get.return_value = _resp(200, {"access_token": "EAAGlongtoken"})

        result = await exchange_embedded_code("code", "waba-1", "phone-1")
        assert result.ok is False
        assert result.code == "invalid_token"
