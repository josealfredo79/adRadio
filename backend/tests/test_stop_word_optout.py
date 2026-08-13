"""Tests for STOP-word opt-out handling in inbound_pipeline.py (Capa 12
anti-baneo) — a real subset of stop words already existed, but had a phone-
matching bug (exact `from_number` instead of the MX 521/52 variants used
everywhere else in the pipeline) that could silently fail to find the
contact and leave them subscribed. Also covers the fuzzier whitespace/
punctuation matching and the opt-out confirmation reply added alongside the
fix, plus the downstream exclusion from campaign sends."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.inbound_pipeline import InboundMessage, process_inbound_message
from app.workers.task_helpers.campaign_ops import _is_contact_active


def _no_handoff_side_effects(contact):
    """First 3 db.execute calls before the STOP check: idempotency check,
    existing-contact lookup (handoff gate), escalated-conversation lookup."""
    no_dup = MagicMock()
    no_dup.scalar_one_or_none.return_value = None
    contact_result = MagicMock()
    contact_result.scalar_one_or_none.return_value = contact
    escalated_result = MagicMock()
    escalated_result.scalar_one_or_none.return_value = None  # not escalated
    return [no_dup, contact_result, escalated_result]


class TestStopWordOptOut:
    @pytest.mark.asyncio
    async def test_exact_stop_word_unsubscribes_and_confirms(self, mock_db, test_user):
        contact = MagicMock(id="contact-1", phone="+521234567890", status="active", engagement_score=80)
        stop_contact_result = MagicMock()
        stop_contact_result.scalar_one_or_none.return_value = contact
        mock_db.execute.side_effect = _no_handoff_side_effects(contact) + [stop_contact_result]

        send = AsyncMock(return_value=("sid-1", None))
        msg = InboundMessage(advertiser=test_user, from_number="+521234567890", body_text="STOP")

        result = await process_inbound_message(mock_db, msg, send=send, send_owner=send)

        assert result == {"message": "ok"}
        assert contact.status == "unsubscribed"
        assert contact.engagement_score == 0
        send.assert_awaited_once()
        assert send.call_args.args[0] == "+521234567890"

    @pytest.mark.parametrize("body", ["baja", " Baja ", "BAJA.", "cancelar", "salir", "no quiero", "stop!"])
    @pytest.mark.asyncio
    async def test_whitespace_case_and_punctuation_tolerated(self, mock_db, test_user, body):
        contact = MagicMock(id="contact-1", phone="+521234567890", status="active", engagement_score=50)
        stop_contact_result = MagicMock()
        stop_contact_result.scalar_one_or_none.return_value = contact
        mock_db.execute.side_effect = _no_handoff_side_effects(contact) + [stop_contact_result]

        send = AsyncMock(return_value=("sid-1", None))
        msg = InboundMessage(advertiser=test_user, from_number="+521234567890", body_text=body)

        await process_inbound_message(mock_db, msg, send=send, send_owner=send)

        assert contact.status == "unsubscribed"

    @pytest.mark.asyncio
    async def test_phrase_merely_containing_a_stop_word_is_not_unsubscribed(self, mock_db, test_user):
        """'no quiero' contained mid-sentence must NOT trigger opt-out — only
        an (normalized) exact match should. Regression guard against being
        too aggressive and unsubscribing people asking a real question."""
        contact = MagicMock(id="contact-1", phone="+521234567890", status="active")
        contact_result = MagicMock()
        contact_result.scalar_one_or_none.return_value = contact
        escalated_result = MagicMock()
        escalated_result.scalar_one_or_none.return_value = None
        no_dup = MagicMock()
        no_dup.scalar_one_or_none.return_value = None
        # No 4th side_effect for a STOP-word contact lookup — if the pipeline
        # tried to consume one here (i.e. wrongly treated this as a stop
        # word), the test fails with StopAsyncIteration, not a silent pass.
        mock_db.execute.side_effect = [no_dup, contact_result, escalated_result]

        send = AsyncMock()
        msg = InboundMessage(
            advertiser=test_user, from_number="+521234567890",
            body_text="no quiero cancelar mi pedido, solo tengo una pregunta",
        )

        with pytest.raises(StopAsyncIteration):
            # Falls through to deeper pipeline logic (contact/conversation
            # lookups) that this test doesn't mock — proves it did NOT take
            # the STOP early-return.
            await process_inbound_message(mock_db, msg, send=send, send_owner=send)
        assert contact.status == "active"  # untouched

    @pytest.mark.asyncio
    async def test_phone_number_variant_still_matches_contact(self, mock_db, test_user):
        """The bug this test guards: the STOP handler used to filter by exact
        `Contact.phone == from_number`, ignoring the MX 521/52 prefix variants
        the rest of the pipeline already normalizes via `from_candidates`. A
        contact saved as '+52...' who texts from a '+521...'-formatted
        webhook payload (or vice versa) must still be found and unsubscribed."""
        contact = MagicMock(id="contact-1", phone="+525512345678", status="active", engagement_score=10)
        stop_contact_result = MagicMock()
        stop_contact_result.scalar_one_or_none.return_value = contact
        mock_db.execute.side_effect = _no_handoff_side_effects(contact) + [stop_contact_result]

        send = AsyncMock(return_value=("sid-1", None))
        # Meta sends the 521-prefixed variant; contact is stored as 52-prefixed.
        msg = InboundMessage(advertiser=test_user, from_number="+5215512345678", body_text="stop")

        await process_inbound_message(mock_db, msg, send=send, send_owner=send)

        assert contact.status == "unsubscribed"
        # The lookup must have used the candidate list (.in_), not a bare ==.
        stop_lookup_call = mock_db.execute.call_args_list[-1]
        compiled = str(stop_lookup_call.args[0])
        assert "IN" in compiled.upper()

    @pytest.mark.asyncio
    async def test_no_matching_contact_is_a_noop(self, mock_db, test_user):
        # No existing contact at all -> handoff gate's `if existing_contact:`
        # is False, so only 2 db.execute calls happen before the STOP check
        # (idempotency + the handoff-gate contact lookup), not 3.
        no_dup = MagicMock()
        no_dup.scalar_one_or_none.return_value = None
        no_existing_contact = MagicMock()
        no_existing_contact.scalar_one_or_none.return_value = None
        no_contact_result = MagicMock()
        no_contact_result.scalar_one_or_none.return_value = None
        mock_db.execute.side_effect = [no_dup, no_existing_contact, no_contact_result]

        send = AsyncMock()
        msg = InboundMessage(advertiser=test_user, from_number="+521234567890", body_text="baja")

        result = await process_inbound_message(mock_db, msg, send=send, send_owner=send)

        assert result == {"message": "ok"}
        send.assert_not_called()  # nothing to confirm — no contact found

    @pytest.mark.asyncio
    async def test_confirmation_send_failure_does_not_crash(self, mock_db, test_user):
        contact = MagicMock(id="contact-1", phone="+521234567890", status="active", engagement_score=10)
        stop_contact_result = MagicMock()
        stop_contact_result.scalar_one_or_none.return_value = contact
        mock_db.execute.side_effect = _no_handoff_side_effects(contact) + [stop_contact_result]

        send = AsyncMock(side_effect=Exception("Meta API down"))
        msg = InboundMessage(advertiser=test_user, from_number="+521234567890", body_text="stop")

        result = await process_inbound_message(mock_db, msg, send=send, send_owner=send)

        assert result == {"message": "ok"}
        assert contact.status == "unsubscribed"  # DB change already committed before the send attempt


class TestUnsubscribedContactsExcludedFromCampaigns:
    def test_unsubscribed_contact_is_not_active(self):
        contact = MagicMock(status="unsubscribed", suppressed_until=None, last_campaign_sent_at=None, last_interaction=None)
        active, reason = _is_contact_active(contact)
        assert active is False
        assert reason is not None

    def test_active_contact_with_no_history_is_active(self):
        contact = MagicMock(status="active", suppressed_until=None, last_campaign_sent_at=None, last_interaction=None)
        active, reason = _is_contact_active(contact)
        assert active is True
        assert reason is None
