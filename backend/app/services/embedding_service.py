"""
Embedding service — Voyage AI voyage-3 (1024 dims, gratis 50M tokens/mes).
"""
import asyncio
import logging

import voyageai

from app.config import settings

logger = logging.getLogger(__name__)

_client: voyageai.AsyncClient | None = None


def _get_client() -> voyageai.AsyncClient:
    global _client
    if _client is None:
        _client = voyageai.AsyncClient(api_key=settings.VOYAGE_API_KEY)
    return _client


async def get_embedding(text: str, _retries: int = 5) -> list[float]:
    """Get 1024-dim embedding vector using voyage-3.

    Retries with exponential backoff on rate limit errors (free tier: 3 RPM).
    """
    client = _get_client()
    text = text.replace("\n", " ").strip()
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
            wait = 22 * (attempt + 1)  # 22s, 44s, 66s... (3 RPM = 1 req/20s)
            logger.warning("Voyage AI rate limit hit, retrying in %ds (attempt %d/%d)", wait, attempt + 1, _retries)
            await asyncio.sleep(wait)


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Split text into overlapping chunks for embedding."""
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size - overlap):
        chunk = " ".join(words[i : i + chunk_size])
        if chunk.strip():
            chunks.append(chunk)
    return chunks
