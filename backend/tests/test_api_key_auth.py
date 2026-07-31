"""Tests for app.api.api_key_auth — the Bearer-token auth used by the
public API (/api/v1/public/*), the highest-risk surface in the app since
it's the one meant for external, third-party clients. Zero coverage
existed before this file."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.api.api_key_auth import get_user_from_api_key, require_api_key_scope
from app.core.security import hash_api_key


def _creds(raw_key: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=raw_key)


def _mock_db_returning(api_key_row, user_row=None):
    db = AsyncMock()
    key_result = MagicMock()
    key_result.scalar_one_or_none.return_value = api_key_row
    if user_row is not None or api_key_row is not None:
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user_row
        db.execute = AsyncMock(side_effect=[key_result, user_result])
    else:
        db.execute = AsyncMock(return_value=key_result)
    db.commit = AsyncMock()
    return db


def _fake_api_key(raw_key: str, *, scopes=None, active=True):
    row = MagicMock()
    row.key = hash_api_key(raw_key)
    row.prefix = raw_key[:8]
    row.active = active
    row.scopes = scopes or []
    row.user_id = uuid.uuid4()
    row.last_used_at = None
    return row


class TestGetUserFromApiKey:
    @pytest.mark.asyncio
    async def test_valid_key_returns_user_and_updates_last_used(self):
        raw = "iar_" + "a" * 60
        api_key_row = _fake_api_key(raw)
        user = MagicMock()
        db = _mock_db_returning(api_key_row, user)

        result = await get_user_from_api_key(credentials=_creds(raw), db=db)

        assert result is user
        assert api_key_row.last_used_at is not None
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unknown_prefix_returns_401(self):
        db = _mock_db_returning(None)
        with pytest.raises(HTTPException) as exc_info:
            await get_user_from_api_key(credentials=_creds("iar_doesnotexist"), db=db)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_correct_prefix_but_wrong_full_key_returns_401(self):
        """The prefix matches (query found a row) but the full key doesn't
        hash-verify against the stored hash — e.g. a key that shares the
        first 8 chars by coincidence, or a truncated/corrupted key."""
        real_raw = "iar_" + "a" * 60
        api_key_row = _fake_api_key(real_raw)
        wrong_raw = real_raw[:8] + "b" * 56  # same prefix, different rest
        db = _mock_db_returning(api_key_row)

        with pytest.raises(HTTPException) as exc_info:
            await get_user_from_api_key(credentials=_creds(wrong_raw), db=db)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_user_not_found_returns_401(self):
        raw = "iar_" + "a" * 60
        api_key_row = _fake_api_key(raw)
        db = _mock_db_returning(api_key_row, user_row=None)

        with pytest.raises(HTTPException) as exc_info:
            await get_user_from_api_key(credentials=_creds(raw), db=db)
        assert exc_info.value.status_code == 401


class TestRequireApiKeyScope:
    @pytest.mark.asyncio
    async def test_key_with_required_scope_passes(self):
        raw = "iar_" + "a" * 60
        api_key_row = _fake_api_key(raw, scopes=["campaigns:read", "contacts:read"])
        user = MagicMock()
        db = _mock_db_returning(api_key_row, user)

        check = require_api_key_scope("campaigns:read")
        result = await check(credentials=_creds(raw), db=db)

        assert result is user

    @pytest.mark.asyncio
    async def test_key_missing_required_scope_returns_403(self):
        raw = "iar_" + "a" * 60
        api_key_row = _fake_api_key(raw, scopes=["contacts:read"])
        db = _mock_db_returning(api_key_row, MagicMock())

        check = require_api_key_scope("campaigns:read")
        with pytest.raises(HTTPException) as exc_info:
            await check(credentials=_creds(raw), db=db)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_key_with_no_scopes_at_all_returns_403(self):
        raw = "iar_" + "a" * 60
        api_key_row = _fake_api_key(raw, scopes=[])
        db = _mock_db_returning(api_key_row, MagicMock())

        check = require_api_key_scope("campaigns:read")
        with pytest.raises(HTTPException) as exc_info:
            await check(credentials=_creds(raw), db=db)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_inactive_key_is_treated_as_not_found(self):
        """The lookup query filters `ApiKey.active == True` — an inactive
        key never even reaches the scope check, it 401s like an unknown key."""
        db = _mock_db_returning(None)  # simulates the filtered-out inactive row
        check = require_api_key_scope("campaigns:read")
        with pytest.raises(HTTPException) as exc_info:
            await check(credentials=_creds("iar_" + "a" * 60), db=db)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_scope_check_updates_last_used_at(self):
        raw = "iar_" + "a" * 60
        api_key_row = _fake_api_key(raw, scopes=["campaigns:read"])
        db = _mock_db_returning(api_key_row, MagicMock())

        check = require_api_key_scope("campaigns:read")
        await check(credentials=_creds(raw), db=db)

        assert api_key_row.last_used_at is not None
