"""
"Déjame preguntarle al dueño" — el bot se completa solo con el uso.

1. Un cliente pregunta algo que no está en la base de conocimiento.
2. escalate_to_owner(): se guarda la pregunta, al dueño le llega por el número
   central de IaRadio ("Un cliente pregunta X, ¿qué le digo?") y al cliente
   se le dice que se va a confirmar.
3. El dueño contesta como siempre (texto o nota de voz) → handle_owner_message():
   el bot redacta la respuesta en su tono, se la manda al cliente desde el
   número del negocio y la guarda en la base de conocimiento, así la
   siguiente vez ya no pregunta.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_base import KnowledgeBase
from app.models.message import Message
from app.models.owner_question import OwnerQuestion
from app.models.user import User
from app.services.embedding_service import get_embedding
from app.services.llm_client import chat_completion
from app.services.meta_service import send_whatsapp
from app.services.platform_whatsapp import send_platform_text
from app.services.realtime import publish_conversation_event

logger = logging.getLogger(__name__)

# filename de los chunks que salen de respuestas del dueño — así se ven
# agrupados en la Base de conocimiento y se pueden revisar o borrar.
OWNER_ANSWERS_FILENAME = "respuestas-del-dueño"


def _last10(number: str) -> str:
    return "".join(ch for ch in number if ch.isdigit())[-10:]


def owner_number(advertiser: User) -> str | None:
    """A dónde avisarle al dueño. `phone` (Configuración → Teléfono) es su
    celular; `whatsapp_number` suele ser el número PÚBLICO del negocio (el de
    los links wa.me del sitio). Nunca el número conectado del bot: sería
    mandarle al negocio sus propios avisos — con coexistencia caerían en el
    chat del cliente IaRadio, y sin ella el bot los contestaría."""
    business = _last10(advertiser.meta_display_phone_number or "")
    for candidate in (advertiser.phone, advertiser.whatsapp_number):
        if candidate and (not business or _last10(candidate) != business):
            return candidate
    return None


def _number_variants(number: str) -> list[str]:
    """Todas las formas en que el número del dueño puede estar guardado:
    con/sin '+', y con/sin el '1' móvil de México (521 vs 52)."""
    digits = number.lstrip("+").replace(" ", "")
    bases = {digits}
    if digits.startswith("521"):
        bases.add("52" + digits[3:])
    elif digits.startswith("52"):
        bases.add("521" + digits[2:])
    return sorted({v for b in bases for v in (b, "+" + b)})


def holding_reply(business_name: str) -> str:
    return (
        f"Déjame confirmarlo con el equipo de {business_name} y te respondo "
        "en un momento 🙏"
    )


def no_info_reply(business_name: str) -> str:
    """Lo que el bot decía antes de esta función — se usa si el aviso al dueño
    no se pudo mandar, para no dejar al cliente esperando algo que no llegará."""
    return (
        "No tengo ese dato a la mano, pero puedes consultarlo directamente "
        f"con nosotros 😊 ¿Te ayudo con algo más de {business_name}?"
    )


async def escalate_to_owner(
    db: AsyncSession,
    *,
    advertiser: User,
    contact_id,
    customer_phone: str,
    customer_name: str,
    question: str,
) -> str:
    """Reenvía `question` al dueño y devuelve lo que el bot le contesta al cliente."""
    business_name = advertiser.business_name or "el negocio"
    to = owner_number(advertiser)
    if not to:
        return no_info_reply(business_name)

    oq = OwnerQuestion(
        advertiser_id=advertiser.id,
        contact_id=contact_id,
        customer_phone=customer_phone,
        question=question,
    )
    db.add(oq)
    await db.flush()

    notice = (
        f"❓ Un cliente de *{business_name}* ({customer_name}) pregunta:\n\n"
        f"“{question}”\n\n"
        "Contéstame aquí con la respuesta (texto o nota de voz) y se la paso. "
        "Me la aprendo para la próxima vez 🧠"
    )
    wamid, err = await send_platform_text(to, notice)
    if not wamid:
        logger.warning("[OWNER Q] Could not reach owner of advertiser=%s: %s", advertiser.id, err)
        oq.status = "undeliverable"
        await db.commit()
        return no_info_reply(business_name)

    oq.owner_wamid = wamid
    await db.commit()
    return holding_reply(business_name)


async def _compose_customer_reply(advertiser: User, question: str, owner_answer: str) -> str:
    """El dueño contesta seco ("sí, 50 pesos"); el cliente debe recibirlo en el
    tono del bot. Si el LLM falla, se manda la respuesta del dueño tal cual —
    es información correcta, solo menos pulida."""
    system = (
        f"Eres {advertiser.bot_name or 'el asistente'} de {advertiser.business_name or 'el negocio'}, "
        f"con personalidad {advertiser.bot_personality or 'amigable y profesional'}. "
        "Un cliente hizo una pregunta que confirmaste con el dueño. Escríbele al cliente "
        "la respuesta del dueño como mensaje de WhatsApp: cálido, máximo 3 oraciones, "
        "1 emoji como mucho. Usa SOLO lo que dijo el dueño: no agregues datos, precios "
        "ni promesas. Devuelve solo el mensaje."
    )
    prompt = f"Pregunta del cliente: {question}\nRespuesta del dueño: {owner_answer}"
    try:
        text = await chat_completion(
            [{"role": "user", "content": prompt}], system=system, max_tokens=300, temperature=0.3
        )
        return text.strip() or owner_answer
    except Exception:
        logger.warning("[OWNER Q] compose failed — sending owner's answer verbatim", exc_info=True)
        return owner_answer


async def _learn(db: AsyncSession, advertiser_id, question: str, answer: str) -> None:
    chunk = f"Pregunta: {question}\nRespuesta: {answer}"
    try:
        embedding = await get_embedding(chunk)
    except Exception:
        # Sin embedding el chunk no aparece en la búsqueda, pero guardarlo igual
        # deja el registro visible en la Base de conocimiento.
        logger.warning("[OWNER Q] embedding failed — saving answer without it", exc_info=True)
        embedding = None
    db.add(
        KnowledgeBase(
            advertiser_id=advertiser_id,
            filename=OWNER_ANSWERS_FILENAME,
            file_type="txt",
            raw_text=chunk,
            chunk_text=chunk,
            embedding=embedding,
            processing_status="done",
            is_active=True,
        )
    )


async def _answers_question(question: str, message: str) -> bool:
    """¿El mensaje del dueño responde la pregunta pendiente, o es otra cosa
    ("¿cuántas citas tengo?")? Si el clasificador falla, se asume que sí
    responde: es lo que el aviso le pidió, y equivocarse hacia el Copiloto
    dejaría al cliente sin respuesta."""
    system = (
        "Clasificas mensajes de un dueño de negocio. Tiene pendiente contestar una "
        "pregunta de un cliente. Decide si su mensaje ES la respuesta a esa pregunta "
        "(aunque sea corta: 'sí', '50 pesos', 'no, solo en local') o si es otra cosa "
        "(una instrucción, una consulta sobre su negocio, un saludo). "
        "Responde solo SI o NO."
    )
    prompt = f"Pregunta del cliente: {question}\nMensaje del dueño: {message}"
    try:
        verdict = await chat_completion(
            [{"role": "user", "content": prompt}], system=system, max_tokens=5, temperature=0
        )
    except Exception:
        logger.warning("[OWNER Q] classifier failed — treating as an answer", exc_info=True)
        return True
    return not verdict.strip().upper().startswith("NO")


async def handle_owner_message(
    db: AsyncSession,
    *,
    from_number: str,
    text: str,
    context_wamid: str | None,
) -> None:
    """Mensaje que un dueño le mandó al número central de IaRadio."""
    variants = _number_variants(from_number)
    owners = (
        await db.execute(
            select(User).where(or_(User.whatsapp_number.in_(variants), User.phone.in_(variants)))
        )
    ).scalars().all()
    if not owners:
        await send_platform_text(
            from_number,
            "Hola 👋 Este es el número de avisos de IaRadio para dueños de negocio. "
            "No encontré una cuenta con tu número — revisa que sea el mismo que "
            "registraste en IaRadio.",
        )
        return

    message = text.strip()
    if not message or message.startswith(("[audio", "[media:", "[interactive:")):
        # Nota de voz sin transcripción, sticker, foto… — no hay qué procesar.
        await send_platform_text(
            from_number,
            "No alcancé a entenderte 🙏 ¿Me lo mandas por escrito o en otra nota de voz?",
        )
        return

    # Un dueño con varios negocios con el mismo celular: el Copiloto opera el
    # primero; las preguntas de clientes sí se resuelven en cualquiera.
    primary = owners[0]
    owner_ids = [o.id for o in owners]
    base = select(OwnerQuestion).where(
        OwnerQuestion.advertiser_id.in_(owner_ids), OwnerQuestion.status == "pending"
    )
    oq = None
    if context_wamid:
        # Respondió citando el aviso: sabemos exactamente a qué pregunta contesta.
        oq = (await db.execute(base.where(OwnerQuestion.owner_wamid == context_wamid))).scalar_one_or_none()

    if oq is None:
        from app.services.copilot_whatsapp_service import (
            handle_owner_command,
            has_pending_confirmation,
            parse_decision,
        )

        # "Sí"/"No" a una acción que el Copiloto le pidió confirmar.
        if parse_decision(message) is not None and await has_pending_confirmation(primary):
            await handle_owner_command(db, owner=primary, from_number=from_number, text=message)
            return

        pending = (await db.execute(base.order_by(OwnerQuestion.created_at.desc()))).scalars().all()
        if not pending or not await _answers_question(pending[0].question, message):
            # No contesta a un cliente: es una instrucción para el Copiloto.
            await handle_owner_command(db, owner=primary, from_number=from_number, text=message)
            return
        if len(pending) > 1:
            await send_platform_text(
                from_number,
                f"Tienes {len(pending)} preguntas pendientes 🙌 Para saber cuál contestas, "
                "mantén presionado el aviso de la pregunta, toca *Responder* y escribe ahí.",
            )
            return
        oq = pending[0]

    answer = message
    advertiser = next(o for o in owners if o.id == oq.advertiser_id)
    customer_reply = await _compose_customer_reply(advertiser, oq.question, answer)

    wamid, err = await send_whatsapp(oq.customer_phone, customer_reply, advertiser=advertiser)
    now = datetime.now(timezone.utc)
    oq.answer = answer
    oq.answered_at = now
    oq.status = "answered" if wamid else "undeliverable"
    if oq.contact_id:
        db.add(
            Message(
                advertiser_id=advertiser.id,
                contact_id=oq.contact_id,
                direction="outbound",
                content=customer_reply,
                status="sent" if wamid else "failed",
                wa_message_id=wamid,
                error_code=None if wamid else err,
                sent_at=now if wamid else None,
            )
        )
    await _learn(db, advertiser.id, oq.question, answer)
    await db.commit()
    if oq.contact_id:
        await publish_conversation_event(advertiser.id, {"type": "message", "contact_id": str(oq.contact_id)})

    if wamid:
        confirm = "✅ Listo, ya se lo mandé al cliente y me lo aprendí para la próxima."
    else:
        confirm = (
            "Me lo aprendí para la próxima 🧠, pero no pude mandárselo al cliente — "
            "probablemente ya pasaron más de 24 horas desde su último mensaje. "
            f"Escríbele tú directamente al {oq.customer_phone}."
        )
    await send_platform_text(from_number, confirm)
