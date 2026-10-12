"""El bot aprende de lo que el dueño contesta en el Inbox
(docs/specs/2026-10-12-bot-aprende-del-inbox.md).

1. El dueño contesta a un cliente desde el Inbox (la respuesta sale igual).
2. suggest(): una llamada de IA decide si eso sirve como información del
   negocio (precio, horario, envíos) o es algo personal ("ya va tu pedido"),
   y si sirve lo redacta como pregunta y respuesta generales, sin datos del
   cliente. Luego busca lo parecido que el bot ya sabía y una segunda llamada
   marca lo que contradice.
3. El dueño corrige si quiere y toca Guardar → save(): se guarda como
   "respuestas-del-dueño" (igual que "déjame preguntarle al dueño") y las
   respuestas viejas que contradice se desactivan. Los documentos subidos no
   se tocan: un pedazo de documento trae más cosas que se perderían; solo se
   le avisa al dueño para que lo corrija ahí.

Nada se guarda sin que el dueño toque Guardar, y si la IA falla no sale
sugerencia: aprender nunca frena una respuesta al cliente.
"""
import json
import logging
import re
import uuid
from datetime import timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.knowledge_base import KnowledgeBase
from app.models.message import Message
from app.services.embedding_service import get_embedding
from app.services.llm_client import chat_completion
from app.services.owner_question_service import OWNER_ANSWERS_FILENAME, learn_answer

logger = logging.getLogger(__name__)

# Lo que el cliente preguntó justo antes: hasta 3 mensajes, de las últimas horas.
_QUESTION_WINDOW = timedelta(hours=12)
_MAX_CUSTOMER_MESSAGES = 3
# Más estricto que el bot (0.35): aquí solo interesa lo que habla de lo mismo.
_SIMILAR_MIN = 0.5
_MAX_SIMILAR = 4
MAX_FIELD = 600
# Nombres de relleno de contactos sin nombre: no cuentan como dato del cliente.
_GENERIC_NAMES = {"cliente", "sin", "nombre", "usuario", "whatsapp", "contacto"}
_INTERNAL_MESSAGE = re.compile(r"^\[[A-Z_]+(:[a-z_]+)?\]")

_SUGGEST_SYSTEM = (
    "Ayudas a un dueño de negocio a enseñarle a su bot de WhatsApp. Te paso lo que un cliente "
    "preguntó y lo que el dueño le contestó. Decide si la respuesta del dueño es INFORMACIÓN DEL "
    "NEGOCIO que le serviría a cualquier cliente (precios, horarios, envíos, formas de pago, "
    "ubicación, políticas, productos o servicios) o si es algo PERSONAL o de ese momento (el "
    "pedido de ese cliente, una cita suya, un saludo, un 'gracias', 'ya voy', 'te espero').\n"
    "Si es información del negocio, redáctala como una pregunta general y su respuesta, en "
    "español, breve y clara, SIN nombres, teléfonos, direcciones ni datos del cliente, y sin "
    "inventar nada que el dueño no dijo.\n"
    'Responde solo JSON: {"useful": true|false, "question": str, "answer": str}'
)

_CONFLICT_SYSTEM = (
    "Comparas información de un negocio. Te paso una respuesta NUEVA del dueño y textos numerados "
    "que el bot ya sabía. Di cuáles textos CONTRADICEN la respuesta nueva (otro precio, otro "
    "horario, dicen que sí cuando ahora es no, etc.). Hablar de lo mismo sin contradecir NO cuenta.\n"
    'Responde solo JSON: {"contradicts": [números]}'
)


def _parse_json(raw: str) -> dict:
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("La respuesta no trae JSON")
    return json.loads(raw[start:end + 1])


def _clean(v, limit: int = MAX_FIELD) -> str:
    return " ".join(v.split())[:limit] if isinstance(v, str) else ""


def _mentions_customer(text_: str, contact: Contact | None) -> bool:
    if contact is None:
        return False
    digits = "".join(ch for ch in text_ if ch.isdigit())
    phone = "".join(ch for ch in (contact.phone or "") if ch.isdigit())[-10:]
    if len(phone) == 10 and phone in digits:
        return True
    lowered = text_.lower()
    return any(
        re.search(rf"\b{re.escape(part)}\b", lowered)
        for part in (contact.name or "").lower().split() if len(part) >= 3 and part not in _GENERIC_NAMES
    )


