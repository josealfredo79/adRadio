"""Promo dentro del chat del cliente — un test por caso de
docs/specs/2026-10-13-promo-en-el-chat.md. BD y Redis de verdad; solo la IA
(answer_with_rag) se simula."""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete, select

from app.api.v1.portal import get_messages
from app.api.v1.widget import widget_chat
from app.database import AsyncSessionLocal, engine
from app.models.campaign import Campaign
from app.models.conversation import Conversation
from app.models.coupon import Coupon
from app.models.message import Message
from app.services.portal_service import make_portal_token
from tests.test_portal import _cleanup as _cleanup_portal
from tests.test_portal import (  # noqa: F401  (_secret_key: fixture autouse)
    _request,
    _secret_key,
    _seed,
    _seed_promos,
)
from tests.test_portal_web_shift import FakeRedis


async def _cleanup(user_id):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Conversation).where(Conversation.advertiser_id == user_id))
        await db.commit()
    await _cleanup_portal(user_id)


async def _chat(s, contact, **extra):
    async with AsyncSessionLocal() as db:
        return await get_messages(request=_request(), token=make_portal_token(s[contact]), db=db, **extra)


def _promos(out):
    return [m for m in out["messages"] if m.get("kind") == "promo"]


async def _web_chat(s, message, promo_id=None, rag_reply="¡Claro! Te la aparto."):
    rag = AsyncMock(return_value=rag_reply)
    body = {"message": message, "session_id": str(uuid.uuid4()), "portal_token": make_portal_token(s["ana"])}
    if promo_id is not None:
        body["promo_id"] = promo_id
    with patch("app.services.rag_service.answer_with_rag", rag), \
            patch("app.services.realtime.publish_conversation_event", AsyncMock()):
        async with AsyncSessionLocal() as db:
            out = await widget_chat(request=_request(), advertiser_id=s["user_id"], body=body, db=db, redis=FakeRedis())
    return out, rag


@pytest.mark.asyncio
async def test_web_promo_shows_in_chat():
    s = await _seed()
    try:
        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as db:
            camp = Campaign(advertiser_id=s["user_id"], name="Fundas", type="promo",
                            message_text="Hola {{nombre}}, 2x1 en fundas en {{negocio}}")
            db.add(camp)
            await db.flush()
            db.add_all([
                Message(advertiser_id=s["user_id"], contact_id=s["ana"], direction="inbound", content="hola",
                        status="delivered", created_at=now - timedelta(minutes=10)),
                Message(advertiser_id=s["user_id"], contact_id=s["ana"], campaign_id=camp.id, direction="outbound",
                        content="[PUSH] Fundas", status="sent", created_at=now - timedelta(minutes=5)),
                Message(advertiser_id=s["user_id"], contact_id=s["ana"], direction="inbound", content="gracias",
                        status="delivered", created_at=now - timedelta(minutes=1)),
            ])
            await db.commit()
        out = await _chat(s, "ana")
        assert [m["content"] for m in out["messages"]] == [
            "hola", "Hola Ana López, 2x1 en fundas en Barbería Don Pepe", "gracias",
        ]
        promo = _promos(out)[0]
        assert promo["role"] == "assistant" and promo["promo"]["id"] == str(camp.id)
        assert promo["promo"]["title"] == "Fundas"
    finally:
        await _cleanup(s["user_id"])


@pytest.mark.asyncio
async def test_whatsapp_promo_shows_in_chat_once():
    s = await _seed()
    try:
        c = await _seed_promos(s)
        async with AsyncSessionLocal() as db:
            # La misma campaña dejó dos mensajes (banner por WhatsApp y su texto).
            db.add(Message(advertiser_id=s["user_id"], contact_id=s["ana"], campaign_id=c["promo"],
                           direction="outbound", content="Hola Ana, este viernes 2x1", status="sent"))
            await db.commit()
        promos = _promos(await _chat(s, "ana"))
        assert [p["promo"]["id"] for p in promos] == [str(c["promo"])]
        assert promos[0]["promo"]["image_url"] == "https://cdn.test/ana.png"
    finally:
        await _cleanup(s["user_id"])


@pytest.mark.asyncio
async def test_chat_promo_coupon_only_when_valid():
    s = await _seed()
    try:
        c = await _seed_promos(s)
        promo = _promos(await _chat(s, "ana"))[0]
        assert promo["promo"]["coupon"]["code"] == f"PRO{s['tag']}"
        assert promo["promo"]["coupon"]["expires_at"]

        async with AsyncSessionLocal() as db:
            coupon = (await db.execute(select(Coupon).where(Coupon.campaign_id == c["promo"]))).scalar_one()
            coupon.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
            await db.commit()
        promo = _promos(await _chat(s, "ana"))[0]
        assert promo["promo"]["coupon"] is None
    finally:
        await _cleanup(s["user_id"])


