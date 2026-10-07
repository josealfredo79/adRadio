"""/health/ready (para el monitoreo externo) revisa base de datos y Redis de
verdad, y contesta 503 si alguno falla — /health solo dice que el proceso vive."""
from unittest.mock import AsyncMock, patch

import pytest

from app.main import health_ready


@pytest.mark.asyncio
async def test_ready_when_database_and_redis_answer():
    assert await health_ready() == {"status": "ok"}


@pytest.mark.asyncio
async def test_503_naming_what_fails_without_details():
    broken = AsyncMock()
    broken.ping.side_effect = ConnectionError("redis caído, con datos internos")
    with patch("app.core.redis.get_redis", AsyncMock(return_value=broken)):
        out = await health_ready()
    assert out.status_code == 503
    assert b'"failing":["redis"]' in out.body
    assert b"internos" not in out.body
