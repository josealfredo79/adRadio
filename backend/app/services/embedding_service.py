"""
Embedding service — Voyage AI voyage-3 (1024 dims, gratis 50M tokens/mes).
"""
import voyageai

from app.config import settings

_client: voyageai.AsyncClient | None = None


def _get_client() -> voyageai.AsyncClient:
    global _client
    if _client is None:
        _client = voyageai.AsyncClient(api_key=settings.VOYAGE_API_KEY)
    return _client


async def get_embedding(text: str) -> list[float]:
    """Get 1024-dim embedding vector using voyage-3."""
    client = _get_client()
    text = text.replace("\n", " ").strip()
    result = await client.embed(
        texts=[text],
        model="voyage-3",
        input_type="document",
    )
    return result.embeddings[0]


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Split text into overlapping chunks for embedding."""
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size - overlap):
        chunk = " ".join(words[i : i + chunk_size])
        if chunk.strip():
            chunks.append(chunk)
    return chunks
