"""Capa 16 anti-baneo: `_offer_or_send_radio_audio` (campaign_ops.py).

Real-world finding (2026-08-25): sending an approved template does NOT
reopen the 24h customer-service window for a follow-up free-form message —
only a real customer reply does (verified live: Meta rejected a follow-up
audio send with error 131047 right after a successful template send, twice,
14+ minutes apart). This is the fix for the radio/audio campaign path: when
the window is closed, offer the audio via an opt-in template (Sí/Ahora no
buttons) and stop — don't send the audio in the same pass.

Mirrors tests/test_whatsapp_window_hard_block.py's style for the sibling
`_ensure_conversation_window` function.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.workers.task_helpers.campaign_ops import _offer_or_send_radio_audio


def _conv(hours_ago: float | None):
    if hours_ago is None:
        return None
    conv = MagicMock()
    conv.last_activity = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return conv


def _campaign():
    return MagicMock(id="camp1")


class TestOpenWindowDispatchesViaCelery:
    @pytest.mark.asyncio
    async def test_open_window_dispatches_audio_task_not_a_direct_send(self, mock_db, test_user):
        contact = MagicMock(id="c1", phone="+521234567890", name="Juan")
        convs = {"c1": _conv(1)}  # window open

        with patch(
            "app.workers.tasks.send_whatsapp_voice_note.apply_async",
        ) as mock_apply_async, patch(
            "app.services.meta_service.send_whatsapp_template",
        ) as mock_template:
            outcome, sid, error = await _offer_or_send_radio_audio(
                mock_db, test_user, contact, "https://x/audio.ogg", "script", _campaign(), ban_delay=5,
                _convs=convs,
            )

        assert outcome == "sent"
        mock_apply_async.assert_called_once()
        # Real content send is queued with the given ban_delay, not fired synchronously.
        assert mock_apply_async.call_args.kwargs["countdown"] == 5
        mock_template.assert_not_called()


class TestClosedWindowOffersInsteadOfSending:
    @pytest.mark.asyncio
    async def test_closed_window_no_invite_template_configured_blocks(self, mock_db, test_user):
        contact = MagicMock(id="c1", phone="+521234567890", name="Juan", consent_status="confirmed")
        convs = {"c1": _conv(30)}  # window closed
        test_user.meta_radio_invite_template_name = None

        with patch("app.services.meta_service.send_whatsapp_template") as mock_template:
            outcome, sid, error = await _offer_or_send_radio_audio(
                mock_db, test_user, contact, "https://x/audio.ogg", "script", _campaign(), ban_delay=0,
                _convs=convs,
            )

        assert outcome == "blocked"
        mock_template.assert_not_called()

    @pytest.mark.asyncio
    async def test_closed_window_unconfirmed_consent_blocks_even_with_template(self, mock_db, test_user):
        contact = MagicMock(id="c1", phone="+521234567890", name="Juan", consent_status="unconfirmed")
        convs = {"c1": _conv(30)}
        test_user.meta_radio_invite_template_name = "iaradio_audio_disponible"

        with patch(
            "app.services.meta_service.send_whatsapp_template",
            new=AsyncMock(return_value=("wamid.OK", None)),
        ) as mock_send:
            outcome, sid, error = await _offer_or_send_radio_audio(
                mock_db, test_user, contact, "https://x/audio.ogg", "script", _campaign(), ban_delay=0,
                _convs=convs,
            )

        assert outcome == "blocked"
        mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_closed_window_template_send_fails_blocks(self, mock_db, test_user):
        contact = MagicMock(id="c1", phone="+521234567890", name="Juan", consent_status="confirmed")
        convs = {"c1": _conv(30)}
        test_user.meta_radio_invite_template_name = "iaradio_audio_disponible"

        with patch(
            "app.services.meta_service.send_whatsapp_template",
            new=AsyncMock(return_value=(None, "template rejected")),
        ):
            outcome, sid, error = await _offer_or_send_radio_audio(
                mock_db, test_user, contact, "https://x/audio.ogg", "script", _campaign(), ban_delay=0,
                _convs=convs,
            )

        assert outcome == "blocked"

    @pytest.mark.asyncio
    async def test_closed_window_template_succeeds_offers_and_defers_audio(self, mock_db, test_user):
        """The key fix under test: a successful template send must NOT be
        treated as "window open, send the audio now" — it must return
        "invited" (audio deferred) and queue a [AUDIO-PENDING] Message for
        inbound_pipeline.py to fulfill once the contact actually replies."""
        contact = MagicMock(id="c1", phone="+521234567890", name="Juan", consent_status="confirmed")
        convs = {"c1": None}  # no conversation yet, window closed
        test_user.meta_radio_invite_template_name = "iaradio_audio_disponible"

        with patch(
            "app.services.meta_service.send_whatsapp_template",
            new=AsyncMock(return_value=("wamid.TEMPLATE", None)),
        ) as mock_template, patch(
            "app.workers.tasks.send_whatsapp_voice_note.apply_async",
        ) as mock_apply_async:
            outcome, sid, error = await _offer_or_send_radio_audio(
                mock_db, test_user, contact, "https://x/audio.ogg", "script", _campaign(), ban_delay=0,
                _convs=convs,
            )

        assert outcome == "invited"
        mock_template.assert_called_once()
        # The audio itself must NOT be dispatched in this same pass.
        mock_apply_async.assert_not_called()

        queued_messages = [
            call.args[0] for call in mock_db.add.call_args_list
            if hasattr(call.args[0], "content") and str(call.args[0].content).startswith("[AUDIO-PENDING]")
        ]
        assert len(queued_messages) == 1
        assert queued_messages[0].status == "queued"
        assert queued_messages[0].content == "[AUDIO-PENDING] https://x/audio.ogg"

    @pytest.mark.asyncio
    async def test_open_window_reaches_unconfirmed_contact_anyway(self, mock_db, test_user):
        """Consent gate only blocks the cold-window offer path — a contact
        who already has an open window is unaffected regardless of
        consent_status, same precedent as _ensure_conversation_window."""
        contact = MagicMock(id="c1", phone="+521234567890", name="Juan", consent_status="unconfirmed")
        convs = {"c1": _conv(1)}  # window open

        with patch("app.workers.tasks.send_whatsapp_voice_note.apply_async") as mock_apply_async:
            outcome, sid, error = await _offer_or_send_radio_audio(
                mock_db, test_user, contact, "https://x/audio.ogg", "script", _campaign(), ban_delay=0,
                _convs=convs,
            )

        assert outcome == "sent"
        mock_apply_async.assert_called_once()
