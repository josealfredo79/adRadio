"""Tests for app.services.meta_service (WhatsApp Cloud API sender)."""
from unittest.mock import AsyncMock, patch

import pytest

from app.services.meta_client import MetaApiError
from app.services.meta_service import (
    send_typing_indicator,
    send_whatsapp,
    send_whatsapp_buttons,
    send_whatsapp_media,
    send_whatsapp_template,
)


def _connect(user, waba="waba-1", phone_id="phone-1", token="EAAG-fake-token"):
    """Mark a test_user fixture as connected, bypassing real encryption
    (send_whatsapp only needs _connection() to succeed, and _connection()
    calls decrypt_secret — so we patch that instead of re-encrypting)."""
    user.meta_connection_status = "connected"
    user.meta_phone_number_id = phone_id
    user.meta_token_cipher = "c"
    user.meta_token_iv = "i"
    user.meta_token_tag = "t"
    return token


class TestConnectionResolution:
    @pytest.mark.asyncio
    async def test_not_connected_advertiser_returns_error(self, test_user):
        # DEBUG=true in this test run would trigger the dev stub — force
        # settings.DEBUG False for this test to exercise the real branch.
        with patch("app.services.meta_service.settings") as mock_settings:
            mock_settings.DEBUG = False
            sid, error = await send_whatsapp("+521234567890", "hola", advertiser=test_user)
            assert sid is None
            assert error == "meta_not_connected"

    @pytest.mark.asyncio
    async def test_not_connected_in_debug_mode_returns_dev_stub(self, test_user):
        with patch("app.services.meta_service.settings") as mock_settings:
            mock_settings.DEBUG = True
            sid, error = await send_whatsapp("+521234567890", "hola", advertiser=test_user)
            assert sid == "DEV_WAMID"
            assert error is None

    @pytest.mark.asyncio
    async def test_connected_but_bad_token_decrypt_treated_as_not_connected(self, test_user):
        _connect(test_user)
        with patch("app.services.meta_service.settings") as mock_settings, \
             patch("app.services.meta_service.decrypt_secret", side_effect=Exception("bad key")):
            mock_settings.DEBUG = False
            sid, error = await send_whatsapp("+521234567890", "hola", advertiser=test_user)
            assert sid is None
            assert error == "meta_not_connected"


class TestSendWhatsapp:
    @pytest.mark.asyncio
    async def test_success_returns_wamid(self, test_user):
        token = _connect(test_user)
        with patch("app.services.meta_service.decrypt_secret", return_value=token), \
             patch("app.services.meta_service.graph_request", new=AsyncMock(
                 return_value={"messages": [{"id": "wamid.ABC123"}]}
             )) as mock_gr:
            sid, error = await send_whatsapp("+521234567890", "hola mundo", advertiser=test_user)
            assert sid == "wamid.ABC123"
            assert error is None
            call_args = mock_gr.call_args
            assert call_args.args[0] == "phone-1/messages"
            assert call_args.kwargs["token"] == token
            assert call_args.kwargs["body"]["type"] == "text"
            assert call_args.kwargs["body"]["text"]["body"] == "hola mundo"

    @pytest.mark.asyncio
    async def test_normalizes_mx_recipient(self, test_user):
        token = _connect(test_user)
        with patch("app.services.meta_service.decrypt_secret", return_value=token), \
             patch("app.services.meta_service.graph_request", new=AsyncMock(
                 return_value={"messages": [{"id": "wamid.X"}]}
             )) as mock_gr:
            await send_whatsapp("+5215599631448", "hola", advertiser=test_user)
            assert mock_gr.call_args.kwargs["body"]["to"] == "525599631448"

    @pytest.mark.asyncio
    async def test_meta_api_error_returns_none_and_message(self, test_user):
        token = _connect(test_user)
        with patch("app.services.meta_service.decrypt_secret", return_value=token), \
             patch("app.services.meta_service.graph_request", new=AsyncMock(
                 side_effect=MetaApiError("(#131047) Re-engagement message", status=400, code=131047)
             )):
            sid, error = await send_whatsapp("+521234567890", "hola", advertiser=test_user)
            assert sid is None
            assert "131047" in error


