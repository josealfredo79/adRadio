"""Avisos de Stripe firmados de verdad y leídos con la librería real (sin
simular construct_event) — 2026-10-13: el primer pago real tronó con 500
porque stripe-python 15 ya no entrega dicts, y las pruebas simulaban un dict.
También: con la API nueva la factura no trae payment_intent y las
renovaciones no se acreditaban. BD real."""
import hashlib
import hmac
import json
import time
import uuid

import pytest
from sqlalchemy import delete, select
from starlette.requests import Request

from app.api.v1.webhooks_pkg.stripe import stripe_webhook
from app.config import settings
from app.core.plans import PLAN_MESSAGES
from app.database import AsyncSessionLocal, engine
from app.models.transaction import Transaction
from app.models.user import User

SECRET = "whsec_test_real_events"


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", SECRET)


def _signed_request(event: dict) -> Request:
    payload = json.dumps(event).encode()
    t = int(time.time())
    sig = hmac.new(SECRET.encode(), f"{t}.".encode() + payload, hashlib.sha256).hexdigest()
    headers = [(b"stripe-signature", f"t={t},v1={sig}".encode())]

    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}

    return Request({"type": "http", "method": "POST", "path": "/api/v1/webhooks/stripe", "headers": headers,
                    "client": ("stripe", 1), "query_string": b""}, receive)


def _event(type_: str, obj: dict) -> dict:
    return {"id": f"evt_{uuid.uuid4().hex}", "object": "event", "api_version": "2026-07-29.dahlia",
            "type": type_, "data": {"object": obj}}


async def _seed(**kw):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="CityCell",
                    stripe_customer_id=f"cus_{uuid.uuid4().hex[:14]}", subscription_status="trial",
                    messages_remaining=50, **kw)
        db.add(user)
        await db.commit()
        return user.id, user.stripe_customer_id


async def _cleanup(user_id):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Transaction).where(Transaction.advertiser_id == user_id))
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()
    await engine.dispose()


async def _send(event: dict):
    async with AsyncSessionLocal() as db:
        return await stripe_webhook(_signed_request(event), db)


async def _user(user_id):
    async with AsyncSessionLocal() as db:
        return await db.get(User, user_id)


def _checkout(customer):
    # Checkout de suscripción: payment_intent viene en null.
    return _event("checkout.session.completed", {
        "id": f"cs_live_{uuid.uuid4().hex}", "object": "checkout.session", "mode": "subscription",
        "customer": customer, "payment_intent": None, "amount_total": 44900, "currency": "mxn",
        "metadata": {"plan": "starter", "billing_cycle": "monthly"},
    })


def _invoice(customer, billing_reason):
    # API 2025-03-31+: la factura ya no trae payment_intent.
    return _event("invoice.payment_succeeded", {
        "id": f"in_{uuid.uuid4().hex}", "object": "invoice", "customer": customer,
        "billing_reason": billing_reason, "amount_paid": 44900, "currency": "mxn", "invoice_pdf": None,
    })


@pytest.mark.asyncio
async def test_real_signed_checkout_activates_the_plan():
    user_id, customer = await _seed()
    try:
        assert await _send(_checkout(customer)) == {"received": True}
        user = await _user(user_id)
        assert (user.subscription_status, user.current_plan) == ("active", "starter")
        assert user.messages_remaining == 50 + PLAN_MESSAGES["starter"]
        async with AsyncSessionLocal() as db:
            txn = (await db.execute(select(Transaction).where(Transaction.advertiser_id == user_id))).scalar_one()
        assert (float(txn.amount), txn.currency) == (449.0, "MXN")
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_first_invoice_does_not_credit_twice():
    user_id, customer = await _seed()
    try:
        await _send(_checkout(customer))
        await _send(_invoice(customer, "subscription_create"))
        user = await _user(user_id)
        assert user.messages_remaining == 50 + PLAN_MESSAGES["starter"]
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_monthly_renewal_without_payment_intent_is_credited_once():
    user_id, customer = await _seed()
    try:
        await _send(_checkout(customer))
        renewal = _invoice(customer, "subscription_cycle")
        await _send(renewal)
        await _send(renewal)  # Stripe reintenta: no se acredita dos veces
        user = await _user(user_id)
        assert user.messages_remaining == 50 + 2 * PLAN_MESSAGES["starter"]
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_me_tells_the_panel_if_cancelled_and_until_when():
    # Planes muestra "Cancelada, sigues hasta el…" o "Se renueva el…" (2026-10-13).
    from app.api.v1.profile import _user_out

    user_id, customer = await _seed()
    try:
        await _send(_checkout(customer))
        async with AsyncSessionLocal() as db:
            user = await db.get(User, user_id)
            user.cancel_at_period_end = True
            await db.commit()
            out = _user_out(await db.get(User, user_id)).model_dump()
        assert out["cancel_at_period_end"] is True
        assert out["plan_expires_at"] is not None
    finally:
        await _cleanup(user_id)
