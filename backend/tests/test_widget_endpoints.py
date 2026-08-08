"""Real-DB integration tests for widget.py — zero coverage existed
before this file. Covers the embeddable snippet's HTML/JS templating
(default fallbacks + single-quote escaping to prevent breaking out of
the inline JS string), the public preview endpoint's 404 + config
passthrough, and update/get config's color/greeting/position
validation."""
import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, func, select
from starlette.requests import Request

from app.api.v1.widget import (
    get_widget_config, get_widget_snippet, update_widget_config, widget_capture_lead, widget_chat, widget_preview,
)
from app.database import AsyncSessionLocal, engine
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User


def _request(host: str | None = None, method: str = "GET") -> Request:
    scope = {
        "type": "http", "method": method, "path": "/api/v1/widget/preview/x", "headers": [],
        "client": (host or f"test-{uuid.uuid4()}", 123), "query_string": b"",
    }
    return Request(scope)


async def _seed_user(**overrides):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", **overrides)
        db.add(user)
        await db.commit()
        return user.id


async def _cleanup(user_ids):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(User).where(User.id.in_(user_ids)))
        await db.commit()
    await engine.dispose()


class TestGetWidgetSnippet:
    @pytest.mark.asyncio
    async def test_uses_defaults_when_unset(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                out = await get_widget_snippet(current_user=user)
            assert "phone: ''" in out["snippet"]
            assert "agent: 'Asistente'" in out["snippet"]
            assert "color: '#25D366'" in out["snippet"]
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_escapes_single_quotes_to_avoid_breaking_out_of_js_string(self):
        user_id = await _seed_user(business_name="Tony's Tacos")
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                out = await get_widget_snippet(current_user=user)
            assert "business: 'Tony\\'s Tacos'" in out["snippet"]
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_uses_custom_values(self):
        user_id = await _seed_user(whatsapp_number="+525511112222", widget_color="#ff0000")
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                out = await get_widget_snippet(current_user=user)
            assert "phone: '+525511112222'" in out["snippet"]
            assert "color: '#ff0000'" in out["snippet"]
        finally:
            await _cleanup([user_id])


class TestWidgetPreview:
    @pytest.mark.asyncio
    async def test_unknown_advertiser_returns_404(self):
        async with AsyncSessionLocal() as db:
            with pytest.raises(HTTPException) as exc_info:
                await widget_preview(request=_request(), advertiser_id=uuid.uuid4(), db=db)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_public_config(self):
        user_id = await _seed_user(business_name="Mi Negocio", widget_position="left")
        try:
            async with AsyncSessionLocal() as db:
                out = await widget_preview(request=_request(), advertiser_id=user_id, db=db)
            assert out["business"] == "Mi Negocio"
            assert out["position"] == "left"
        finally:
            await _cleanup([user_id])


class TestUpdateWidgetConfig:
    @pytest.mark.asyncio
    async def test_rejects_invalid_hex_color(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with pytest.raises(HTTPException) as exc_info:
                    await update_widget_config(
                        request=_request(), body={"color": "notacolor"}, current_user=user, db=db, _=None, redis=None,
                    )
                assert exc_info.value.status_code == 400
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_rejects_greeting_over_200_chars(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with pytest.raises(HTTPException) as exc_info:
                    await update_widget_config(
                        request=_request(), body={"greeting": "x" * 201}, current_user=user, db=db, _=None, redis=None,
                    )
                assert exc_info.value.status_code == 400
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_rejects_invalid_position(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with pytest.raises(HTTPException) as exc_info:
                    await update_widget_config(
                        request=_request(), body={"position": "center"}, current_user=user, db=db, _=None, redis=None,
                    )
                assert exc_info.value.status_code == 400
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_updates_and_persists_valid_fields(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                result = await update_widget_config(
                    request=_request(), body={"color": "#abc", "greeting": "Hola!", "position": "left"},
                    current_user=user, db=db, _=None, redis=None,
                )
            assert "message" in result

            async with AsyncSessionLocal() as db:
                reloaded = await db.get(User, user_id)
                assert reloaded.widget_color == "#abc"
                assert reloaded.widget_greeting == "Hola!"
                assert reloaded.widget_position == "left"
        finally:
            await _cleanup([user_id])


class TestWidgetChat:
    """The widget's real in-page chat — a website visitor talks to the
    advertiser's bot directly, no WhatsApp involved. Session history lives in
    Redis only (mirrors chat_demo.py), never in Contact/Conversation/Message."""

    @pytest.mark.asyncio
    async def test_unknown_advertiser_returns_404(self):
        async with AsyncSessionLocal() as db:
            with pytest.raises(HTTPException) as exc_info:
                await widget_chat(
                    request=_request(method="POST"), advertiser_id=uuid.uuid4(),
                    body={"message": "hola"}, db=db, redis=None,
                )
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_empty_message_returns_400(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                with pytest.raises(HTTPException) as exc_info:
                    await widget_chat(
                        request=_request(method="POST"), advertiser_id=user_id,
                        body={"message": "   "}, db=db, redis=None,
                    )
                assert exc_info.value.status_code == 400
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_message_too_long_returns_400(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                with pytest.raises(HTTPException) as exc_info:
                    await widget_chat(
                        request=_request(method="POST"), advertiser_id=user_id,
                        body={"message": "x" * 501}, db=db, redis=None,
                    )
                assert exc_info.value.status_code == 400
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_returns_rag_reply_and_generates_session_id(self):
        user_id = await _seed_user(business_name="Tacos El Primo")
        try:
            with patch("app.services.rag_service.answer_with_rag", new_callable=AsyncMock) as mock_rag:
                mock_rag.return_value = "Abrimos de 9am a 9pm."
                async with AsyncSessionLocal() as db:
                    out = await widget_chat(
                        request=_request(method="POST"), advertiser_id=user_id,
                        body={"message": "¿A qué hora abren?"}, db=db, redis=None,
                    )
            assert out["reply"] == "Abrimos de 9am a 9pm."
            assert out["session_id"]
            call_kwargs = mock_rag.call_args.kwargs
            assert call_kwargs["advertiser_id"] == str(user_id)
            assert call_kwargs["business_name"] == "Tacos El Primo"
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_falls_back_to_generic_reply_on_rag_error(self):
        user_id = await _seed_user()
        try:
            with patch("app.services.rag_service.answer_with_rag", new_callable=AsyncMock) as mock_rag:
                mock_rag.side_effect = Exception("claude down")
                async with AsyncSessionLocal() as db:
                    out = await widget_chat(
                        request=_request(method="POST"), advertiser_id=user_id,
                        body={"message": "hola"}, db=db, redis=None,
                    )
            assert "asesor" in out["reply"].lower()
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_reuses_session_history_from_redis(self):
        user_id = await _seed_user()
        try:
            fake_redis = AsyncMock()
            fake_redis.get.return_value = None
            with patch("app.services.rag_service.answer_with_rag", new_callable=AsyncMock) as mock_rag:
                mock_rag.return_value = "primera respuesta"
                async with AsyncSessionLocal() as db:
                    await widget_chat(
                        request=_request(method="POST"), advertiser_id=user_id,
                        body={"message": "primer mensaje", "session_id": "sess-1"}, db=db, redis=fake_redis,
                    )
            # setex called with the accumulated [user, assistant] history for this session
            args, _ = fake_redis.setex.call_args
            assert args[0] == f"widget_chat:{user_id}:sess-1"
            stored_history = args[2]
            assert '"primer mensaje"' in stored_history
            assert '"primera respuesta"' in stored_history
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_routes_to_order_service_when_session_has_a_linked_contact(self):
        """A session that already captured a lead (POST /widget/lead) is
        linked to its Contact in Redis — an order-intent message should be
        handled by widget_order_service instead of falling through to RAG."""
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                contact = Contact(advertiser_id=user_id, name="Ana", phone="+525511115555", source="widget")
                db.add(contact)
                await db.commit()
                await db.refresh(contact)

            def _get_side_effect(key):
                if key.startswith("widget_session_contact:"):
                    return str(contact.id)
                return None

            fake_redis = AsyncMock()
            fake_redis.get.side_effect = _get_side_effect

            with patch("app.services.rag_service.answer_with_rag", new_callable=AsyncMock) as mock_rag:
                async with AsyncSessionLocal() as db:
                    out = await widget_chat(
                        request=_request(method="POST"), advertiser_id=user_id,
                        body={"message": "quiero pedir 2 pizzas", "session_id": "sess-order"},
                        db=db, redis=fake_redis,
                    )
            assert "nombre" in out["reply"].lower()
            mock_rag.assert_not_called()
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_falls_through_to_rag_when_no_order_intent_despite_linked_contact(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                contact = Contact(advertiser_id=user_id, name="Ana", phone="+525511116666", source="widget")
                db.add(contact)
                await db.commit()
                await db.refresh(contact)

            def _get_side_effect(key):
                if key.startswith("widget_session_contact:"):
                    return str(contact.id)
                return None

            fake_redis = AsyncMock()
            fake_redis.get.side_effect = _get_side_effect

            with patch("app.services.rag_service.answer_with_rag", new_callable=AsyncMock) as mock_rag:
                mock_rag.return_value = "Abrimos de 9 a 9."
                async with AsyncSessionLocal() as db:
                    out = await widget_chat(
                        request=_request(method="POST"), advertiser_id=user_id,
                        body={"message": "¿cuál es su horario?", "session_id": "sess-rag"},
                        db=db, redis=fake_redis,
                    )
            assert out["reply"] == "Abrimos de 9 a 9."
            mock_rag.assert_awaited_once()
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_appointment_intent_is_routed_before_order_intent(self):
        """'pedir cita' contains the bare word 'pedir', which alone would
        match order-intent keywords — appointment detection must win so this
        resolves to booking a slot, not to starting an order."""
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                contact = Contact(advertiser_id=user_id, name="Ana", phone="+525511119999", source="widget")
                db.add(contact)
                await db.commit()
                await db.refresh(contact)

            def _get_side_effect(key):
                if key.startswith("widget_session_contact:"):
                    return str(contact.id)
                return None

            fake_redis = AsyncMock()
            fake_redis.get.side_effect = _get_side_effect

            with patch("app.services.rag_service.answer_with_rag", new_callable=AsyncMock) as mock_rag:
                async with AsyncSessionLocal() as db:
                    out = await widget_chat(
                        request=_request(method="POST"), advertiser_id=user_id,
                        body={"message": "quiero pedir una cita para corte", "session_id": "sess-appt"},
                        db=db, redis=fake_redis,
                    )
            assert "día" in out["reply"].lower()
            mock_rag.assert_not_called()
        finally:
            await _cleanup([user_id])


class TestWidgetCaptureLead:
    """A widget visitor leaves their name/phone — turns the ephemeral chat
    into a real Contact/Conversation/Message so it shows up in Contacts/Inbox
    exactly like a WhatsApp lead."""

    @pytest.mark.asyncio
    async def test_unknown_advertiser_returns_404(self):
        async with AsyncSessionLocal() as db:
            with pytest.raises(HTTPException) as exc_info:
                await widget_capture_lead(
                    request=_request(method="POST"), advertiser_id=uuid.uuid4(),
                    body={"name": "Ana", "phone": "+525511112222"}, db=db, redis=None,
                )
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_missing_name_returns_400(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                with pytest.raises(HTTPException) as exc_info:
                    await widget_capture_lead(
                        request=_request(method="POST"), advertiser_id=user_id,
                        body={"name": "", "phone": "+525511112222"}, db=db, redis=None,
                    )
                assert exc_info.value.status_code == 400
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_invalid_phone_returns_400(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                with pytest.raises(HTTPException) as exc_info:
                    await widget_capture_lead(
                        request=_request(method="POST"), advertiser_id=user_id,
                        body={"name": "Ana", "phone": "123"}, db=db, redis=None,
                    )
                assert exc_info.value.status_code == 400
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_creates_contact_and_conversation_and_fires_webhook(self):
        user_id = await _seed_user()
        try:
            with patch("app.services.webhook_dispatcher.dispatch_webhook_event", new_callable=AsyncMock) as mock_hook:
                async with AsyncSessionLocal() as db:
                    out = await widget_capture_lead(
                        request=_request(method="POST"), advertiser_id=user_id,
                        body={"name": "Ana López", "phone": "+525511112222"}, db=db, redis=None,
                    )
            assert out["message"] == "ok"
            mock_hook.assert_awaited_once()
            call_kwargs = mock_hook.call_args.kwargs
            assert call_kwargs["advertiser_id"] == user_id

            async with AsyncSessionLocal() as db:
                c = (await db.execute(
                    select(Contact).where(Contact.id == uuid.UUID(out["contact_id"]))
                )).scalar_one()
                assert c.name == "Ana López"
                assert c.source == "widget"
                conv = (await db.execute(
                    select(Conversation).where(Conversation.contact_id == c.id)
                )).scalar_one_or_none()
                assert conv is not None
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_reuses_existing_contact_by_phone_and_skips_webhook(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                existing = Contact(advertiser_id=user_id, name="Ya Existía", phone="+525511113333", source="manual")
                db.add(existing)
                await db.commit()
                await db.refresh(existing)

            with patch("app.services.webhook_dispatcher.dispatch_webhook_event", new_callable=AsyncMock) as mock_hook:
                async with AsyncSessionLocal() as db:
                    out = await widget_capture_lead(
                        request=_request(method="POST"), advertiser_id=user_id,
                        body={"name": "Otro nombre", "phone": "+525511113333"}, db=db, redis=None,
                    )
            assert out["contact_id"] == str(existing.id)
            mock_hook.assert_not_called()

            async with AsyncSessionLocal() as db:
                count = (await db.execute(
                    select(func.count()).select_from(Contact).where(
                        Contact.advertiser_id == user_id, Contact.phone == "+525511113333"
                    )
                )).scalar_one()
                assert count == 1  # no duplicate created
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_pulls_redis_transcript_into_conversation_and_messages(self):
        user_id = await _seed_user()
        try:
            fake_redis = AsyncMock()
            fake_redis.get.return_value = json.dumps([
                {"role": "user", "content": "¿Tienen envíos a domicilio?"},
                {"role": "assistant", "content": "Sí, cubrimos toda la ciudad."},
            ])
            async with AsyncSessionLocal() as db:
                out = await widget_capture_lead(
                    request=_request(method="POST"), advertiser_id=user_id,
                    body={"name": "Luis", "phone": "+525511114444", "session_id": "sess-42"},
                    db=db, redis=fake_redis,
                )
            fake_redis.get.assert_awaited_once_with(f"widget_chat:{user_id}:sess-42")

            async with AsyncSessionLocal() as db:
                conv = (await db.execute(
                    select(Conversation).where(Conversation.contact_id == uuid.UUID(out["contact_id"]))
                )).scalar_one()
                assert len(conv.messages) == 2
                assert conv.messages[0]["content"] == "¿Tienen envíos a domicilio?"

                messages = (await db.execute(
                    select(Message).where(Message.contact_id == uuid.UUID(out["contact_id"]))
                )).scalars().all()
                assert len(messages) == 2
                directions = {m.direction for m in messages}
                assert directions == {"inbound", "outbound"}
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_generates_and_links_session_id_when_visitor_leaves_data_before_chatting(self):
        """A visitor can click 'Dejar mis datos' before ever sending a chat
        message — widget.js's own session_id is still null at that point.
        The endpoint must generate one, return it, and link it, so a
        follow-up /widget/chat call with that returned session_id resolves
        to this Contact (see widget.js's sessionId = data.session_id)."""
        user_id = await _seed_user()
        try:
            fake_redis = AsyncMock()
            fake_redis.get.return_value = None
            async with AsyncSessionLocal() as db:
                out = await widget_capture_lead(
                    request=_request(method="POST"), advertiser_id=user_id,
                    body={"name": "Luis", "phone": "+525511118888"}, db=db, redis=fake_redis,
                )
            assert out["session_id"]
            fake_redis.setex.assert_any_call(
                f"widget_session_contact:{user_id}:{out['session_id']}", 1800, out["contact_id"]
            )
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_links_session_to_contact_in_redis(self):
        user_id = await _seed_user()
        try:
            fake_redis = AsyncMock()
            fake_redis.get.return_value = None
            async with AsyncSessionLocal() as db:
                out = await widget_capture_lead(
                    request=_request(method="POST"), advertiser_id=user_id,
                    body={"name": "Luis", "phone": "+525511117777", "session_id": "sess-link"},
                    db=db, redis=fake_redis,
                )
            fake_redis.setex.assert_any_call(
                f"widget_session_contact:{user_id}:sess-link", 1800, out["contact_id"]
            )
        finally:
            await _cleanup([user_id])


class TestGetWidgetConfig:
    @pytest.mark.asyncio
    async def test_returns_defaults_when_unset(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                out = await get_widget_config(current_user=user)
            assert out == {"color": "#25D366", "greeting": "¡Hola! ¿En qué puedo ayudarte?", "position": "right"}
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_returns_custom_values(self):
        user_id = await _seed_user(widget_color="#000000", widget_position="left")
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                out = await get_widget_config(current_user=user)
            assert out["color"] == "#000000"
            assert out["position"] == "left"
        finally:
            await _cleanup([user_id])
