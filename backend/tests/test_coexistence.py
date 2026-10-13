"""Coexistencia — un test por caso de docs/specs/2026-10-12-coexistencia.md.
BD y Redis de verdad para el servicio; solo Meta (API de pago) se simula."""
import contextlib
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import delete, select

from app.database import AsyncSessionLocal, engine
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User
from app.services import coexistence_service as coex
from app.services.inbound_pipeline import InboundMessage, process_inbound_message
from app.services.portal_service import whatsapp_replies_this_month
from tests.test_portal_web_shift import FakeRedis

BUSINESS = "5219531112233"
CUSTOMER = "5219535550001"
PHONE_ID = "pn-coex-"


class TtlRedis(FakeRedis):
    """FakeRedis que recuerda el TTL de setex, para revisar los 30 min."""

    def __init__(self):
        super().__init__()
        self.ttl: dict = {}

    async def setex(self, k, ttl, v):
        self.store[k] = v
        self.ttl[k] = ttl


async def _seed():
    await engine.dispose()
    phone_id = PHONE_ID + uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="CityCell",
                    meta_phone_number_id=phone_id, meta_waba_id="waba-" + phone_id,
                    meta_display_phone_number="+" + BUSINESS, meta_connection_status="connected",
                    meta_coexistence=True)
        db.add(user)
        await db.commit()
        return user.id, phone_id


async def _cleanup(user_id):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        for model in (Message, Conversation, Contact):
            await db.execute(delete(model).where(model.advertiser_id == user_id))
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()
    await engine.dispose()


def _echo(to=CUSTOMER, text="Sí, ya te lo aparto", mid=None, ts=1760300000):
    return {"from": BUSINESS, "to": to, "id": mid or f"wamid.{uuid.uuid4().hex}", "timestamp": str(ts),
            "type": "text", "text": {"body": text}}


async def _run(user_id, fn, *args):
    """Llama un manejador del servicio con el negocio recién leído. handle_echoes
    recibe además Redis: _run(uid, coex.handle_echoes, redis, value)."""
    async with AsyncSessionLocal() as db:
        user = await db.get(User, user_id)
        if fn is coex.handle_echoes:
            redis, value = args
            return await fn(db, redis, user, value)
        return await fn(db, user, *args)


async def _messages(user_id):
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(Message).where(Message.advertiser_id == user_id)
                                 .order_by(Message.created_at))).scalars().all()


async def _contacts(user_id):
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(Contact).where(Contact.advertiser_id == user_id))).scalars().all()


async def _conv(user_id):
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(Conversation).where(Conversation.advertiser_id == user_id))).scalars().all()


