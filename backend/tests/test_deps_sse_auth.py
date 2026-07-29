"""Tests for get_current_user_sse — token via query param (EventSource can't set headers)."""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.deps import get_current_user_sse


class TestGetCurrentUserSse:
    @pytest.mark.asyncio
    async def test_valid_query_token_returns_user(self, mock_db, test_user):
        result = MagicMock()
        result.scalar_one_or_none.return_value = test_user
        mock_db.execute.return_value = result

        with patch("app.api.deps.decode_token", return_value={"type": "access", "sub": str(test_user.id)}):
            user = await get_current_user_sse(token="valid-token", credentials=None, db=mock_db)

        assert user is test_user

    @pytest.mark.asyncio
    async def test_falls_back_to_bearer_header_if_no_query_token(self, mock_db, test_user):
        creds = MagicMock(credentials="bearer-token")
        result = MagicMock()
        result.scalar_one_or_none.return_value = test_user
        mock_db.execute.return_value = result

        with patch("app.api.deps.decode_token", return_value={"type": "access", "sub": str(test_user.id)}) as mock_decode:
            user = await get_current_user_sse(token=None, credentials=creds, db=mock_db)

        assert user is test_user
        mock_decode.assert_called_once_with("bearer-token")

    @pytest.mark.asyncio
    async def test_query_token_takes_precedence_over_header(self, mock_db, test_user):
        creds = MagicMock(credentials="header-token")
        result = MagicMock()
        result.scalar_one_or_none.return_value = test_user
        mock_db.execute.return_value = result

        with patch("app.api.deps.decode_token", return_value={"type": "access", "sub": str(test_user.id)}) as mock_decode:
            await get_current_user_sse(token="query-token", credentials=creds, db=mock_db)

        mock_decode.assert_called_once_with("query-token")

    @pytest.mark.asyncio
    async def test_no_token_at_all_raises_401(self, mock_db):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user_sse(token=None, credentials=None, db=mock_db)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_token_raises_401(self, mock_db):
        with patch("app.api.deps.decode_token", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user_sse(token="garbage", credentials=None, db=mock_db)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_wrong_token_type_raises_401(self, mock_db):
        with patch("app.api.deps.decode_token", return_value={"type": "refresh", "sub": str(uuid.uuid4())}):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user_sse(token="a-refresh-token", credentials=None, db=mock_db)
        assert exc_info.value.status_code == 401
