"""Invitación a seguir en la web desde WhatsApp (decisión del dueño 2026-11-04):
"cuando se tiene el WhatsApp no siempre manda al bot en web". El catálogo y el
agente contestaban por caminos que nunca agregaban la invitación. Entrada real
de WhatsApp (process_inbound_message) con base y Redis reales; Claude y Meta
simulados."""
import pytest

from app.config import settings
from tests.test_customer_agent import fake_claude, resp, text
from tests.test_customer_agent_whatsapp import (  # noqa: F401 (_keys: fixture)
    _cleanup,
    _keys,
    _seed,
    _wa,
)

INVITE = "💬 ¿Seguimos por aquí?"


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setattr(settings, "SECRET_KEY", "test-secret")
    monkeypatch.setattr(settings, "PORTAL_INVITE_FROM_WA_REPLIES", 0)


@pytest.mark.asyncio
async def test_the_catalog_reply_invites_to_the_web(monkeypatch):
    monkeypatch.setattr(settings, "CUSTOMER_AGENT_WHATSAPP", "")  # sin agente: contesta el catálogo
    user_id, *_ = await _seed()
    try:
        sent = await _wa(user_id, "¿qué productos tienen?")
        reply = sent.last()
        assert "Cera para cabello" in reply
        assert INVITE in reply and "/c/" in reply
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_the_agent_reply_invites_to_the_web():
    user_id, *_ = await _seed()
    try:
        claude, _ = fake_claude(resp(text("La cera cuesta $80."), stop="end_turn"))
        sent = await _wa(user_id, "quiero pedir una cera, ¿cuánto cuesta?", claude)
        reply = sent.last()
        assert reply.startswith("La cera cuesta $80.")
        assert INVITE in reply
    finally:
        await _cleanup(user_id)
