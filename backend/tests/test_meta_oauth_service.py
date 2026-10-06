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


def _exchange_ok(mock_client_cls):
    mock_client = mock_client_cls.return_value.__aenter__.return_value
    mock_client.get.return_value = _resp(200, {"access_token": "EAAGlongtoken"})


_VALID = ConnectionCheck(ok=True, display_phone_number="+521234567890", verified_name="Mi Negocio")


@pytest.mark.asyncio
async def test_missing_ids_are_read_from_the_token(oauth_settings):
    graph = AsyncMock(side_effect=[
        {"data": {"granular_scopes": [
            {"scope": "whatsapp_business_messaging", "target_ids": ["waba-7"]},
            {"scope": "whatsapp_business_management", "target_ids": ["waba-7"]},
        ]}},
        {"data": [{"id": "phone-7"}]},
    ])
    with patch("app.services.meta_oauth_service.httpx.AsyncClient") as mock_client_cls, \
            patch("app.services.meta_oauth_service.graph_request", new=graph), \
            patch("app.services.meta_connect_service.test_connection", new=AsyncMock(return_value=_VALID)) as mock_test:
        _exchange_ok(mock_client_cls)
        result = await exchange_embedded_code("code", "", "")

    assert result.ok is True
    assert (result.waba_id, result.phone_number_id) == ("waba-7", "phone-7")
    debug_call, phones_call = graph.await_args_list
    assert debug_call.args[0] == "debug_token"
    assert debug_call.kwargs["token"] == "123456|secret123"
    assert debug_call.kwargs["params"] == {"input_token": "EAAGlongtoken"}
    assert phones_call.args[0] == "waba-7/phone_numbers"
    mock_test.assert_awaited_with("phone-7", "EAAGlongtoken")


@pytest.mark.asyncio
async def test_ids_from_signup_window_skip_the_lookup(oauth_settings):
    graph = AsyncMock()
    with patch("app.services.meta_oauth_service.httpx.AsyncClient") as mock_client_cls, \
            patch("app.services.meta_oauth_service.graph_request", new=graph), \
            patch("app.services.meta_connect_service.test_connection", new=AsyncMock(return_value=_VALID)):
        _exchange_ok(mock_client_cls)
        result = await exchange_embedded_code("code", "waba-1", "phone-1")
    assert (result.waba_id, result.phone_number_id) == ("waba-1", "phone-1")
    graph.assert_not_awaited()


@pytest.mark.asyncio
async def test_several_wabas_is_no_waba(oauth_settings):
    graph = AsyncMock(return_value={"data": {"granular_scopes": [
        {"scope": "whatsapp_business_management", "target_ids": ["waba-1", "waba-2"]},
    ]}})
    with patch("app.services.meta_oauth_service.httpx.AsyncClient") as mock_client_cls, \
            patch("app.services.meta_oauth_service.graph_request", new=graph):
        _exchange_ok(mock_client_cls)
        result = await exchange_embedded_code("code", "", "")
    assert result.ok is False
    assert result.code == "no_waba"


@pytest.mark.asyncio
async def test_waba_without_number_is_no_phone(oauth_settings):
    # FINISH_ONLY_WABA: the customer created the WABA but added no number.
    graph = AsyncMock(return_value={"data": []})
    with patch("app.services.meta_oauth_service.httpx.AsyncClient") as mock_client_cls, \
            patch("app.services.meta_oauth_service.graph_request", new=graph):
        _exchange_ok(mock_client_cls)
        result = await exchange_embedded_code("code", "waba-1", "")
    assert result.ok is False
    assert result.code == "no_phone"
    graph.assert_awaited_once()
    assert graph.await_args.args[0] == "waba-1/phone_numbers"
