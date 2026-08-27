"""
Tests for consent_status on CSV-imported contacts — the anti-ban guard that
blocks cold-window template sends to bulk lists the advertiser hasn't vouched
for (see app.workers.task_helpers.campaign_ops._offer_or_queue).
"""
import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.workers.tasks import import_contacts_csv


def _no_existing_contact_db():
    """AsyncSessionLocal() is used via `async with ... as db:` in the task —
    __aenter__ must resolve back to this same mock for assertions to see the
    calls made inside."""
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.__aenter__ = AsyncMock(return_value=db)
    db.__aexit__ = AsyncMock(return_value=False)
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result)
    return db


class TestImportContactsCsvConsent:
    def test_consent_not_confirmed_marks_contacts_unconfirmed(self):
        advertiser_id = str(uuid.uuid4())
        db = _no_existing_contact_db()

        with patch("app.database.CeleryAsyncSessionLocal", return_value=db), \
             patch("app.workers.tasks.run_async", side_effect=lambda coro: asyncio.run(coro)):
            import_contacts_csv(
                advertiser_id,
                [{"phone": "+521234567890", "name": "Negocio Frío"}],
                False,  # consent_confirmed
            )

        added = [c.args[0] for c in db.add.call_args_list if hasattr(c.args[0], "consent_status")]
        assert len(added) == 1
        assert added[0].consent_status == "unconfirmed"

    def test_consent_confirmed_marks_contacts_confirmed(self):
        advertiser_id = str(uuid.uuid4())
        db = _no_existing_contact_db()

        with patch("app.database.CeleryAsyncSessionLocal", return_value=db), \
             patch("app.workers.tasks.run_async", side_effect=lambda coro: asyncio.run(coro)):
            import_contacts_csv(
                advertiser_id,
                [{"phone": "+521234567891", "name": "Cliente Vouched"}],
                True,  # consent_confirmed
            )

        added = [c.args[0] for c in db.add.call_args_list if hasattr(c.args[0], "consent_status")]
        assert len(added) == 1
        assert added[0].consent_status == "confirmed"

    def test_default_is_unconfirmed_when_flag_omitted(self):
        advertiser_id = str(uuid.uuid4())
        db = _no_existing_contact_db()

        with patch("app.database.CeleryAsyncSessionLocal", return_value=db), \
             patch("app.workers.tasks.run_async", side_effect=lambda coro: asyncio.run(coro)):
            import_contacts_csv(
                advertiser_id,
                [{"phone": "+521234567892", "name": "Sin Flag"}],
            )

        added = [c.args[0] for c in db.add.call_args_list if hasattr(c.args[0], "consent_status")]
        assert len(added) == 1
        assert added[0].consent_status == "unconfirmed"
