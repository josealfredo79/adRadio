"""
RAG service — similarity search over pgvector + Claude response generation.
"""
import logging
import uuid

logger = logging.getLogger(__name__)

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.claude_service import generate_bot_response
from app.services.embedding_service import get_embedding


async def _fetch_user(
    advertiser_id: str, db: AsyncSession
) -> User | None:
    result = await db.execute(
        select(User).where(User.id == uuid.UUID(advertiser_id))
    )
    return result.scalar_one_or_none()


async def search_knowledge(db: AsyncSession, advertiser_id: str, query: str) -> str:
    """Los pedazos de la base de conocimiento del negocio que se parecen a
    *query* (pgvector), unidos en un texto. "" si no hay nada o falla. Lo usa
    el bot de siempre y el agente del cliente (customer_agent.py) como herramienta."""
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
            context_parts = [row.chunk_text for row in rows if row.similarity > 0.35]
            context = "\n\n".join(context_parts) if context_parts else ""
        except Exception as e:
            logger.warning("[RAG] Vector search failed: %s", e)

    return context


async def answer_with_rag(
    advertiser_id: str,
    query: str,
    conversation_history: list[dict],
    db: AsyncSession,
    business_name: str = "el negocio",
    bot_name: str = "Asistente",
    bot_personality: str = "amigable y profesional",
    time_gap_note: str = "",
    ask_owner: bool = False,
    conversation_key: str | None = None,
    redis=None,
    contact_id: uuid.UUID | None = None,
) -> str:
    """
    `conversation_key` (contacto o sesión del chat web) activa la cuota de
    conversaciones del plan (plan_usage.py): se cuenta solo si de verdad se
    llama a la IA, y pasado el límite se contesta con el modelo económico.
    `contact_id` le da al bot los sellos de ese cliente (loyalty_service.py).

    1. Generate embedding for the user query.
    2. Find top-k similar chunks from the advertiser's knowledge base.
    3. Build context string.
    4. Generate response with Claude (temp=0.3, only from context).
    """
    context = await search_knowledge(db, advertiser_id, query)

    user = await _fetch_user(advertiser_id, db)
    bot_instructions = user.bot_instructions if user else None
    customer_note = ""
    if user:
        from app.services.loyalty_service import bot_note

        try:
            customer_note = await bot_note(db, user, contact_id)
        except Exception:
            logger.warning("[RAG] loyalty note failed", exc_info=True)

    # Always call Claude if there are custom instructions or KB context. With
    # ask_owner, also with neither: a brand-new business with nothing loaded
    # yet is exactly when the bot must ask the owner instead of greeting.
    if bot_instructions or context or ask_owner or customer_note:
        economy = False
        if conversation_key:
            from app.services.plan_usage import register_bot_conversation
            usage = await register_bot_conversation(uuid.UUID(str(advertiser_id)), conversation_key, redis)
            economy = usage.economy
        return await generate_bot_response(
            advertiser_context=context,
            conversation_history=conversation_history,
            user_message=query,
            business_name=business_name,
            bot_name=bot_name,
            bot_personality=bot_personality,
            bot_instructions=bot_instructions,
            time_gap_note=time_gap_note,
            ask_owner=ask_owner,
            economy=economy,
            customer_note=customer_note,
        )

    # Pure fallback — no instructions, no context
    if user and user.business_name:
        return f"Hola! Soy {user.bot_name or 'el asistente'} de {user.business_name}. {user.bot_personality or 'Estoy aquí para ayudarte con información sobre nuestros servicios y productos.'} ¿En qué puedo ayudarte hoy?"
    return "Gracias por tu mensaje. En breve un asesor te atenderá. 😊"
