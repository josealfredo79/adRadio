"""Real-DB integration tests for widget.py — zero coverage existed
before this file. Covers the embeddable snippet's HTML/JS templating
(default fallbacks + single-quote escaping to prevent breaking out of
the inline JS string), the public preview endpoint's 404 + config
passthrough, and update/get config's color/greeting/position
validation."""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import delete
from starlette.requests import Request

from app.api.v1.widget import get_widget_config, get_widget_snippet, update_widget_config, widget_chat, widget_preview
from app.database import AsyncSessionLocal, engine
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
