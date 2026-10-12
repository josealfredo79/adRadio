"""Con alguien esperando (el bot buscando en la base de conocimiento), Voyage
saturado no debe colgar el chat: el 12-oct-2026 los reintentos de 22 s+
dejaron el chat web 40 s sin contestar ("Uy, no me llegó tu mensaje")."""
import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest
import voyageai

from app.services import embedding_service
from app.services.rag_service import search_knowledge


class _RateLimitedClient:
    calls = 0

    def __init__(self, *a, **kw):
        pass

    async def embed(self, **kw):
        _RateLimitedClient.calls += 1
        raise voyageai.error.RateLimitError("3 RPM")


class _SlowClient:
    def __init__(self, *a, **kw):
        pass

    async def embed(self, **kw):
        await asyncio.sleep(30)


@pytest.fixture
def voyage_settings():
    with patch.object(embedding_service, "settings", MagicMock(USE_OPENAI_EMBEDDINGS=False, VOYAGE_API_KEY="k")):
        yield


@pytest.mark.asyncio
async def test_live_rate_limit_fails_at_once_without_retrying(voyage_settings):
    _RateLimitedClient.calls = 0
    with patch("voyageai.AsyncClient", _RateLimitedClient), \
            patch("asyncio.sleep", side_effect=AssertionError("no debe esperar")):
        with pytest.raises(voyageai.error.RateLimitError):
            await embedding_service.get_embedding("¿hacen envíos?", live=True)
    assert _RateLimitedClient.calls == 1


@pytest.mark.asyncio
async def test_live_slow_provider_is_cut_off(voyage_settings, monkeypatch):
    monkeypatch.setattr(embedding_service, "LIVE_TIMEOUT_S", 0.2)
    with patch("voyageai.AsyncClient", _SlowClient):
        start = time.monotonic()
        with pytest.raises(asyncio.TimeoutError):
            await embedding_service.get_embedding("hola", live=True)
    assert time.monotonic() - start < 2


@pytest.mark.asyncio
async def test_background_still_retries_on_rate_limit(voyage_settings):
    # Procesar documentos (worker) sí espera: ahí nadie está esperando la respuesta.
    _RateLimitedClient.calls = 0

    async def no_wait(_):
        return None

    with patch("voyageai.AsyncClient", _RateLimitedClient), patch("asyncio.sleep", no_wait):
        with pytest.raises(voyageai.error.RateLimitError):
            await embedding_service.get_embedding("chunk de documento")
    assert _RateLimitedClient.calls == 5


@pytest.mark.asyncio
async def test_bot_search_answers_without_knowledge_when_provider_is_saturated(voyage_settings):
    db = MagicMock()
    with patch("voyageai.AsyncClient", _RateLimitedClient):
        start = time.monotonic()
        assert await search_knowledge(db, "00000000-0000-0000-0000-000000000000", "¿precio?") == ""
    assert time.monotonic() - start < 2
    db.execute.assert_not_called()
