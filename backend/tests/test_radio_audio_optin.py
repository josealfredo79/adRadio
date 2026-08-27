"""Capa 16 anti-baneo: `send_radio_messages`'s open/invited branching
(campaign_ops.py).

Real-world finding (2026-08-25): sending an approved template does NOT
reopen the 24h customer-service window for a follow-up free-form message —
only a real customer reply does (verified live: Meta rejected a follow-up
audio send with error 131047 right after a successful template send, twice,
14+ minutes apart). The fix lives in the shared `_offer_or_queue` gate (see
tests/test_whatsapp_window_hard_block.py for its own unit tests) — this file
covers what `send_radio_messages` does with each of its outcomes: dispatch
the audio via Celery when the window's already "open", or defer it as a
`[PENDING:audio]` Message when the gate only managed to send an "invited"
opt-in template.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.workers.task_helpers.campaign_ops import send_radio_messages


def _contact():
    return MagicMock(
        id="c1", phone="+521234567890", name="Juan", status="active",
        suppressed_until=None, last_campaign_sent_at=None, last_interaction=None,
        engagement_score=0,
    )


def _campaign(test_user):
    return MagicMock(id="camp1", advertiser_id=test_user.id)


class TestOpenWindowDispatchesViaCelery:
    @pytest.mark.asyncio
    async def test_open_outcome_dispatches_audio_task_not_a_direct_send(self, test_user):
        db = AsyncMock()
        contact = _contact()
        campaign = _campaign(test_user)
        test_user.messages_remaining = 100
        ab = {"audio_url": "https://x/audio.ogg", "radio_script": "script"}

        with patch("app.workers.task_helpers.campaign_ops._preload_conversations", new=AsyncMock(return_value={"c1": None})), \
             patch("app.workers.task_helpers.campaign_ops._offer_or_queue", new=AsyncMock(return_value=("open", None))), \
             patch("app.workers.tasks.send_whatsapp_voice_note.apply_async") as mock_apply_async, \
             patch("app.services.messaging_throttle.anti_ban_delay", return_value=1):
            await send_radio_messages(db, campaign, [contact], test_user, ab, ban_delay=5)

        mock_apply_async.assert_called_once()
        assert mock_apply_async.call_args.kwargs["countdown"] == 5
        assert mock_apply_async.call_args.kwargs["args"][2] == "https://x/audio.ogg"

        queued_pending = [
            call.args[0] for call in db.add.call_args_list
            if hasattr(call.args[0], "content") and str(call.args[0].content).startswith("[PENDING:")
        ]
        assert queued_pending == []


class TestInvitedOutcomeDefersAudio:
    @pytest.mark.asyncio
    async def test_invited_outcome_queues_pending_audio_without_dispatching(self, test_user):
        """The key fix under test: an "invited" outcome from the gate (opt-in
        template sent, window still closed) must NOT dispatch the real audio
        in the same pass — it must be stored as [PENDING:audio] for
        inbound_pipeline.py to fulfill once the contact actually replies."""
        db = AsyncMock()
        contact = _contact()
        campaign = _campaign(test_user)
        test_user.messages_remaining = 100
        ab = {"audio_url": "https://x/audio.ogg", "radio_script": "script"}

        with patch("app.workers.task_helpers.campaign_ops._preload_conversations", new=AsyncMock(return_value={"c1": None})), \
             patch("app.workers.task_helpers.campaign_ops._offer_or_queue", new=AsyncMock(return_value=("invited", None))), \
             patch("app.workers.tasks.send_whatsapp_voice_note.apply_async") as mock_apply_async, \
             patch("app.services.messaging_throttle.anti_ban_delay", return_value=1):
            await send_radio_messages(db, campaign, [contact], test_user, ab, ban_delay=0)

        mock_apply_async.assert_not_called()

        queued_messages = [
            call.args[0] for call in db.add.call_args_list
            if hasattr(call.args[0], "content") and str(call.args[0].content).startswith("[PENDING:audio]")
        ]
        assert len(queued_messages) == 1
        assert queued_messages[0].status == "queued"
        import json
        payload = json.loads(queued_messages[0].content.removeprefix("[PENDING:audio] "))
        assert payload == {"audio_url": "https://x/audio.ogg", "script": "script"}

    @pytest.mark.asyncio
    async def test_blocked_outcome_skips_contact_entirely(self, test_user):
        db = AsyncMock()
        contact = _contact()
        campaign = _campaign(test_user)
        test_user.messages_remaining = 100
        ab = {"audio_url": "https://x/audio.ogg", "radio_script": "script"}

        with patch("app.workers.task_helpers.campaign_ops._preload_conversations", new=AsyncMock(return_value={"c1": None})), \
             patch("app.workers.task_helpers.campaign_ops._offer_or_queue", new=AsyncMock(return_value=("blocked", None))), \
             patch("app.workers.tasks.send_whatsapp_voice_note.apply_async") as mock_apply_async, \
             patch("app.services.messaging_throttle.anti_ban_delay", return_value=1):
            await send_radio_messages(db, campaign, [contact], test_user, ab, ban_delay=0)

        mock_apply_async.assert_not_called()
        assert not any(
            call.args and hasattr(call.args[0], "direction") for call in db.add.call_args_list
        )
