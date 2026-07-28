"""Tests for app.services.meta_client (thin WhatsApp Cloud API HTTP client)."""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.meta_client import MetaApiError, download_media, graph_request, normalize_recipient


def _mock_response(status_code=200, json_data=None, is_error=False):
    resp = MagicMock()
    resp.status_code = status_code
    resp.is_error = is_error
    resp.json.return_value = json_data or {}
    return resp


class TestGraphRequest:
    @pytest.mark.asyncio
    async def test_success_returns_json_body(self):
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.request.return_value = _mock_response(
                200, {"display_phone_number": "+521234567890"}
            )
            data = await graph_request("123/messages", token="tok")
            assert data == {"display_phone_number": "+521234567890"}

    @pytest.mark.asyncio
    async def test_sends_bearer_token_header(self):
        with patch("httpx.AsyncClient") as mock_client:
            request_mock = mock_client.return_value.__aenter__.return_value.request
            request_mock.return_value = _mock_response(200, {})
            await graph_request("123", token="my-secret-token")
            _, kwargs = request_mock.call_args
            assert kwargs["headers"]["Authorization"] == "Bearer my-secret-token"

    @pytest.mark.asyncio
    async def test_error_response_raises_meta_api_error(self):
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.request.return_value = _mock_response(
                401,
                {"error": {"message": "Invalid OAuth access token", "code": 190, "type": "OAuthException"}},
                is_error=True,
            )
            with pytest.raises(MetaApiError) as exc_info:
                await graph_request("123", token="bad-token")
            err = exc_info.value
            assert err.status == 401
            assert err.code == 190
            assert err.error_type == "OAuthException"
            assert err.is_auth_error is True

    @pytest.mark.asyncio
    async def test_network_error_raises_meta_api_error_status_zero(self):
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.request = AsyncMock(
                side_effect=httpx.ConnectError("boom")
            )
            with pytest.raises(MetaApiError) as exc_info:
                await graph_request("123", token="tok")
            assert exc_info.value.status == 0

    @pytest.mark.asyncio
    async def test_non_json_body_treated_as_empty_dict_on_error(self):
        with patch("httpx.AsyncClient") as mock_client:
            resp = _mock_response(500, is_error=True)
            resp.json.side_effect = ValueError("not json")
            mock_client.return_value.__aenter__.return_value.request.return_value = resp
            with pytest.raises(MetaApiError) as exc_info:
                await graph_request("123", token="tok")
            assert exc_info.value.status == 500


class TestMetaApiErrorIsAuthError:
    def test_status_401_is_auth_error(self):
        assert MetaApiError("x", status=401).is_auth_error is True

    def test_code_190_is_auth_error(self):
        assert MetaApiError("x", status=400, code=190).is_auth_error is True

    def test_oauth_exception_type_is_auth_error(self):
        assert MetaApiError("x", status=400, error_type="OAuthException").is_auth_error is True

    def test_other_errors_not_auth_error(self):
        assert MetaApiError("x", status=500, code=1).is_auth_error is False


class TestNormalizeRecipient:
    def test_strips_extra_1_from_mx_number(self):
        assert normalize_recipient("+5215599631448") == "525599631448"

    def test_leaves_number_without_extra_1_unchanged(self):
        assert normalize_recipient("+525599631448") == "525599631448"

    def test_leaves_non_mx_number_unchanged(self):
        assert normalize_recipient("+14155551234") == "14155551234"

    def test_strips_spaces(self):
        assert normalize_recipient("+52 1 55 9963 1448") == "525599631448"


class TestDownloadMedia:
    @pytest.mark.asyncio
    async def test_success_returns_bytes_and_mime_type(self):
        with patch("app.services.meta_client.graph_request", new=AsyncMock(return_value={
            "url": "https://lookaside.fbsbx.com/whatsapp_business/attachments/xyz",
            "mime_type": "audio/ogg",
        })):
            with patch("httpx.AsyncClient") as mock_client:
                media_resp = MagicMock()
                media_resp.content = b"fake-audio-bytes"
                media_resp.raise_for_status = MagicMock()
                mock_client.return_value.__aenter__.return_value.get.return_value = media_resp

                result = await download_media("media-id-123", "tok")
                assert result == (b"fake-audio-bytes", "audio/ogg")

    @pytest.mark.asyncio
    async def test_resolve_failure_returns_none(self):
        with patch("app.services.meta_client.graph_request", new=AsyncMock(
            side_effect=MetaApiError("not found", status=404)
        )):
            result = await download_media("bad-id", "tok")
            assert result is None

    @pytest.mark.asyncio
    async def test_missing_url_in_response_returns_none(self):
        with patch("app.services.meta_client.graph_request", new=AsyncMock(return_value={"mime_type": "audio/ogg"})):
            result = await download_media("media-id", "tok")
            assert result is None

    @pytest.mark.asyncio
    async def test_download_http_error_returns_none(self):
        with patch("app.services.meta_client.graph_request", new=AsyncMock(return_value={
            "url": "https://example.com/x", "mime_type": "audio/ogg",
        })):
            with patch("httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                    side_effect=httpx.HTTPError("boom")
                )
                result = await download_media("media-id", "tok")
                assert result is None
