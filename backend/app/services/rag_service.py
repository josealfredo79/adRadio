"""
RAG service — similarity search over pgvector + Claude response generation.
"""
import logging
import uuid

logger = logging.getLogger(__name__)

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.embedding_service import get_embedding
from app.services.claude_service import generate_bot_response


async def _fetch_user(
    advertiser_id: str, db: AsyncSession
) -> User | None:
    result = await db.execute(
        select(User).where(User.id == uuid.UUID(advertiser_id))
    )
    return result.scalar_one_or_none()


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
    try:
        query_embedding = await get_embedding(query)
    except Exception as e:
        logger.warning("[RAG] Embedding failed: %s", e)
        query_embedding = None

    context = ""
    if query_embedding:
        sql = text("""
            SELECT chunk_text, 1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
            FROM knowledge_base
            WHERE advertiser_id = :advertiser_id
              AND is_active = TRUE
              AND embedding IS NOT NULL
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT 5
        """)
        try:
            result = await db.execute(
                sql,
                {
                    "advertiser_id": uuid.UUID(advertiser_id),
                    "embedding": str(query_embedding),
                },
            )
            rows = result.fetchall()
            context_parts = [row.chunk_text for row in rows if row.similarity > 0.5]
            context = "\n\n".join(context_parts) if context_parts else ""
        except Exception as e:
            logger.warning("[RAG] Vector search failed: %s", e)

    user = await _fetch_user(advertiser_id, db)
    bot_instructions = user.bot_instructions if user else None

    # Always call Claude if there are custom instructions or KB context
    if bot_instructions or context:
        return await generate_bot_response(
            advertiser_context=context,
            conversation_history=conversation_history,
            user_message=query,
            business_name=business_name,
            bot_name=bot_name,
            bot_personality=bot_personality,
            bot_instructions=bot_instructions,
        )

    # Pure fallback — no instructions, no context
    if user and user.business_name:
        return f"Hola! Soy {user.bot_name or 'el asistente'} de {user.business_name}. {user.bot_personality or 'Estoy aquí para ayudarte con información sobre nuestros servicios y productos.'} ¿En qué puedo ayudarte hoy?"
    return "Gracias por tu mensaje. En breve un asesor te atenderá. 😊"
