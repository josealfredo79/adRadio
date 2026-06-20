"""
Tests extendidos para servicios de IaRadio.
Mockea APIs externas (Claude, OpenAI, Twilio, Google, etc.)
"""
import uuid
import json
import base64
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock
import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestClaudeService:
    """Tests para el servicio de Claude (sin API real)."""

    @patch("app.services.claude_service._get_client")
    @pytest.mark.asyncio
    async def test_generate_campaign_variants(self, mock_get_client):
        mock_client = AsyncMock()
        msg = MagicMock()
        msg.content = [MagicMock(text="🔥 Oferta especial\n---\n✨ Descuento único\n---\n🎉 No te lo pierdas")]
        mock_client.messages.create.return_value = msg
        mock_get_client.return_value = mock_client

        from app.services.claude_service import generate_campaign_variants
        variants = await generate_campaign_variants("promo", "Mi Negocio", "vender más")

        assert isinstance(variants, list)
        assert len(variants) == 3
        assert "Oferta" in variants[0]

    @patch("app.services.claude_service._get_client")
    @pytest.mark.asyncio
    async def test_generate_bot_response(self, mock_get_client):
        mock_client = AsyncMock()
        msg = MagicMock()
        msg.content = [MagicMock(text="Claro, te ayudo con eso 😊")]
        mock_client.messages.create.return_value = msg
        mock_get_client.return_value = mock_client

        from app.services.claude_service import generate_bot_response
        reply = await generate_bot_response(
            advertiser_context="Vendemos tacos",
            conversation_history=[],
            user_message="¿Qué venden?",
            business_name="Taquería",
        )
        assert "ayudo" in reply

    def test_personalize_message(self):
        from app.services.claude_service import personalize_message

        contact = {"name": "Juan Pérez", "city": "CDMX"}
        advertiser = {"business_name": "Mi Tienda", "city": "Querétaro"}

        msg = personalize_message("Hola {{nombre}} de {{ciudad}}", contact, advertiser)
        assert "Juan Pérez" in msg
        assert "CDMX" in msg

        msg2 = personalize_message("Oferta de {{negocio}}", contact, advertiser)
        assert "Mi Tienda" in msg2

    def test_personalize_message_fallback(self):
        from app.services.claude_service import personalize_message

        msg = personalize_message("Hola {{nombre}} {{ciudad}} {{negocio}}", {}, {})
        assert "amigo" in msg
        assert "tu ciudad" in msg
        assert "nosotros" in msg

    def test_detect_order_intent(self):
        from app.services.claude_service import detect_order_intent

        assert detect_order_intent("quiero pedir una pizza") is True
        assert detect_order_intent("cuánto cuesta") is False
        assert detect_order_intent("Hola buenos días") is False
        assert detect_order_intent("") is False
        assert detect_order_intent("QUIERO COMPRAR") is True

    @pytest.mark.asyncio
    async def test_detect_order_intent_async(self):
        from app.services.claude_service import detect_order_intent_async

        assert await detect_order_intent_async("quiero pedir") is True
        assert await detect_order_intent_async("hola") is False

    @patch("app.services.claude_service._get_client")
    @pytest.mark.asyncio
    async def test_generate_sequence_messages(self, mock_get_client):
        mock_client = AsyncMock()
        msg = MagicMock()
        msg.content = [MagicMock(text="📢 Día 1\n---\n💡 Día 3\n---\n🎯 Día 5")]
        mock_client.messages.create.return_value = msg
        mock_get_client.return_value = mock_client

        from app.services.claude_service import generate_sequence_messages
        seq = await generate_sequence_messages("Tienda", "promo")
        assert len(seq) == 3

    @patch("app.services.claude_service._get_client")
    @pytest.mark.asyncio
    async def test_generate_saga_episodes(self, mock_get_client):
        mock_client = AsyncMock()
        msg = MagicMock()
        msg.content = [MagicMock(text="📻 Episodio 1:...\n---\n📻 Episodio 2:...\n---\n📻 Episodio 3:...\n---\n📻 Episodio 4:...")]
        mock_client.messages.create.return_value = msg
        mock_get_client.return_value = mock_client

        from app.services.claude_service import generate_saga_episodes
        eps = await generate_saga_episodes("Negocio", "Producto X")
        assert len(eps) == 4

    @patch("app.services.claude_service._get_client")
    @pytest.mark.asyncio
    async def test_detect_intent_tags(self, mock_get_client):
        mock_client = AsyncMock()
        msg = MagicMock()
        msg.content = [MagicMock(text='["interesado","precio"]')]
        mock_client.messages.create.return_value = msg
        mock_get_client.return_value = mock_client

        from app.services.claude_service import detect_intent_tags
        tags = await detect_intent_tags("¿Cuánto cuesta?")
        assert "interesado" in tags
        assert "precio" in tags

    @patch("app.services.claude_service._get_client")
    @pytest.mark.asyncio
    async def test_detect_intent_tags_parse_failure(self, mock_get_client):
        mock_client = AsyncMock()
        msg = MagicMock()
        msg.content = [MagicMock(text="not json at all")]
        mock_client.messages.create.return_value = msg
        mock_get_client.return_value = mock_client

        from app.services.claude_service import detect_intent_tags
        tags = await detect_intent_tags("Hola")
        assert tags == []

    @patch("app.services.claude_service._get_client")
    @pytest.mark.asyncio
    async def test_generate_voces_capsule(self, mock_get_client):
        mock_client = AsyncMock()
        msg = MagicMock()
        msg.content = [MagicMock(text="🎙️ Cápsula narrativa de radio...")]
        mock_client.messages.create.return_value = msg
        mock_get_client.return_value = mock_client

        from app.services.claude_service import generate_voces_capsule
        capsule = await generate_voces_capsule(
            "Mi Negocio",
            [{"name": "Ana", "text": "Excelente servicio"}],
            "ven a conocernos",
        )
        assert "Cápsula" in capsule


