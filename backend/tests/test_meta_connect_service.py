"""Tests for app.services.meta_connect_service (test connection + subscribe app)."""
from unittest.mock import AsyncMock, patch

import pytest

from app.services.meta_client import MetaApiError
from app.services.meta_connect_service import subscribe_app_to_waba
from app.services.meta_connect_service import test_connection as check_connection


class TestTestConnection:
    @pytest.mark.asyncio
    async def test_valid_credentials_returns_ok(self):
        with patch("app.services.meta_connect_service.graph_request", new=AsyncMock(return_value={
            "display_phone_number": "+521234567890",
            "verified_name": "Mi Negocio",
        })):
            result = await check_connection("phone-id", "good-token")
            assert result.ok is True
            assert result.display_phone_number == "+521234567890"
            assert result.verified_name == "Mi Negocio"
            assert result.code is None

    @pytest.mark.asyncio
    async def test_invalid_token_maps_to_invalid_token_code(self):
        with patch("app.services.meta_connect_service.graph_request", new=AsyncMock(
            side_effect=MetaApiError("Invalid token", status=401, code=190, error_type="OAuthException")
        )):
            result = await check_connection("phone-id", "bad-token")
            assert result.ok is False
            assert result.code == "invalid_token"

    @pytest.mark.asyncio
    async def test_network_failure_maps_to_meta_unavailable(self):
        with patch("app.services.meta_connect_service.graph_request", new=AsyncMock(
            side_effect=MetaApiError("boom", status=0)
        )):
            result = await check_connection("phone-id", "tok")
            assert result.ok is False
            assert result.code == "meta_unavailable"

    @pytest.mark.asyncio
    async def test_server_error_maps_to_meta_unavailable(self):
        with patch("app.services.meta_connect_service.graph_request", new=AsyncMock(
            side_effect=MetaApiError("boom", status=503)
        )):
            result = await check_connection("phone-id", "tok")
            assert result.ok is False
            assert result.code == "meta_unavailable"

    @pytest.mark.asyncio
    async def test_other_error_maps_to_meta_error(self):
        with patch("app.services.meta_connect_service.graph_request", new=AsyncMock(
            side_effect=MetaApiError("Unsupported request", status=400, code=100)
        )):
            result = await check_connection("phone-id", "tok")
            assert result.ok is False
            assert result.code == "meta_error"

    @pytest.mark.asyncio
    async def test_missing_display_phone_number_is_meta_error(self):
        with patch("app.services.meta_connect_service.graph_request", new=AsyncMock(return_value={
            "verified_name": "Sin número"
        })):
            result = await check_connection("wrong-phone-id", "tok")
            assert result.ok is False
            assert result.code == "meta_error"

    @pytest.mark.asyncio
    async def test_no_persistence_side_effects(self):
        """test_connection must be a pure read — no db import/usage at all."""
        import app.services.meta_connect_service as mod
        assert "db" not in mod.test_connection.__code__.co_varnames


class TestSubscribeAppToWaba:
    @pytest.mark.asyncio
    async def test_success_calls_graph_request(self):
        with patch("app.services.meta_connect_service.graph_request", new=AsyncMock(return_value={"success": True})) as mock_gr:
            await subscribe_app_to_waba("waba-123", "tok")
            mock_gr.assert_called_once_with("waba-123/subscribed_apps", token="tok", method="POST")

    @pytest.mark.asyncio
    async def test_failure_is_swallowed_not_raised(self):
        with patch("app.services.meta_connect_service.graph_request", new=AsyncMock(
            side_effect=MetaApiError("boom", status=403)
        )):
            # Must not raise — best-effort by design.
            await subscribe_app_to_waba("waba-123", "tok")
