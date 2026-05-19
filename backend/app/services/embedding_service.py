"""
Embedding service — OpenAI text-embedding-3-small (1536 dims, sin rate limit).

Fallback a Voyage AI voyage-3 si OPENAI_API_KEY no está configurado.

OpenAI text-embedding-3-small:
  - $0.02 / 1M tokens (vs Voyage free pero con 3 RPM y 22s delay)
  - Sin rate limit en plan de pago
  - Compatible con pgvector (cualquier dimensión)
  - Ya incluido en requirements.txt (openai==1.57.0)
"""
import logging

from app.config import settings

logger = logging.getLogger(__name__)


async def get_embedding(text: str) -> list[float]:
    """
    Genera embedding del texto.
    - Usa OpenAI text-embedding-3-small si OPENAI_API_KEY está configurado (recomendado).
    - Fallback a Voyage AI voyage-3 si no hay clave de OpenAI.
    """
    text = text.replace("\n", " ").strip()

    if settings.OPENAI_API_KEY:
        return await _embed_openai(text)
    return await _embed_voyage(text)


async def _embed_openai(text: str) -> list[float]:
    """OpenAI text-embedding-3-small con 1024 dims — compatible con vector(1024) en pgvector.
    El parámetro dimensions trunca el embedding para coincidir con Voyage AI voyage-3.
    Sin rate limit, $0.02/1M tokens.
    """
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    response = await client.embeddings.create(
        input=text,
        model="text-embedding-3-small",
        dimensions=1024,  # ← misma dim que voyage-3 → compatible con vector(1024) en BD
    )
    return response.data[0].embedding


async def _embed_voyage(text: str, _retries: int = 5) -> list[float]:
    """Voyage AI voyage-3 — fallback gratuito (3 RPM, delay 22s entre llamadas)."""
    import asyncio
    import voyageai

    client = voyageai.AsyncClient(api_key=settings.VOYAGE_API_KEY)
    for attempt in range(_retries):
        try:
            result = await client.embed(
                texts=[text],
                model="voyage-3",
                input_type="document",
            )
            return result.embeddings[0]
        except voyageai.error.RateLimitError:
            if attempt == _retries - 1:
                raise
            wait = 22 * (attempt + 1)
            logger.warning(
                "Voyage AI rate limit, reintentando en %ds (intento %d/%d)",
                wait, attempt + 1, _retries,
            )
            await asyncio.sleep(wait)
    raise RuntimeError("Voyage AI: máximo de reintentos alcanzado")


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Divide el texto en chunks con solapamiento para embeddings."""
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size - overlap):
        chunk = " ".join(words[i : i + chunk_size])
        if chunk.strip():
            chunks.append(chunk)
    return chunks