class TestEmbeddingService:
    """Tests para el servicio de embeddings."""

    @pytest.mark.asyncio
    async def test_chunk_text_basic(self):
        from app.services.embedding_service import chunk_text

        text = "palabra " * 1000
        chunks = chunk_text(text, chunk_size=100, overlap=20)
        assert len(chunks) > 1
        for c in chunks:
            assert len(c.split()) <= 100

    def test_chunk_text_small(self):
        from app.services.embedding_service import chunk_text

        chunks = chunk_text("texto corto")
        assert len(chunks) == 1
        assert chunks[0] == "texto corto"

    def test_chunk_text_empty(self):
        from app.services.embedding_service import chunk_text

        assert chunk_text("") == []
        assert chunk_text("   ") == []

    @patch("app.services.embedding_service.settings")
    @pytest.mark.asyncio
    async def test_get_embedding_openai(self, mock_settings):
        mock_settings.OPENAI_API_KEY = "sk-test"

        with patch("app.services.embedding_service._embed_openai", new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = [0.1] * 1024
            from app.services.embedding_service import get_embedding

            result = await get_embedding("test query")
            assert len(result) == 1024
            mock_embed.assert_awaited_once()

    @patch("app.services.embedding_service.settings")
    @pytest.mark.asyncio
    async def test_get_embedding_voyage(self, mock_settings):
        mock_settings.OPENAI_API_KEY = ""

        with patch("app.services.embedding_service._embed_voyage", new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = [0.2] * 1024
            from app.services.embedding_service import get_embedding

            result = await get_embedding("test query")
            assert len(result) == 1024
            mock_embed.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_embed_openai_mocked(self):
        with patch("app.services.embedding_service.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = "sk-test"
            with patch("openai.AsyncOpenAI") as mock_openai:
                mock_client = AsyncMock()
                mock_response = MagicMock()
                mock_response.data = [MagicMock(embedding=[0.5] * 1024)]
                mock_client.embeddings.create.return_value = mock_response
                mock_openai.return_value = mock_client

                from app.services.embedding_service import _embed_openai
                result = await _embed_openai("test")
                assert len(result) == 1024

    @pytest.mark.asyncio
    async def test_embed_voyage_success(self):
        with patch("app.services.embedding_service.settings") as mock_settings:
            mock_settings.VOYAGE_API_KEY = "voyage-test"
            with patch("voyageai.AsyncClient") as mock_voyage:
                mock_client = AsyncMock()
                mock_result = MagicMock()
                mock_result.embeddings = [[0.3] * 1024]
                mock_client.embed.return_value = mock_result
                mock_voyage.return_value = mock_client

                from app.services.embedding_service import _embed_voyage
                result = await _embed_voyage("test")
                assert len(result) == 1024




class TestRagService:
    """Tests para el servicio RAG."""

    @pytest.mark.asyncio
    async def test_answer_with_rag_fallback_with_user(self):
        with patch("app.services.rag_service.get_embedding", new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = [0.1] * 1024

            db = AsyncMock()

            class FakeResult:
                def fetchall(self):
                    return []

            db.execute = AsyncMock(return_value=FakeResult())

            user = MagicMock()
            user.business_name = "Taquería El Tío"
            user.bot_name = "Tito"
            user.bot_personality = "alegre y servicial"
            user.bot_instructions = None

            class FakeScalarResult:
                def scalar_one_or_none(self):
                    return user

            # After fetchall returns [], the second db.execute returns the user
            db.execute = AsyncMock(side_effect=[FakeResult(), FakeScalarResult()])

            from app.services.rag_service import answer_with_rag
            result = await answer_with_rag(
                str(uuid.uuid4()), "¿Qué hay?", [], db,
            )
            assert "Taquería" in result
            assert "Tito" in result

    @pytest.mark.asyncio
    async def test_answer_with_rag_with_context(self):
        with patch("app.services.rag_service.get_embedding", new_callable=AsyncMock) as mock_embed, \
             patch("app.services.rag_service.generate_bot_response", new_callable=AsyncMock) as mock_bot:
            mock_embed.return_value = [0.1] * 1024
            mock_bot.return_value = "Respuesta con contexto."

            db = AsyncMock()
            db_result = MagicMock()

            row1 = MagicMock()
            row1.chunk_text = "Vendemos tacos al pastor"
            row1.similarity = 0.85
            row2 = MagicMock()
            row2.chunk_text = "Tenemos horario de 9am a 9pm"
            row2.similarity = 0.72
            db_result.fetchall.return_value = [row1, row2]
            db.execute.return_value = db_result

            from app.services.rag_service import answer_with_rag
            result = await answer_with_rag(
                str(uuid.uuid4()), "¿Qué venden?", [], db,
            )
            assert result == "Respuesta con contexto."

    @pytest.mark.asyncio
    async def test_answer_with_rag_low_similarity(self):
        with patch("app.services.rag_service.get_embedding", new_callable=AsyncMock) as mock_embed, \
             patch("app.services.rag_service.generate_bot_response", new_callable=AsyncMock) as mock_bot:
            mock_embed.return_value = [0.1] * 1024
            mock_bot.return_value = "No tengo esa información, ¿en qué más puedo ayudarte?"

            db = AsyncMock()
            db_result = MagicMock()

            row = MagicMock()
            row.chunk_text = "algo irrelevante"
            row.similarity = 0.1
            db_result.fetchall.return_value = [row]
            db.execute.return_value = db_result

            from app.services.rag_service import answer_with_rag
            result = await answer_with_rag(
                str(uuid.uuid4()), "pregunta rara", [], db,
            )
            assert "no tengo" in result.lower() or "ayudar" in result.lower()


class TestStorageService:
    """Tests para el servicio de storage."""

    @patch("app.services.storage_service.settings")
    @patch("app.services.storage_service.os")
    @pytest.mark.asyncio
    async def test_upload_bytes_local_only(self, mock_os, mock_settings):
        mock_settings.CF_R2_ACCESS_KEY = ""
        mock_settings.BASE_URL = "http://test:8000"
        mock_os.path.join.return_value = "/tmp/audio/test.mp3"
        mock_os.makedirs = MagicMock()
        mock_os.path.dirname.return_value = "/tmp/audio"

        from app.services.storage_service import upload_bytes

        with patch("builtins.open", unittest.mock.mock_open()) as mock_file:
            result = await upload_bytes(b"audio data", "test.mp3", "audio/mpeg")

        assert result == "http://test:8000/api/v1/radio/audio/test.mp3"
        mock_file.assert_called_once_with("/tmp/audio/test.mp3", "wb")

    @patch("app.services.storage_service.settings")
    @patch("app.services.storage_service.os")
    @pytest.mark.asyncio
    async def test_upload_bytes_with_r2(self, mock_os, mock_settings):
        mock_settings.CF_R2_ACCESS_KEY = "key"
        mock_settings.CF_R2_ENDPOINT = "https://r2.example.com"
        mock_settings.CF_R2_SECRET_KEY = "secret"
        mock_settings.CF_R2_BUCKET = "bucket"
        mock_settings.BASE_URL = "http://test:8000"
        mock_os.path.join.return_value = "/tmp/audio/test.mp3"
        mock_os.makedirs = MagicMock()
        mock_os.path.dirname.return_value = "/tmp/audio"

        from app.services.storage_service import upload_bytes

        with patch("builtins.open", unittest.mock.mock_open()) as mock_file, \
             patch("app.services.storage_service._upload_to_r2", new_callable=AsyncMock) as mock_r2:
            result = await upload_bytes(b"audio data", "test.mp3", "audio/mpeg")

        assert result == "http://test:8000/api/v1/radio/audio/test.mp3"
        mock_r2.assert_awaited_once()

    @patch("app.services.storage_service.settings")
    def test_get_client_creates_s3(self, mock_settings):
        mock_settings.CF_R2_ENDPOINT = "https://r2.example.com"
        mock_settings.CF_R2_ACCESS_KEY = "key"
        mock_settings.CF_R2_SECRET_KEY = "secret"

        with patch("boto3.client") as mock_boto:
            from app.services.storage_service import _get_client

            global _s3_client  # noqa
            import app.services.storage_service as ss
            ss._s3_client = None

            client = _get_client()
            mock_boto.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_to_r2_failure_logged(self):
        with patch("app.services.storage_service.settings") as mock_settings, \
             patch("app.services.storage_service._get_client") as mock_get:
            mock_settings.CF_R2_BUCKET = "bucket"
            mock_client = MagicMock()
            mock_client.put_object.side_effect = Exception("R2 down")
            mock_get.return_value = mock_client

            from app.services.storage_service import _upload_to_r2
            await _upload_to_r2(b"data", "key.mp3", "audio/mpeg")
            mock_client.put_object.assert_called_once()


class TestCalendarService:
    """Tests para el servicio de Google Calendar."""

    def _mock_flow(self, from_client_config_return=None):
        """Helper to mock _get_flow so we don't need google_auth_oauthlib installed."""
        mock_flow = MagicMock()
        if from_client_config_return:
            mock_flow.from_client_config.return_value = from_client_config_return
        return mock_flow

    @patch("app.services.calendar_service.settings")
    def test_get_auth_url(self, mock_settings):
        mock_settings.GOOGLE_CALENDAR_CLIENT_ID = "client-123"
        mock_settings.GOOGLE_CALENDAR_CLIENT_SECRET = "secret-456"

        from app.services.calendar_service import get_auth_url

        with patch("app.services.calendar_service._get_flow") as mock_get_flow:
            mock_flow = MagicMock()
            mock_flow.authorization_url.return_value = ("https://accounts.google.com/o/oauth2/auth?foo=bar", None)
            mock_get_flow.return_value = mock_flow

            url = get_auth_url("https://example.com/callback", "state123")
            assert "https://" in url
            mock_get_flow.assert_called_once()

    @patch("app.services.calendar_service.settings")
    def test_exchange_code_returns_token(self, mock_settings):
        mock_settings.GOOGLE_CALENDAR_CLIENT_ID = "client-123"
        mock_settings.GOOGLE_CALENDAR_CLIENT_SECRET = "secret-456"

        from app.services.calendar_service import exchange_code

        with patch("app.services.calendar_service._get_flow") as mock_get_flow:
            mock_flow = MagicMock()
            mock_creds = MagicMock()
            mock_creds.refresh_token = "rtoken789"
            mock_flow.credentials = mock_creds
            mock_get_flow.return_value = mock_flow

            token = exchange_code("auth-code", "https://example.com/callback")
            assert token == "rtoken789"

    @patch("app.services.calendar_service.settings")
    def test_exchange_code_no_token_raises(self, mock_settings):
        mock_settings.GOOGLE_CALENDAR_CLIENT_ID = "client-123"
        mock_settings.GOOGLE_CALENDAR_CLIENT_SECRET = "secret-456"

        from app.services.calendar_service import exchange_code

        with patch("app.services.calendar_service._get_flow") as mock_get_flow:
            mock_flow = MagicMock()
            mock_flow.credentials = MagicMock()
            mock_flow.credentials.refresh_token = None
            mock_get_flow.return_value = mock_flow

            with pytest.raises(ValueError, match="No refresh token"):
                exchange_code("code", "https://example.com/callback")

    @patch("app.services.calendar_service.settings")
    def test_create_event(self, mock_settings):
        mock_settings.GOOGLE_CALENDAR_CLIENT_ID = "client-123"
        mock_settings.GOOGLE_CALENDAR_CLIENT_SECRET = "secret-456"

        from app.services.calendar_service import create_event

        with patch("app.services.calendar_service._get_calendar_service") as mock_get_svc:
            mock_service = MagicMock()
            mock_events = MagicMock()
            mock_events.insert.return_value.execute.return_value = {"id": "event-1"}
            mock_service.events.return_value = mock_events
            mock_get_svc.return_value = mock_service

            event_id = create_event(
                refresh_token="rtoken",
                summary="Cita",
                description="Desc",
                start_dt=datetime.now(timezone.utc) + timedelta(hours=1),
                duration_min=30,
                customer_phone="+521234567890",
            )
            assert event_id == "event-1"
            mock_events.insert.assert_called_once()

    @patch("app.services.calendar_service.settings")
    def test_update_event(self, mock_settings):
        mock_settings.GOOGLE_CALENDAR_CLIENT_ID = "client-123"
        mock_settings.GOOGLE_CALENDAR_CLIENT_SECRET = "secret-456"

        from app.services.calendar_service import update_event

        with patch("app.services.calendar_service._get_calendar_service") as mock_get_svc:
            mock_service = MagicMock()
            mock_events = MagicMock()
            mock_get = MagicMock()
            mock_get.execute.return_value = {"id": "event-1", "summary": "Old"}
            mock_events.get.return_value = mock_get
            mock_events.update.return_value.execute.return_value = {}
            mock_service.events.return_value = mock_events
            mock_get_svc.return_value = mock_service

            update_event("rtoken", "event-1", summary="New Summary")
            assert mock_events.update.called

    @patch("app.services.calendar_service.settings")
    def test_delete_event(self, mock_settings):
        mock_settings.GOOGLE_CALENDAR_CLIENT_ID = "client-123"
        mock_settings.GOOGLE_CALENDAR_CLIENT_SECRET = "secret-456"

        from app.services.calendar_service import delete_event

        with patch("app.services.calendar_service._get_calendar_service") as mock_get_svc:
            mock_service = MagicMock()
            mock_events = MagicMock()
            mock_events.delete.return_value.execute.return_value = {}
            mock_service.events.return_value = mock_events
            mock_get_svc.return_value = mock_service

            delete_event("rtoken", "event-1")
            mock_events.delete.assert_called_once_with(calendarId="primary", eventId="event-1")


class TestBannerService:
    """Tests para el servicio de banners."""

    def test_banner_copy_namedtuple(self):
        from app.services.banner_service import BannerCopy

        copy = BannerCopy(
            headline="OFERTA",
            subheadline="No te lo pierdas",
            cta="Compra ahora",
            contact_name="María",
            business_name="Tienda",
        )
        assert copy.headline == "OFERTA"
        assert copy.contact_name == "María"

    def test_generate_banner_png_returns_bytes(self):
        from app.services.banner_service import BannerCopy, generate_banner_png

        copy = BannerCopy("GRAN OFERTA", "Válido hasta fin de mes", "Ver más", "Ana", "Mi Tienda")
        result = generate_banner_png(copy, palette_name="promo")
        assert isinstance(result, bytes)
        assert len(result) > 100
        # PNG magic bytes
        assert result[:8] == b"\x89PNG\r\n\x1a\n"

    def test_generate_banner_png_all_palettes(self):
        from app.services.banner_service import BannerCopy, generate_banner_png

        copy = BannerCopy("HOLA", "mundo", "cta", "Juan", "Co")
        for palette in ["promo", "verde", "naranja", "morado", "azul", "oscuro", "rojo", "elegante"]:
            result = generate_banner_png(copy, palette_name=palette)
            assert len(result) > 100
            assert result[:8] == b"\x89PNG\r\n\x1a\n"

    def test_generate_banner_png_invalid_palette_falls_back(self):
        from app.services.banner_service import BannerCopy, generate_banner_png

        copy = BannerCopy("OFERTA", "Descripción", "CTR", "Pedro", "Shop")
        result = generate_banner_png(copy, palette_name="nonexistent")
        assert len(result) > 100

    @patch("app.config.settings")
    @pytest.mark.asyncio
    async def test_generate_banner_copy_with_claude(self, mock_settings):
        mock_settings.ANTHROPIC_API_KEY = "sk-ant-test"

        with patch("anthropic.AsyncAnthropic") as mock_anthropic:
            mock_client = AsyncMock()
            msg = MagicMock()
            msg.content = [MagicMock(text='{"headline": "SUPER OFERTA", "subheadline": "50% descuento", "cta": "Compra ya"}')]
            mock_client.messages.create.return_value = msg
            mock_anthropic.return_value = mock_client

            from app.services.banner_service import generate_banner_copy_with_claude
            copy = await generate_banner_copy_with_claude("Tienda", "Luis", "Descuento del 50%")
            assert copy.headline == "SUPER OFERTA"
            assert copy.cta == "Compra ya"
            assert copy.contact_name == "Luis"
            assert copy.business_name == "Tienda"

    @patch("app.config.settings")
    @pytest.mark.asyncio
    async def test_generate_banner_copy_fallback(self, mock_settings):
        mock_settings.ANTHROPIC_API_KEY = "sk-ant-test"

        with patch("anthropic.AsyncAnthropic") as mock_anthropic:
            mock_client = AsyncMock()
            mock_client.messages.create.side_effect = Exception("API Error")
            mock_anthropic.return_value = mock_client

            from app.services.banner_service import generate_banner_copy_with_claude
            copy = await generate_banner_copy_with_claude("Tienda", "Luis", "Oferta increíble")
            assert "OFERTA INCREÍBLE" in copy.headline
            assert copy.contact_name == "Luis"


class TestNumberPoolService:
    """Tests para el servicio de pool de números."""

    @pytest.mark.asyncio
    async def test_assign_pool_number_empty_pool(self):
        from app.services.number_pool_service import assign_pool_number

        user = MagicMock()
        db = AsyncMock()
        # Mock pool numbers query → empty
        pool_result = MagicMock()
        pool_result.fetchall.return_value = []
        db.execute.return_value = pool_result

        result = await assign_pool_number(user, db)
        assert result is False

    @pytest.mark.asyncio
    async def test_assign_pool_number_success(self):
        from app.services.number_pool_service import assign_pool_number

        user = MagicMock()
        user.whatsapp_number = None
        user.whatsapp_number_source = "shared"
        db = AsyncMock()
        # Mock pool numbers → return 2 numbers
        pool_result = MagicMock()
        pool_result.fetchall.return_value = [("+521111111111",), ("+522222222222",)]
        # Mock assigned numbers → return 1 already assigned
        assigned_result = MagicMock()
        assigned_result.fetchall.return_value = [("+521111111111",)]
        # First call returns pool, second call returns assigned
        db.execute.side_effect = [pool_result, assigned_result]

        result = await assign_pool_number(user, db)
        assert result is True
        assert user.whatsapp_number == "+522222222222"
        assert user.whatsapp_number_source == "pool"
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_assign_pool_number_exhausted(self):
        from app.services.number_pool_service import assign_pool_number

        db = AsyncMock()
        # Mock pool numbers → return 1 number
        pool_result = MagicMock()
        pool_result.fetchall.return_value = [("+521111111111",)]
        # Mock assigned numbers → return same number as taken
        assigned_result = MagicMock()
        assigned_result.fetchall.return_value = [("+521111111111",)]
        db.execute.side_effect = [pool_result, assigned_result]

        user = MagicMock()
        result = await assign_pool_number(user, db)
        assert result is False

    @pytest.mark.asyncio
    async def test_release_pool_number(self):
        from app.services.number_pool_service import release_pool_number

        user = MagicMock()
        user.whatsapp_number = "+521111111111"
        user.whatsapp_number_source = "pool"
        db = AsyncMock()

        await release_pool_number(user, db)
        assert user.whatsapp_number is None
        assert user.whatsapp_number_source == "shared"
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_release_pool_number_shared_ignored(self):
        from app.services.number_pool_service import release_pool_number

        user = MagicMock()
        user.whatsapp_number = "+523333333333"
        user.whatsapp_number_source = "shared"
        db = AsyncMock()

        await release_pool_number(user, db)
        db.flush.assert_not_called()

    @pytest.mark.asyncio
    async def test_pool_status(self):
        from app.services.number_pool_service import pool_status

        db = AsyncMock()
        # Mock pool numbers → return 3 numbers
        pool_result = MagicMock()
        pool_result.fetchall.return_value = [
            ("+521111111111",), ("+522222222222",), ("+523333333333",)
        ]
        # Mock assigned users → return 2 assigned
        assigned_result = MagicMock()
        assigned_result.fetchall.return_value = [
            ("+521111111111", "a@b.com", "Negocio A"),
            ("+522222222222", "c@d.com", "Negocio C"),
        ]
        db.execute.side_effect = [pool_result, assigned_result]

        status = await pool_status(db)
        assert status["total"] == 3
        assert status["assigned"] == 2
        assert status["free"] == 1
        assert len(status["numbers"]) == 3

    @pytest.mark.asyncio
    async def test_pool_status_empty(self):
        from app.services.number_pool_service import pool_status

        db = AsyncMock()
        pool_result = MagicMock()
        pool_result.fetchall.return_value = []
        db.execute.return_value = pool_result

        status = await pool_status(db)
        assert status == {"total": 0, "assigned": 0, "free": 0, "numbers": []}


class TestRadioScripts:
    """Tests para generación de guiones de radio."""

    @patch("app.services.claude_service._get_client")
    @pytest.mark.asyncio
    async def test_generate_radio_script_classic(self, mock_get_client):
        mock_client = AsyncMock()
        msg = MagicMock()
        msg.content = [MagicMock(text="🎵 ¿Cansado del mismo café? Ven a Coffee House...")]
        mock_client.messages.create.return_value = msg
        mock_get_client.return_value = mock_client

        from app.services.radio.scripts import generate_radio_script
        script = await generate_radio_script("Coffee House", "Promo café", mode="classic")
        assert len(script) > 0
        assert "Coffee" in script

    @patch("app.services.claude_service._get_client")
    @pytest.mark.asyncio
    async def test_generate_radio_script_comunitaria(self, mock_get_client):
        mock_client = AsyncMock()
        msg = MagicMock()
        msg.content = [MagicMock(text="🌱 ¿Sabías que...")]
        mock_client.messages.create.return_value = msg
        mock_get_client.return_value = mock_client

        from app.services.radio.scripts import generate_radio_script
        script = await generate_radio_script("Tienda", "consejos", mode="comunitaria")
        assert len(script) > 0

    @patch("app.services.claude_service._get_client")
    @pytest.mark.asyncio
    async def test_generate_radio_script_unknown_mode(self, mock_get_client):
        mock_client = AsyncMock()
        msg = MagicMock()
        msg.content = [MagicMock(text="Texto genérico de locutor...")]
        mock_client.messages.create.return_value = msg
        mock_get_client.return_value = mock_client

        from app.services.radio.scripts import generate_radio_script
        script = await generate_radio_script("Negocio", "msg", mode="unknown")
        assert len(script) > 0

    def test_mode_prompts_defined(self):
        from app.services.radio.scripts import _MODE_PROMPTS
        assert len(_MODE_PROMPTS) == 7
        for mode in ["classic", "comunitaria", "capsula", "trivia", "historia", "alerta", "estacional"]:
            assert mode in _MODE_PROMPTS

    def test_system_prompts_not_empty(self):
        from app.services.radio.scripts import (
            GUION_SYSTEM_PROMPT, GUION_COMUNITARIO_PROMPT, GUION_CAPSULA_PROMPT,
            GUION_TRIVIA_PROMPT, GUION_HISTORIA_PROMPT, GUION_ALERTA_PROMPT, GUION_ESTACIONAL_PROMPT,
        )
        for p in [GUION_SYSTEM_PROMPT, GUION_COMUNITARIO_PROMPT, GUION_CAPSULA_PROMPT,
                  GUION_TRIVIA_PROMPT, GUION_HISTORIA_PROMPT, GUION_ALERTA_PROMPT, GUION_ESTACIONAL_PROMPT]:
            assert len(p) > 50


class AsyncIter:
    """Helper para crear async iterables en tests."""
    def __init__(self, items):
        self.items = items
    def __aiter__(self):
        return self
    async def __anext__(self):
        if not self.items:
            raise StopAsyncIteration
        return self.items.pop(0)


class TestRadioTts:
    """Tests para el servicio de TTS."""

    def test_locutor_voices_defined(self):
        from app.services.radio.tts import LOCUTOR_VOICES
        for country in ["mx", "co", "ar", "es"]:
            assert country in LOCUTOR_VOICES
        assert "default" in LOCUTOR_VOICES

    @patch("app.config.settings")
    @pytest.mark.asyncio
    async def test_text_to_speech_edge(self, mock_settings):
        mock_settings.GOOGLE_TTS_PROVIDER = ""
        mock_settings.FISH_AUDIO_API_KEY = ""

        with patch("edge_tts.Communicate") as mock_comm:
            mock_comm_instance = MagicMock()
            chunks = [
                {"type": "audio", "data": b"fake_audio_chunk1"},
                {"type": "audio", "data": b"fake_audio_chunk2"},
                {"type": "done", "data": None},
            ]
            mock_comm_instance.stream.return_value = AsyncIter(list(chunks))
            mock_comm.return_value = mock_comm_instance

            from app.services.radio.tts import text_to_speech
            result = await text_to_speech("Hola mundo", "es-MX-JorgeNeural")
            assert isinstance(result, bytes)
            assert len(result) > 0
            mock_comm.assert_called_once_with("Hola mundo", voice="es-MX-JorgeNeural", rate="-5%", pitch="-5Hz")

    @pytest.mark.skipif(True, reason="fishaudio no instalado — test opcional")
    @patch("app.config.settings")
    @pytest.mark.asyncio
    async def test_text_to_speech_fish_audio(self, mock_settings):
        mock_settings.GOOGLE_TTS_PROVIDER = ""
        mock_settings.FISH_AUDIO_API_KEY = "fish-key"
        mock_settings.FISH_AUDIO_VOICE_ID = "voice-123"

        with patch("fishaudio.AsyncFishAudio") as mock_fish:
            mock_client = MagicMock()
            chunks = [b"chunk1", b"chunk2"]
            mock_client.tts.stream.return_value = AsyncIter(list(chunks))
            mock_fish.return_value = mock_client

            from app.services.radio.tts import text_to_speech
            result = await text_to_speech("test", "es-MX-JorgeNeural")
            assert isinstance(result, bytes)
            assert result == b"chunk1chunk2"

    @patch("app.config.settings")
    @pytest.mark.asyncio
    async def test_text_to_speech_google(self, mock_settings):
        mock_settings.GOOGLE_TTS_PROVIDER = "google"
        mock_settings.GOOGLE_TTS_VOICE_NAME = "es-ES-Neural2-F"
        mock_settings.GOOGLE_SERVICE_ACCOUNT_JSON = json.dumps({"type": "service_account"})

        with patch("google.cloud.texttospeech_v1.TextToSpeechAsyncClient") as mock_tts:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.audio_content = b"google_tts_audio"
            mock_client.synthesize_speech.return_value = mock_response
            mock_tts.from_service_account_info.return_value = mock_client

            from app.services.radio.tts import text_to_speech
            result = await text_to_speech("test", "es-MX-JorgeNeural")
            assert result == b"google_tts_audio"


class TestRadioAudio:
    """Tests para procesamiento de audio de radio."""

    def test_get_jingle_path_known_category(self):
        from app.services.radio.audio import get_jingle_path, JINGLES_DIR

        with patch("pathlib.Path.exists") as mock_exists:
            mock_exists.return_value = True
            path = get_jingle_path("restaurante")
            assert path is not None
            assert "restaurante.mp3" in path

    def test_get_jingle_path_unknown_category(self):
        from app.services.radio.audio import get_jingle_path, JINGLES_DIR

        with patch("pathlib.Path.exists") as mock_exists:
            mock_exists.return_value = True
            path = get_jingle_path("categoria_inexistente_xyz")
            assert path is not None
            assert "generico.mp3" in path

    def test_get_jingle_path_none_category(self):
        from app.services.radio.audio import get_jingle_path, JINGLES_DIR

        with patch("pathlib.Path.exists") as mock_exists:
            mock_exists.return_value = True
            path = get_jingle_path(None)
            assert path is not None
            assert "generico.mp3" in path

    def test_get_jingle_path_file_not_found(self):
        from app.services.radio.audio import get_jingle_path

        with patch("pathlib.Path.exists") as mock_exists:
            mock_exists.return_value = False
            path = get_jingle_path("restaurante")
            assert path is None

    def test_category_jingle_map_has_default(self):
        from app.services.radio.audio import JINGLE_DEFAULT
        assert JINGLE_DEFAULT == "generico.mp3"

    def test_normalize_unicode(self):
        from app.services.radio.audio import _norm
        assert _norm("Restaurante") == "restaurante"
        assert _norm("Farmacia") == "farmacia"
        assert _norm("Bienes Raíces") == "bienes raices"
        assert _norm("México") == "mexico"

    def test_mix_with_jingle_no_jingle(self):
        from app.services.radio.audio import mix_with_jingle

        with patch("pydub.AudioSegment") as mock_audio:
            mock_segment = MagicMock()
            mock_audio.from_mp3.return_value = mock_segment
            mock_segment.dBFS = -15.0

            import io
            mock_out = MagicMock()
            mock_segment.export.return_value = None

            result = mix_with_jingle(b"fake_mp3_bytes")
            assert isinstance(result, bytes) or result == b"fake_mp3_bytes"

    def test_mix_with_jingle_with_jingle(self):
        from app.services.radio.audio import mix_with_jingle

        with patch("pydub.AudioSegment") as mock_audio, \
             patch("pathlib.Path.exists") as mock_exists:
            mock_exists.return_value = True
            mock_voice = MagicMock()
            mock_jingle = MagicMock()
            mock_audio.from_mp3.return_value = mock_voice
            mock_audio.from_file.return_value = mock_jingle

            mock_voice.dBFS = -15.0
            mock_jingle.dBFS = -12.0
            mock_jingle.__len__.return_value = 10000

            mock_voice.__add__ = lambda a, b: MagicMock()
            mock_voice.__len__ = lambda s: 5000

            result = mix_with_jingle(b"voice_bytes", jingle_path="/fake/jingle.mp3", jingle_intro_ms=2000)
            assert isinstance(result, bytes) or result is not None

    def test_mix_with_jingle_exception_fallback(self):
        from app.services.radio.audio import mix_with_jingle

        with patch("pydub.AudioSegment") as mock_audio:
            mock_audio.from_mp3.side_effect = Exception("pydub error")

            result = mix_with_jingle(b"raw_bytes_fallback")
            # Should return original bytes on error
            assert result == b"raw_bytes_fallback"


class TestRadioAdPipeline:
    """Tests para el pipeline completo de radio."""

    @patch("app.config.settings")
    @patch("app.services.storage_service.settings")
    @pytest.mark.asyncio
    async def test_generate_radio_ad_with_script(self, mock_ssettings, mock_csettings):
        mock_csettings.ANTHROPIC_API_KEY = "sk-ant"
        mock_ssettings.CF_R2_ACCESS_KEY = ""

        with patch("app.services.radio.generate_radio_script", new_callable=AsyncMock) as mock_script, \
             patch("app.services.radio.text_to_speech", new_callable=AsyncMock) as mock_tts, \
             patch("app.services.radio.mix_with_jingle") as mock_mix, \
             patch("app.services.storage_service.upload_bytes", new_callable=AsyncMock) as mock_up:

            mock_script.return_value = "Guión de prueba para la cuña..."
            mock_tts.return_value = b"mp3_bytes"
            mock_mix.return_value = b"ogg_mixed"
            mock_up.return_value = "https://example.com/audio/test.ogg"

            from app.services.radio import generate_radio_ad
            url = await generate_radio_ad(
                business_name="Mi Negocio",
                message_or_intent="Vende más",
                _script="Script predefinido",
            )
            # Should NOT call generate_radio_script when _script is provided
            mock_script.assert_not_called()
            assert url == "https://example.com/audio/test.ogg"

    @patch("app.config.settings")
    @patch("app.services.storage_service.settings")
    @pytest.mark.asyncio
    async def test_generate_radio_ad_no_script(self, mock_ssettings, mock_csettings):
        mock_csettings.ANTHROPIC_API_KEY = "sk-ant"
        mock_ssettings.CF_R2_ACCESS_KEY = ""

        with patch("app.services.radio.generate_radio_script", new_callable=AsyncMock) as mock_script, \
             patch("app.services.radio.text_to_speech", new_callable=AsyncMock) as mock_tts, \
             patch("app.services.radio.mix_with_jingle") as mock_mix, \
             patch("app.services.storage_service.upload_bytes", new_callable=AsyncMock) as mock_up:

            mock_script.return_value = "Guión generado por Claude..."
            mock_tts.return_value = b"mp3_bytes"
            mock_mix.return_value = b"ogg_mixed"
            mock_up.return_value = "https://example.com/audio/gen.ogg"

            from app.services.radio import generate_radio_ad
            url = await generate_radio_ad(
                business_name="Tienda",
                message_or_intent="Oferta especial",
            )
            mock_script.assert_awaited_once()
            assert "https://" in url


class TestImagenService:
    """Tests para el servicio de Google Imagen."""

    @patch("app.services.imagen_service.settings")
    @pytest.mark.asyncio
    async def test_generate_flyer_no_token(self, mock_settings):
        mock_settings.GOOGLE_SERVICE_ACCOUNT_JSON = ""

        from app.services.imagen_service import generate_flyer
        result = await generate_flyer("Campaña", "Mensaje", "Negocio")
        assert result is None

    @patch("app.services.imagen_service.settings")
    @pytest.mark.asyncio
    async def test_generate_flyer_no_project(self, mock_settings):
        mock_settings.GOOGLE_SERVICE_ACCOUNT_JSON = '{"type": "service_account"}'
        mock_settings.GOOGLE_CLOUD_PROJECT = ""

        from app.services.imagen_service import generate_flyer
        result = await generate_flyer("Campaña", "Mensaje", "Negocio")
        assert result is None

    @patch("app.services.imagen_service.settings")
    @pytest.mark.asyncio
    async def test_generate_flyer_success(self, mock_settings):
        mock_settings.GOOGLE_SERVICE_ACCOUNT_JSON = json.dumps({"type": "service_account", "project_id": "test"})
        mock_settings.GOOGLE_CLOUD_PROJECT = "test-project"

        with patch("app.services.imagen_service._get_access_token") as mock_token, \
             patch("app.services.imagen_service.upload_bytes", new_callable=AsyncMock) as mock_up:

            mock_token.return_value = "ya29.test-token"
            mock_up.return_value = "https://cdn.example.com/flyers/campania.png"

            from app.services.imagen_service import generate_flyer

            with patch("httpx.AsyncClient") as mock_httpx:
                mock_client = AsyncMock()
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "predictions": [{"bytesBase64Encoded": base64.b64encode(b"fake_image").decode()}]
                }
                mock_client.post.return_value = mock_response
                mock_httpx.return_value.__aenter__.return_value = mock_client

                url = await generate_flyer("Campaña Test", "Mensaje promocional", "Negocio México")
                assert url == "https://cdn.example.com/flyers/campania.png"

    @patch("app.services.imagen_service.settings")
    @pytest.mark.asyncio
    async def test_generate_flyer_api_error(self, mock_settings):
        mock_settings.GOOGLE_SERVICE_ACCOUNT_JSON = json.dumps({"type": "service_account"})
        mock_settings.GOOGLE_CLOUD_PROJECT = "test-project"

        with patch("app.services.imagen_service._get_access_token") as mock_token:
            mock_token.return_value = "ya29.test-token"

            from app.services.imagen_service import generate_flyer

            with patch("httpx.AsyncClient") as mock_httpx:
                mock_client = AsyncMock()
                mock_response = MagicMock()
                mock_response.status_code = 400
                mock_client.post.return_value = mock_response
                mock_httpx.return_value.__aenter__.return_value = mock_client

                url = await generate_flyer("Campaña", "Mensaje", "Negocio")
                assert url is None

    def test_get_access_token_no_creds(self):
        with patch("app.services.imagen_service.settings") as mock_settings:
            mock_settings.GOOGLE_SERVICE_ACCOUNT_JSON = ""
            from app.services.imagen_service import _get_access_token
            assert _get_access_token() is None

    def test_get_access_token_success(self):
        with patch("app.services.imagen_service.settings") as mock_settings:
            mock_settings.GOOGLE_SERVICE_ACCOUNT_JSON = json.dumps({"type": "service_account"})

            with patch("google.oauth2.service_account.Credentials") as mock_creds, \
                 patch("google.auth.transport.requests.Request"):

                mock_creds_instance = MagicMock()
                mock_creds.from_service_account_info.return_value = mock_creds_instance
                mock_creds_instance.token = "ya29.token123"

                from app.services.imagen_service import _get_access_token
                token = _get_access_token()
                assert token == "ya29.token123"


class TestWhisperService:
    """Tests para el servicio de transcripción Whisper."""

    @patch("app.services.whisper_service.settings")
    @pytest.mark.asyncio
    async def test_transcribe_no_api_key(self, mock_settings):
        mock_settings.OPENAI_API_KEY = ""

        from app.services.whisper_service import transcribe_audio_url
        result = await transcribe_audio_url("https://example.com/audio.ogg")
        assert result is None

    @patch("app.services.whisper_service.settings")
    @pytest.mark.asyncio
    async def test_transcribe_success(self, mock_settings):
        mock_settings.OPENAI_API_KEY = "sk-test"

        from app.services.whisper_service import transcribe_audio_url

        with patch("httpx.AsyncClient") as mock_httpx:
            mock_client = AsyncMock()

            # First call: download audio
            download_resp = MagicMock()
            download_resp.status_code = 200
            download_resp.content = b"fake_audio_data"
            download_resp.headers = {"content-type": "audio/ogg"}

            # Second call: Whisper API
            whisper_resp = MagicMock()
            whisper_resp.status_code = 200
            whisper_resp.text = "Hola, esto es una prueba de transcripción"
            whisper_resp.raise_for_status = MagicMock()

            mock_client.get.return_value = download_resp
            mock_client.post.return_value = whisper_resp
            mock_httpx.return_value.__aenter__.return_value = mock_client

            text = await transcribe_audio_url(
                "https://api.twilio.com/audio.ogg",
                twilio_account_sid="AC123",
                twilio_auth_token="auth_token",
            )
            assert text == "Hola, esto es una prueba de transcripción"
            assert mock_client.get.call_count == 1
            assert mock_client.post.call_count == 1

    @patch("app.services.whisper_service.settings")
    @pytest.mark.asyncio
    async def test_transcribe_download_failure(self, mock_settings):
        mock_settings.OPENAI_API_KEY = "sk-test"

        from app.services.whisper_service import transcribe_audio_url

        with patch("httpx.AsyncClient") as mock_httpx:
            mock_client = AsyncMock()
            mock_client.get.side_effect = Exception("Connection error")
            mock_httpx.return_value.__aenter__.return_value = mock_client

            text = await transcribe_audio_url("https://example.com/audio.ogg")
            assert text is None

    @patch("app.services.whisper_service.settings")
    @pytest.mark.asyncio
    async def test_transcribe_empty_response(self, mock_settings):
        mock_settings.OPENAI_API_KEY = "sk-test"

        from app.services.whisper_service import transcribe_audio_url

        with patch("httpx.AsyncClient") as mock_httpx:
            mock_client = AsyncMock()
            download_resp = MagicMock()
            download_resp.status_code = 200
            download_resp.content = b"audio_data"
            download_resp.headers = {"content-type": "audio/mpeg"}

            whisper_resp = MagicMock()
            whisper_resp.status_code = 200
            whisper_resp.text = ""
            whisper_resp.raise_for_status = MagicMock()

            mock_client.get.return_value = download_resp
            mock_client.post.return_value = whisper_resp
            mock_httpx.return_value.__aenter__.return_value = mock_client

            text = await transcribe_audio_url("https://example.com/audio.mp3")
            assert text is None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-x"])
