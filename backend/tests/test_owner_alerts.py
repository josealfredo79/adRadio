"""Avisos al dueño (owner_alerts.py) — las reglas para no saturarlo: uno por
cliente cada 30 min, tope por hora, clientes nuevos agrupados, silencio
nocturno con resumen de las 8 am."""
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.models.user import User
from app.services import owner_alerts as oa
from app.services.availability_service import TZ

NOON = datetime(2026, 10, 5, 12, 0, tzinfo=TZ)
NIGHT = datetime(2026, 10, 5, 23, 30, tzinfo=TZ)


class Redis:
    def __init__(self):
        self.kv: dict[str, str] = {}
        self.sets: dict[str, set] = {}

    async def set(self, k, v, nx=False, ex=None):
        if nx and k in self.kv:
            return None
        self.kv[k] = v
        return True

    async def incr(self, k):
        self.kv[k] = str(int(self.kv.get(k, "0")) + 1)
        return int(self.kv[k])

    async def expire(self, k, ttl):
        return True

    async def sadd(self, k, v):
        self.sets.setdefault(k, set()).add(v)

    async def smembers(self, k):
        return set(self.sets.get(k, set()))

    async def delete(self, *keys):
        for k in keys:
            self.kv.pop(k, None)
            self.sets.pop(k, None)

    async def scan_iter(self, match):
        prefix = match.rstrip("*")
        for k in list(self.sets):
            if k.startswith(prefix):
                yield k


@pytest.fixture(autouse=True)
def _central(monkeypatch):
    monkeypatch.setattr(settings, "IARADIO_WA_PHONE_NUMBER_ID", "123")
    monkeypatch.setattr(settings, "FRONTEND_URL", "https://www.iaradio.online")


@pytest.fixture
def send():
    mock = AsyncMock(return_value=("wamid.1", None))
    with patch("app.services.platform_whatsapp.send_platform_text", mock):
        yield mock


def _owner(phone="+5219511111111"):
    return User(id=uuid.uuid4(), email="x@test.com", password_hash="x", business_name="Barbería", phone=phone)


def _at(when):
    return patch("app.services.owner_alerts._now_local", return_value=when)


class TestWebMessages:
    @pytest.mark.asyncio
    async def test_one_alert_per_customer_every_30_minutes(self, send):
        r, owner, ana = Redis(), _owner(), uuid.uuid4()
        with _at(NOON):
            assert await oa.alert_web_message(r, owner, ana, "Ana", "¿me atienden a las 5?") is True
            assert await oa.alert_web_message(r, owner, ana, "Ana", "¿hola?") is False
        to, body = send.await_args.args
        assert to == "+5219511111111"
        assert "Ana te escribió por la web" in body and "¿me atienden a las 5?" in body
        assert "https://www.iaradio.online/app/inbox" in body
        assert send.await_count == 1

    @pytest.mark.asyncio
    async def test_hourly_cap_folds_the_rest_into_the_next_alert(self, send):
        r, owner = Redis(), _owner()
        with _at(NOON):
            results = [await oa.alert_web_message(r, owner, uuid.uuid4(), n, "hola") for n in ["A", "B", "C", "D", "E"]]
        assert results == [True, True, True, True, False]
        with _at(NOON.replace(hour=13)):
            await oa.alert_web_message(r, owner, uuid.uuid4(), "F", "hola")
        assert "Además: 1 cliente más te escribió por la web (E)" in send.await_args.args[1]

    @pytest.mark.asyncio
    async def test_no_owner_phone_or_no_central_number_means_silence(self, send, monkeypatch):
        with _at(NOON):
            assert await oa.alert_web_message(Redis(), _owner(phone=None), uuid.uuid4(), "Ana", "x") is False
            monkeypatch.setattr(settings, "IARADIO_WA_PHONE_NUMBER_ID", "")
            assert await oa.alert_web_message(Redis(), _owner(), uuid.uuid4(), "Ana", "x") is False
        send.assert_not_called()


class TestNewCustomers:
    @pytest.mark.asyncio
    async def test_grouped_every_two_hours(self, send):
        r, owner = Redis(), _owner()
        with _at(NOON):
            assert await oa.alert_new_customer(r, owner, "Ana", "tu QR de mostrador") is True
            assert await oa.alert_new_customer(r, owner, "Beto", "tu QR de mostrador") is False
            assert await oa.alert_new_customer(r, owner, "Lupita", "el directorio de IaRadio") is False
        assert "Cliente nuevo: Ana se unió desde tu QR de mostrador" in send.await_args.args[1]
        r.kv.pop(f"owner_alert_new:{owner.id}")  # pasaron las 2 horas
        with _at(NOON.replace(hour=15)):
            await oa.alert_new_customer(r, owner, "Mario", "tu QR de mostrador")
        body = send.await_args.args[1]
        assert body.startswith("🎉 3 clientes nuevos:")
        assert "Beto (tu QR de mostrador)" in body and "Lupita (el directorio de IaRadio)" in body


class TestQuietHours:
    def test_window(self):
        assert oa.is_quiet_hours(NIGHT) and oa.is_quiet_hours(NOON.replace(hour=7))
        assert not oa.is_quiet_hours(NOON) and not oa.is_quiet_hours(NOON.replace(hour=8))

    @pytest.mark.asyncio
    async def test_night_is_silent_and_morning_brings_one_summary(self, send):
        r, owner = Redis(), _owner()
        with _at(NIGHT):
            assert await oa.alert_web_message(r, owner, uuid.uuid4(), "Ana", "¿abren mañana?") is False
            assert await oa.alert_web_message(r, owner, uuid.uuid4(), "Beto", "precio?") is False
            assert await oa.alert_new_customer(r, owner, "Lupita", "tu QR de mostrador") is False
        send.assert_not_called()

        class Db:
            async def execute(self, _q):
                class R:
                    def scalar_one_or_none(self_inner):
                        return owner
                return R()

        assert await oa.send_morning_digests(Db(), r) == 1
        body = send.await_args.args[1]
        assert body.startswith("☀️ Buenos días")
        assert "2 clientes te escribieron por la web: Ana, Beto" in body
        assert "1 cliente nuevo: Lupita (tu QR de mostrador)" in body
        assert await oa.send_morning_digests(Db(), r) == 0  # ya se vació