class TestSendWhatsappMedia:
    @pytest.mark.asyncio
    async def test_sends_audio_type(self, test_user):
        token = _connect(test_user)
        with patch("app.services.meta_service.decrypt_secret", return_value=token), \
             patch("app.services.meta_service.graph_request", new=AsyncMock(
                 return_value={"messages": [{"id": "wamid.AUDIO1"}]}
             )) as mock_gr:
            sid, error = await send_whatsapp_media(
                "+521234567890", "https://example.com/cuna.mp3", advertiser=test_user
            )
            assert sid == "wamid.AUDIO1"
            assert error is None
            body = mock_gr.call_args.kwargs["body"]
            assert body["type"] == "audio"
            assert body["audio"]["link"] == "https://example.com/cuna.mp3"

    @pytest.mark.asyncio
    async def test_caption_sent_as_followup_text(self, test_user):
        token = _connect(test_user)
        with patch("app.services.meta_service.decrypt_secret", return_value=token), \
             patch("app.services.meta_service.graph_request", new=AsyncMock(
                 return_value={"messages": [{"id": "wamid.AUDIO2"}]}
             )) as mock_gr:
            await send_whatsapp_media(
                "+521234567890", "https://example.com/x.mp3", body="Hola, aquí tu cuña", advertiser=test_user
            )
            # audio message + follow-up text = 2 calls
            assert mock_gr.call_count == 2
            second_call_body = mock_gr.call_args_list[1].kwargs["body"]
            assert second_call_body["type"] == "text"
            assert second_call_body["text"]["body"] == "Hola, aquí tu cuña"

    @pytest.mark.asyncio
    async def test_caption_followup_failure_does_not_fail_the_send(self, test_user):
        token = _connect(test_user)
        call_count = 0

        async def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"messages": [{"id": "wamid.AUDIO3"}]}
            raise MetaApiError("caption failed", status=500)

        with patch("app.services.meta_service.decrypt_secret", return_value=token), \
             patch("app.services.meta_service.graph_request", new=AsyncMock(side_effect=_side_effect)):
            sid, error = await send_whatsapp_media(
                "+521234567890", "https://example.com/x.mp3", body="caption", advertiser=test_user
            )
            assert sid == "wamid.AUDIO3"
            assert error is None


class TestSendWhatsappTemplate:
    @pytest.mark.asyncio
    async def test_sends_template_with_components(self, test_user):
        token = _connect(test_user)
        with patch("app.services.meta_service.decrypt_secret", return_value=token), \
             patch("app.services.meta_service.graph_request", new=AsyncMock(
                 return_value={"messages": [{"id": "wamid.TPL1"}]}
             )) as mock_gr:
            components = [{"type": "body", "parameters": [{"type": "text", "text": "Juan"}]}]
            sid, error = await send_whatsapp_template(
                "+521234567890", "utility_template", components=components, advertiser=test_user
            )
            assert sid == "wamid.TPL1"
            body = mock_gr.call_args.kwargs["body"]
            assert body["type"] == "template"
            assert body["template"]["name"] == "utility_template"
            assert body["template"]["language"] == {"code": "es_MX"}
            assert body["template"]["components"] == components


class TestSendTypingIndicator:
    """Real Meta Cloud API feature (not simulated): POST .../messages with
    status=read + typing_indicator marks the customer's message read and
    shows "escribiendo..." for up to 25s or until the real reply is sent.
    Built 2026-08-13. https://developers.facebook.com/docs/whatsapp/cloud-api/typing-indicators"""

    @pytest.mark.asyncio
    async def test_sends_read_status_and_typing_indicator(self, test_user):
        token = _connect(test_user)
        with patch("app.services.meta_service.decrypt_secret", return_value=token), \
             patch("app.services.meta_service.graph_request", new=AsyncMock(return_value={})) as mock_gr:
            await send_typing_indicator("wamid.INCOMING123", advertiser=test_user)
            assert mock_gr.call_args.args[0] == "phone-1/messages"
            body = mock_gr.call_args.kwargs["body"]
            assert body["status"] == "read"
            assert body["message_id"] == "wamid.INCOMING123"
            assert body["typing_indicator"] == {"type": "text"}

    @pytest.mark.asyncio
    async def test_not_connected_is_a_silent_noop(self, test_user):
        with patch("app.services.meta_service.settings") as mock_settings:
            mock_settings.DEBUG = False
            # Must not raise — this is a best-effort UX nicety, never worth
            # failing the real reply over.
            await send_typing_indicator("wamid.X", advertiser=test_user)

    @pytest.mark.asyncio
    async def test_meta_api_error_is_swallowed(self, test_user):
        token = _connect(test_user)
        with patch("app.services.meta_service.decrypt_secret", return_value=token), \
             patch("app.services.meta_service.graph_request", new=AsyncMock(
                 side_effect=MetaApiError("boom", status=500)
             )):
            # Must not raise.
            await send_typing_indicator("wamid.X", advertiser=test_user)


class TestSendWhatsappButtons:
    @pytest.mark.asyncio
    async def test_falls_back_to_plain_text_without_template(self, test_user):
        token = _connect(test_user)
        with patch("app.services.meta_service.decrypt_secret", return_value=token), \
             patch("app.services.meta_service.graph_request", new=AsyncMock(
                 return_value={"messages": [{"id": "wamid.PLAIN"}]}
             )) as mock_gr:
            sid, error = await send_whatsapp_buttons(
                "+521234567890", "texto plano de respaldo", template_name="", advertiser=test_user
            )
            assert sid == "wamid.PLAIN"
            assert mock_gr.call_args.kwargs["body"]["type"] == "text"

    @pytest.mark.asyncio
    async def test_uses_template_when_configured(self, test_user):
        token = _connect(test_user)
        with patch("app.services.meta_service.decrypt_secret", return_value=token), \
             patch("app.services.meta_service.graph_request", new=AsyncMock(
                 return_value={"messages": [{"id": "wamid.BTN"}]}
             )) as mock_gr:
            sid, error = await send_whatsapp_buttons(
                "+521234567890", "fallback", template_name="appt_confirm", advertiser=test_user
            )
            assert sid == "wamid.BTN"
            assert mock_gr.call_args.kwargs["body"]["type"] == "template"
            assert mock_gr.call_args.kwargs["body"]["template"]["name"] == "appt_confirm"
