"""Tests for require_admin — the authorization gate on the entire admin.py
router (`APIRouter(dependencies=[Depends(require_admin)])`). Zero coverage
existed before this file despite being the highest-risk authorization
surface in the app."""
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.api.deps import require_admin
from app.models.user import User


class TestRequireAdmin:
    @pytest.mark.asyncio
    async def test_admin_role_passes_through(self):
        user = MagicMock(spec=User)
        user.role = "admin"
        result = await require_admin(user=user)
        assert result is user

    @pytest.mark.asyncio
    async def test_advertiser_role_is_rejected_with_403(self):
        user = MagicMock(spec=User)
        user.role = "advertiser"
        with pytest.raises(HTTPException) as exc_info:
            await require_admin(user=user)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_empty_role_is_rejected(self):
        user = MagicMock(spec=User)
        user.role = ""
        with pytest.raises(HTTPException) as exc_info:
            await require_admin(user=user)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_role_check_is_case_sensitive(self):
        """'Admin'/'ADMIN' must not accidentally pass — the check is a
        plain string equality against the literal 'admin'."""
        user = MagicMock(spec=User)
        user.role = "Admin"
        with pytest.raises(HTTPException) as exc_info:
            await require_admin(user=user)
        assert exc_info.value.status_code == 403