class TestOwnerMessagesFromPhone:
    @pytest.mark.asyncio
    async def test_caso4_echo_shows_in_inbox_marked_from_phone_and_is_free(self):
        user_id, _ = await _seed()
        try:
            async with AsyncSessionLocal() as db:
                db.add(Contact(advertiser_id=user_id, name="Ana", phone="+" + CUSTOMER))
                await db.commit()
            with patch("app.services.realtime.publish_conversation_event", AsyncMock()):
                assert await _run(user_id, coex.handle_echoes, None, {"message_echoes": [_echo()]}) == 1
            [msg] = await _messages(user_id)
            assert (msg.direction, msg.sender, msg.channel, msg.content) == ("outbound", "owner", "app", "Sí, ya te lo aparto")
            [conv] = await _conv(user_id)
            assert conv.messages[-1] == {"role": "assistant", "content": "Sí, ya te lo aparto", "sender": "owner", "channel": "app"}
            # No cuenta como respuesta de WhatsApp cobrada del mes.
            async with AsyncSessionLocal() as db:
                assert await whatsapp_replies_this_month(db, None, user_id) == 0
            assert len(await _contacts(user_id)) == 1  # usó el contacto que ya existía
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso4_same_echo_twice_is_saved_once(self):
        user_id, _ = await _seed()
        try:
            echo = _echo(mid="wamid.REPETIDO")
            with patch("app.services.realtime.publish_conversation_event", AsyncMock()):
                await _run(user_id, coex.handle_echoes, None, {"message_echoes": [echo]})
                assert await _run(user_id, coex.handle_echoes, None, {"message_echoes": [echo]}) == 0
            assert len(await _messages(user_id)) == 1
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso5_echo_to_unknown_number_creates_contact(self):
        user_id, _ = await _seed()
        try:
            with patch("app.services.realtime.publish_conversation_event", AsyncMock()):
                await _run(user_id, coex.handle_echoes, None, {"message_echoes": [_echo(to="5219539998877")]})
            [contact] = await _contacts(user_id)
            assert contact.phone == "+5219539998877" and contact.consent_status == "unconfirmed"
            assert len(await _conv(user_id)) == 1
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso6_echo_silences_bot_for_that_customer_30_min(self):
        user_id, _ = await _seed()
        redis = TtlRedis()
        try:
            with patch("app.services.realtime.publish_conversation_event", AsyncMock()):
                await _run(user_id, coex.handle_echoes, redis, {"message_echoes": [_echo()]})
            [contact] = await _contacts(user_id)
            key = coex.owner_active_key(user_id, contact.id)
            assert redis.ttl[key] == 30 * 60
            assert await coex.owner_is_attending(redis, user_id, contact.id) is True
            # Otro cliente: el bot sigue normal.
            assert await coex.owner_is_attending(redis, user_id, uuid.uuid4()) is False
            # Pasados los 30 min (la llave venció): el bot vuelve.
            del redis.store[key]
            assert await coex.owner_is_attending(redis, user_id, contact.id) is False
        finally:
            await _cleanup(user_id)


class TestBotStaysQuietWhileOwnerAttends:
    """La compuerta del pipeline (mismo estilo que test_inbound_pipeline_handoff)."""

    def _db(self, mock_db, contact):
        none = MagicMock()
        none.scalar_one_or_none.return_value = None
        found = MagicMock()
        found.scalar_one_or_none.return_value = contact
        # idempotencia, contacto, conversación escalada (no hay)
        mock_db.execute.side_effect = [none, found, none]

    @pytest.mark.asyncio
    async def test_caso6_customer_writes_while_owner_attends_bot_does_not_answer(self, mock_db, test_user):
        test_user.meta_coexistence = True
        contact = MagicMock(id="contact-1")
        self._db(mock_db, contact)
        conv = MagicMock(messages=[])
        send = AsyncMock()
        with patch("app.services.coexistence_service.owner_is_attending", AsyncMock(return_value=True)), \
                patch("app.services.web_conversation.open_conversation", AsyncMock(return_value=conv)), \
                patch("app.services.inbound_pipeline.publish_conversation_event", AsyncMock()), \
                patch("app.services.inbound_pipeline.answer_with_rag", new=AsyncMock()) as rag:
            out = await process_inbound_message(mock_db, InboundMessage(
                advertiser=test_user, from_number="+" + CUSTOMER, body_text="¿y el precio?",
                external_message_id="wamid.C6"), send=send, send_owner=send)
        assert out == {"message": "ok"}
        send.assert_not_called()
        rag.assert_not_called()
        assert mock_db.add.call_args.args[0].content == "¿y el precio?"  # queda en el Inbox
        assert conv.messages[-1] == {"role": "user", "content": "¿y el precio?"}

    @pytest.mark.asyncio
    async def test_caso6_not_coexistence_never_checks_the_lock(self, mock_db, test_user):
        test_user.meta_coexistence = False
        self._db(mock_db, MagicMock(id="contact-1"))
        attending = AsyncMock(return_value=True)
        # más adelante el pipeline necesita más mocks; aquí solo importa la compuerta
        with patch("app.services.coexistence_service.owner_is_attending", attending), \
                patch("app.services.inbound_pipeline.answer_with_rag", new=AsyncMock()), \
                contextlib.suppress(Exception):
            await process_inbound_message(mock_db, InboundMessage(
                advertiser=test_user, from_number="+" + CUSTOMER, body_text="hola",
                external_message_id="wamid.C6b"), send=AsyncMock(), send_owner=AsyncMock())
        attending.assert_not_awaited()