@pytest.mark.asyncio
async def test_chat_never_shows_promos_not_received():
    s = await _seed()
    try:
        c = await _seed_promos(s)
        ana = [p["promo"]["id"] for p in _promos(await _chat(s, "ana"))]
        # Ni la de Beto ni el testimonio ("voces" no es promoción).
        assert ana == [str(c["promo"])]
        beto = [p["promo"]["id"] for p in _promos(await _chat(s, "beto"))]
        assert beto == [str(c["beto_only"])]
    finally:
        await _cleanup(s["user_id"])


@pytest.mark.asyncio
async def test_want_it_gives_bot_the_promo_context():
    s = await _seed()
    try:
        c = await _seed_promos(s)
        out, rag = await _web_chat(s, "¡La quiero! — 2x1 en cortes", promo_id=str(c["promo"]))
        assert out["reply"] == "¡Claro! Te la aparto."
        context = rag.await_args.kwargs["conversation_history"][-1]
        assert context["role"] == "assistant"
        assert "2x1 en cortes" in context["content"] and f"PRO{s['tag']}" in context["content"]
        # Y junto al contexto del negocio: como turno de la plática solo, el modelo
        # lo ignoraba en producción ("responde SOLO con el contexto") — 13-oct.
        note = rag.await_args.kwargs["extra_note"]
        assert "2x1 en cortes" in note and f"PRO{s['tag']}" in note
    finally:
        await _cleanup(s["user_id"])


@pytest.mark.asyncio
@pytest.mark.parametrize("which", ["beto_only", "garbage"])
async def test_want_it_with_foreign_or_bad_promo_gives_bot_nothing(which):
    # Un promo_id ajeno no debe filtrarle al bot (ni al cliente) la promo o el cupón de otro.
    s = await _seed()
    try:
        c = await _seed_promos(s)
        promo_id = str(c[which]) if which in c else "no-es-uuid"
        _, rag = await _web_chat(s, "¡La quiero!", promo_id=promo_id)
        history = rag.await_args.kwargs["conversation_history"]
        assert not any("Promoción vigente" in h["content"] for h in history)
        assert rag.await_args.kwargs["extra_note"] == ""
    finally:
        await _cleanup(s["user_id"])


@pytest.mark.asyncio
async def test_new_promo_appears_in_open_chat():
    s = await _seed()
    try:
        before = datetime.now(timezone.utc) - timedelta(seconds=1)
        c = await _seed_promos(s)
        # El chat abierto pregunta "¿algo nuevo desde before?": la promo llega sola.
        fresh = _promos(await _chat(s, "ana", after=before.isoformat()))
        assert [p["promo"]["id"] for p in fresh] == [str(c["promo"])]
        # Y no se repite en la siguiente vuelta.
        later = datetime.now(timezone.utc).isoformat()
        assert _promos(await _chat(s, "ana", after=later)) == []
    finally:
        await _cleanup(s["user_id"])


@pytest.mark.asyncio
async def test_inbox_sees_which_promo():
    s = await _seed()
    try:
        c = await _seed_promos(s)
        await _web_chat(s, "¡La quiero! — 2x1 en cortes", promo_id=str(c["promo"]))
        async with AsyncSessionLocal() as db:
            conv = (await db.execute(select(Conversation).where(Conversation.contact_id == s["ana"]))).scalar_one()
        assert conv.messages[-2] == {"role": "user", "content": "¡La quiero! — 2x1 en cortes", "channel": "web"}
        # El contexto interno es solo para el bot: no queda en la plática del Inbox.
        assert not any("Promoción vigente" in m["content"] for m in conv.messages)
    finally:
        await _cleanup(s["user_id"])


@pytest.mark.asyncio
async def test_radio_promo_brings_its_audio_to_the_chat():
    s = await _seed()
    try:
        async with AsyncSessionLocal() as db:
            camp = Campaign(advertiser_id=s["user_id"], name="Micas", type="promo", message_text="2 micas x 1",
                            ab_test={"campaign_mode": "radio", "audio_url": "https://cdn.test/cuna.mp3"})
            db.add(camp)
            await db.flush()
            db.add(Message(advertiser_id=s["user_id"], contact_id=s["ana"], campaign_id=camp.id,
                           direction="outbound", content="[WEB] Micas", status="sent"))
            await db.commit()
        promo = _promos(await _chat(s, "ana"))[0]
        assert promo["promo"]["audio_url"] == "https://cdn.test/cuna.mp3"
    finally:
        await _cleanup(s["user_id"])
