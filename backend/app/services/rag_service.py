"""
RAG service — similarity search over pgvector + Claude response generation.
"""
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.embedding_service import get_embedding
from app.services.claude_service import generate_bot_response


async def answer_with_rag(
    advertiser_id: str,
    query: str,
    conversation_history: list[dict],
    db: AsyncSession,
    business_name: str = "el negocio",
    bot_name: str = "Asistente",
    bot_personality: str = "amigable y profesional",
) -> str:
    """
    1. Generate embedding for the user query.
    2. Find top-k similar chunks from the advertiser's knowledge base.
    3. Build context string.
    4. Generate response with Claude (temp=0.3, only from context).
    """
    query_embedding = await get_embedding(query)

    # pgvector similarity search — cosine distance
    sql = text("""
        SELECT chunk_text, 1 - (embedding <=> :embedding::vector) AS similarity
        FROM knowledge_base
        WHERE advertiser_id = :advertiser_id
          AND is_active = TRUE
          AND embedding IS NOT NULL
        ORDER BY embedding <=> :embedding::vector
        LIMIT 5
    """)

    result = await db.execute(
        sql,
        {
            "advertiser_id": uuid.UUID(advertiser_id),
            "embedding": str(query_embedding),
        },
    )
    rows = result.fetchall()

    if not rows:
        return "Gracias por tu mensaje. En breve un asesor te atenderá. 😊"

    # Build context from top chunks (filter by similarity threshold)
    context_parts = [row.chunk_text for row in rows if row.similarity > 0.3]
    if not context_parts:
        return "Por el momento no tengo esa información disponible. ¿Te puedo ayudar con algo más?"

    context = "\n\n".join(context_parts)

    return await generate_bot_response(
        advertiser_context=context,
        conversation_history=conversation_history,
        user_message=query,
        business_name=business_name,
        bot_name=bot_name,
        bot_personality=bot_personality,
    )