class TestContactsFromPhone:
    @pytest.mark.asyncio
    async def test_caso7_contacts_arrive_unconfirmed_and_existing_untouched(self):
        user_id, _ = await _seed()
        try:
            async with AsyncSessionLocal() as db:
                db.add(Contact(advertiser_id=user_id, name="Ana de siempre", phone="+5219535550001",
                               consent_status="confirmed"))
                await db.commit()
            sync = {"state_sync": [
                {"type": "contact", "action": "add", "contact": {"full_name": "Ana López", "phone_number": "5219535550001"}},
                {"type": "contact", "action": "add", "contact": {"full_name": "Beto", "phone_number": "529535550002"}},
                {"type": "contact", "action": "remove", "contact": {"full_name": "Carla", "phone_number": "5219535550003"}},
            ]}
            assert await _run(user_id, coex.handle_contacts, sync) == 1
            by_phone = {c.phone: c for c in await _contacts(user_id)}
            assert by_phone["+5219535550001"].name == "Ana de siempre"  # no se tocó
            assert by_phone["+5219535550001"].consent_status == "confirmed"
            assert by_phone["+529535550002"].name == "Beto"
            assert by_phone["+529535550002"].consent_status == "unconfirmed"  # sin campañas hasta que escriba
            assert by_phone["+529535550002"].source == "whatsapp_app"
            assert "+5219535550003" not in by_phone
        finally:
            await _cleanup(user_id)


def _history(threads, errors=None):
    chunk = {"metadata": {"phase": 0, "chunk_order": 1, "progress": 100}, "threads": threads}
    if errors:
        chunk["errors"] = errors
    return {"history": [chunk]}


class TestHistory:
    @pytest.mark.asyncio
    async def test_caso8_history_lands_with_real_dates_once_and_without_groups(self):
        user_id, _ = await _seed()
        try:
            thread = {"id": CUSTOMER, "messages": [
                {"from": CUSTOMER, "id": "wamid.H1", "timestamp": "1750000000", "type": "text", "text": {"body": "¿Tienen fundas?"}},
                {"from": BUSINESS, "id": "wamid.H2", "timestamp": "1750000060", "type": "text", "text": {"body": "Sí, de $150"}},
                {"from": CUSTOMER, "id": "wamid.H3", "timestamp": "1750000120", "type": "image", "image": {"caption": "esta"}},
            ]}
            group = {"id": "120363000000@g.us", "messages": [
                {"from": CUSTOMER, "id": "wamid.G1", "timestamp": "1750000000", "type": "text", "text": {"body": "grupo"}}]}
            payload = _history([thread, group])
            assert await _run(user_id, coex.handle_history, payload) == 3
            assert await _run(user_id, coex.handle_history, payload) == 0  # Meta lo repite: nada doble
            msgs = await _messages(user_id)
            assert [(m.direction, m.content) for m in msgs] == [
                ("inbound", "¿Tienen fundas?"), ("outbound", "Sí, de $150"), ("inbound", "📎 archivo: esta")]
            assert msgs[0].created_at == datetime.fromtimestamp(1750000000, tz=timezone.utc)
            assert msgs[1].sender == "owner" and msgs[1].channel == "app"
            [conv] = await _conv(user_id)
            assert [t["content"] for t in conv.messages] == ["¿Tienen fundas?", "Sí, de $150", "📎 archivo: esta"]
            assert [c.phone for c in await _contacts(user_id)] == ["+" + CUSTOMER]
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso9_owner_declined_sharing_history(self):
        user_id, _ = await _seed()
        try:
            payload = _history([], errors=[{"code": 2593109, "title": "History sharing declined"}])
            assert await _run(user_id, coex.handle_history, payload) == 0
            assert await _messages(user_id) == []
        finally:
            await _cleanup(user_id)


