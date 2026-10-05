"""Prueba A/B de la mascota (services/mascot_ab.py): cada visitante cuenta
una vez por evento, lo inválido no se cuenta y las tasas salen sobre visitas."""
import pytest

from app.services import mascot_ab


class FakeRedis:
    def __init__(self):
        self.kv, self.h = {}, {}

    async def set(self, key, value, ex=None, nx=False):
        if nx and key in self.kv:
            return None
        self.kv[key] = value
        return True

    async def get(self, key):
        return self.kv.get(key)

    async def hincrby(self, key, field, n):
        self.h.setdefault(key, {})
        self.h[key][field] = self.h[key].get(field, 0) + n

    async def hgetall(self, key):
        return dict(self.h.get(key, {}))


VISITORS = [f"visitor{i:04d}" for i in range(10)]


@pytest.mark.asyncio
async def test_counts_each_visitor_once_per_event_and_computes_rates():
    r = FakeRedis()
    for v in VISITORS[:4]:
        for _ in range(3):  # recargar la página no infla las visitas
            await mascot_ab.record(r, "lupita", "3d", "view", v)
    await mascot_ab.record(r, "lupita", "3d", "chat_open", VISITORS[0])
    await mascot_ab.record(r, "lupita", "3d", "confirmed", VISITORS[0])
    for v in VISITORS[4:6]:
        await mascot_ab.record(r, "lupita", "static", "view", v)

    out = await mascot_ab.results(r)
    three, still = out["variants"]["3d"], out["variants"]["static"]
    assert three["counts"]["view"] == 4 and three["chat_open_pct"] == 25.0 and three["confirmed_pct"] == 25.0
    assert still["counts"]["view"] == 2 and still["chat_open_pct"] == 0.0
    assert out["since"]


@pytest.mark.parametrize("slug,variant,event,visitor", [
    ("lupita", "4d", "view", "visitor0001"),
    ("lupita", "3d", "hack", "visitor0001"),
    ("lupita", "3d", "view", "x"),
    ("../etc", "3d", "view", "visitor0001"),
])
def test_rejects_invalid_events(slug, variant, event, visitor):
    assert mascot_ab.valid(slug, variant, event, visitor) is False


def test_accepts_a_real_event():
    assert mascot_ab.valid("estetica-lupita", "static", "chat_open", "a1b2c3d4e5f6") is True


@pytest.mark.asyncio
async def test_empty_results_have_zero_rates():
    out = await mascot_ab.results(FakeRedis())
    assert out["variants"]["3d"]["chat_open_pct"] == 0.0 and out["since"] is None