async def _customer_question(db: AsyncSession, owner_msg: Message) -> str:
    rows = (await db.execute(
        select(Message.content)
        .where(
            Message.advertiser_id == owner_msg.advertiser_id,
            Message.contact_id == owner_msg.contact_id,
            Message.direction == "inbound",
            Message.created_at < owner_msg.created_at,
            Message.created_at > owner_msg.created_at - _QUESTION_WINDOW,
        )
        .order_by(Message.created_at.desc())
        .limit(_MAX_CUSTOMER_MESSAGES)
    )).scalars().all()
    return "\n".join(c for c in reversed(rows) if c and not _INTERNAL_MESSAGE.match(c))


async def _similar(db: AsyncSession, advertiser_id: uuid.UUID, query: str) -> list[dict]:
    embedding = await get_embedding(query)
    rows = (await db.execute(
        text("""
            SELECT id, filename, chunk_text, 1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
            FROM knowledge_base
            WHERE advertiser_id = :advertiser_id AND is_active = TRUE AND embedding IS NOT NULL
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :limit
        """),
        {"advertiser_id": advertiser_id, "embedding": str(embedding), "limit": _MAX_SIMILAR},
    )).fetchall()
    return [
        {"id": r.id, "filename": r.filename, "text": r.chunk_text or ""}
        for r in rows if r.similarity >= _SIMILAR_MIN
    ]


async def _contradicted(question: str, answer: str, similar: list[dict]) -> list[dict]:
    if not similar:
        return []
    numbered = "\n\n".join(f"[{i}] {s['text'][:800]}" for i, s in enumerate(similar, 1))
    raw = await chat_completion(
        [{"role": "user", "content": f"NUEVA:\nPregunta: {question}\nRespuesta: {answer}\n\nYA SABÍA:\n{numbered}"}],
        system=_CONFLICT_SYSTEM, max_tokens=60, temperature=0,
    )
    picked = _parse_json(raw).get("contradicts") or []
    return [similar[n - 1] for n in picked if isinstance(n, int) and 1 <= n <= len(similar)]


async def suggest(db: AsyncSession, owner_msg: Message) -> dict | None:
    """La sugerencia para la tarjeta del Inbox, o None si no sirve o la IA falló."""
    asked = await _customer_question(db, owner_msg)
    if not asked or not owner_msg.content:
        return None
    try:
        raw = await chat_completion(
            [{"role": "user", "content": f"Cliente: {asked}\nDueño: {owner_msg.content}"}],
            system=_SUGGEST_SYSTEM, max_tokens=300, temperature=0,
        )
        data = _parse_json(raw)
    except Exception:
        logger.warning("[INBOX LEARN] suggestion failed msg=%s", owner_msg.id, exc_info=True)
        return None
    question, answer = _clean(data.get("question")), _clean(data.get("answer"))
    if data.get("useful") is not True or not question or not answer:
        return None
    if _mentions_customer(f"{question} {answer}", await db.get(Contact, owner_msg.contact_id)):
        # La IA dejó el nombre o el teléfono del cliente: no se le ofrece al
        # dueño algo que el bot repetiría a todos.
        return None

    replaces: list[dict] = []
    documents: list[str] = []
    try:
        for s in await _contradicted(question, answer, await _similar(db, owner_msg.advertiser_id, question)):
            if s["filename"] == OWNER_ANSWERS_FILENAME:
                replaces.append({"id": str(s["id"]), "text": s["text"]})
            elif s["filename"] not in documents:
                documents.append(s["filename"])
    except Exception:
        # Sin revisión de contradicciones la sugerencia sigue sirviendo.
        logger.warning("[INBOX LEARN] conflict check failed msg=%s", owner_msg.id, exc_info=True)
    return {"question": question, "answer": answer, "replaces": replaces, "documents": documents}


async def save(db: AsyncSession, advertiser_id: uuid.UUID, question: str, answer: str,
               replace_ids: list[uuid.UUID]) -> int:
    """Guarda la respuesta y desactiva las respuestas viejas que contradice —
    solo "respuestas-del-dueño" de este mismo negocio. Regresa cuántas desactivó."""
    replaced = 0
    if replace_ids:
        old = (await db.execute(
            select(KnowledgeBase).where(
                KnowledgeBase.id.in_(replace_ids),
                KnowledgeBase.advertiser_id == advertiser_id,
                KnowledgeBase.filename == OWNER_ANSWERS_FILENAME,
            )
        )).scalars().all()
        for kb in old:
            kb.is_active = False
        replaced = len(old)
    await learn_answer(db, advertiser_id, question, answer)
    await db.commit()
    return replaced