class TestDisconnect:
    @pytest.mark.asyncio
    async def test_caso10_business_disconnected_from_its_app(self):
        from app.core.crypto import encrypt_secret
        from app.services.meta_service import _connection

        user_id, _ = await _seed()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                enc = encrypt_secret("EAAtoken")
                user.meta_token_cipher, user.meta_token_iv, user.meta_token_tag = enc.cipher, enc.iv, enc.tag
                await db.commit()
                assert _connection(user) is not None  # antes: el bot sí puede enviar
            assert await _run(user_id, coex.handle_account_update,
                              {"phone_number": BUSINESS, "event": "PARTNER_REMOVED",
                               "disconnection_info": {"reason": "x", "initiated_by": "BUSINESS"}}) is True
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                assert (user.meta_connection_status, user.meta_coexistence) == ("not_connected", False)
            # El envío del bot revisa ese estado y deja de usar el número.
            assert _connection(user) is None
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso10_other_account_events_change_nothing(self):
        user_id, _ = await _seed()
        try:
            assert await _run(user_id, coex.handle_account_update, {"event": "VERIFIED_ACCOUNT"}) is False
            async with AsyncSessionLocal() as db:
                assert (await db.get(User, user_id)).meta_connection_status == "connected"
        finally:
            await _cleanup(user_id)


class TestWebhookDispatch:
    @pytest.mark.asyncio
    async def test_caso12_events_for_unknown_numbers_are_ignored(self):
        from app.api.v1.webhooks_pkg.meta_incoming import _handle_coexistence

        async with AsyncSessionLocal() as db:
            for field in ("smb_message_echoes", "smb_app_state_sync", "history", "account_update"):
                await _handle_coexistence(db, field, "waba-que-no-existe",
                                          {"metadata": {"phone_number_id": "pn-que-no-existe"},
                                           "message_echoes": [_echo()], "event": "PARTNER_REMOVED"})

    @pytest.mark.asyncio
    async def test_caso12_echo_webhook_reaches_the_right_business(self):
        from app.api.v1.webhooks_pkg.meta_incoming import _handle_coexistence

        user_id, phone_id = await _seed()
        try:
            with patch("app.core.redis.get_redis_optional", AsyncMock(return_value=None)), \
                    patch("app.services.realtime.publish_conversation_event", AsyncMock()):
                async with AsyncSessionLocal() as db:
                    await _handle_coexistence(db, "smb_message_echoes", None, {
                        "metadata": {"phone_number_id": phone_id}, "message_echoes": [_echo()]})
            assert len(await _messages(user_id)) == 1
        finally:
            await _cleanup(user_id)


class TestIsOnBusinessApp:
    @pytest.mark.asyncio
    async def test_caso2_reads_is_on_biz_app_from_meta(self):
        import httpx

        seen = {}

        def handler(request: httpx.Request):
            seen["fields"] = request.url.params.get("fields")
            return httpx.Response(200, json={"is_on_biz_app": True, "platform_type": "CLOUD_API", "id": "phone-1"})

        real_client = httpx.AsyncClient
        with patch("httpx.AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(handler))):
            assert await coex.is_on_business_app("phone-1", "tok") is True
        assert seen["fields"] == "is_on_biz_app,platform_type"

    @pytest.mark.asyncio
    async def test_caso2_unknown_when_meta_fails(self):
        import httpx

        real_client = httpx.AsyncClient
        with patch("httpx.AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(
                lambda r: httpx.Response(400, json={"error": {"message": "x"}})))):
            assert await coex.is_on_business_app("phone-1", "tok") is None
