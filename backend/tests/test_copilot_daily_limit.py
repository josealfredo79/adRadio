"""Copiloto: tope diario de mensajes por plan (core/plans.py, "copilot").

Es un seguro contra la cuenta de Anthropic: al pasarse, el Copiloto contesta un
aviso fijo SIN llamar a Claude. Corre contra Redis real (el contador vive ahí)."""
import uuid
from types import SimpleNamespace

import pytest

from app.core.plans import plan_limit
from app.core.redis import get_redis
from app.models.user import User
from app.services import copilot_service
from app.services.copilot_service import DAILY_LIMIT_REPLY, handle_chat


class _FakeMessages:
    def __init__(self):
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
        return SimpleNamespace(content=[SimpleNamespace(type="text", text="Hola, ¿en qué te ayudo?")])


@pytest.fixture
def fake_claude(monkeypatch):
    messages = _FakeMessages()
    monkeypatch.setattr(copilot_service, "_get_client", lambda: SimpleNamespace(messages=messages))
    return messages


def _user(plan: str, role: str = "advertiser") -> User:
    return User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@test.com", business_name="CityCell",
                current_plan=plan, role=role)


async def _clear(user: User):
    redis = await get_redis()
    keys = await redis.keys(f"copilot:daily:{user.id}:*")
    if keys:
        await redis.delete(*keys)


def test_every_plan_has_a_copilot_cap():
    assert plan_limit("trial", "copilot") == 25
    assert plan_limit("starter", "copilot") == 25
    assert plan_limit("growth", "copilot") == 60
    assert plan_limit("pro", "copilot") == 120
    assert plan_limit("enterprise", "copilot") == 300


@pytest.mark.asyncio
async def test_over_the_cap_answers_without_calling_claude(fake_claude):
    user = _user("starter")
    try:
        for _ in range(25):
            out = await handle_chat(None, user, "hola", [])
            assert out["reply"] != DAILY_LIMIT_REPLY
        assert fake_claude.calls == 25

        out = await handle_chat(None, user, "hola", [])
        assert out["reply"] == DAILY_LIMIT_REPLY
        assert out["pending_confirmation"] is None
        assert fake_claude.calls == 25  # el mensaje 26 no gastó en Claude
    finally:
        await _clear(user)


@pytest.mark.asyncio
async def test_admins_have_no_cap(fake_claude):
    user = _user("starter", role="admin")
    for _ in range(30):
        out = await handle_chat(None, user, "hola", [])
        assert out["reply"] != DAILY_LIMIT_REPLY
    assert fake_claude.calls == 30


@pytest.mark.asyncio
async def test_without_redis_the_copilot_keeps_working(fake_claude, monkeypatch):
    async def no_redis():
        return None

    monkeypatch.setattr(copilot_service, "get_redis_optional", no_redis)
    user = _user("starter")
    for _ in range(30):
        out = await handle_chat(None, user, "hola", [])
        assert out["reply"] != DAILY_LIMIT_REPLY
