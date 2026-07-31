"""
Runs one persona's simulated conversation against the REAL bot pipeline.

Sandbox guarantee: this module only ever calls `answer_with_rag` (pure
text-in/text-out RAG generation) — it never imports meta_service or
twilio_service, so a Laboratorio run structurally cannot send a real
WhatsApp message.
"""
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.lab.personas import Persona
from app.services.llm_client import chat_completion
from app.services.rag_service import answer_with_rag

logger = logging.getLogger(__name__)

_END_MARKER = "***FIN***"


async def generate_persona_message(
    persona: Persona, business_context: dict, history: list[dict]
) -> str:
    """Ask the persona LLM to write its next customer message, given the
    transcript so far rendered as plain text (avoids message-role-alternation
    edge cases from inverting an existing user/assistant transcript)."""
    if history:
        lines = [
            f"{'Tú (cliente)' if m['role'] == 'user' else 'Negocio'}: {m['content']}"
            for m in history
        ]
        instruction = (
            "Esta es la conversación hasta ahora:\n\n"
            + "\n".join(lines)
            + "\n\nEscribe tu SIGUIENTE mensaje como cliente. Responde solo con el mensaje, nada más."
        )
    else:
        instruction = (
            "Escribe tu primer mensaje de WhatsApp a este negocio para iniciar la conversación. "
            "Responde solo con el mensaje, nada más."
        )

    system = (
        f"{persona.system_prompt}\n\n"
        f"Estás escribiendo por WhatsApp a: {business_context['business_name']} "
        f"({business_context.get('business_category') or 'negocio'}).\n\n"
        f"Si sientes que ya lograste tu objetivo o la conversación llegó a un cierre natural, "
        f"responde exactamente: {_END_MARKER}\n"
        "No agregues explicaciones ni comillas, solo el mensaje de WhatsApp."
    )

    return await chat_completion(
        [{"role": "user", "content": instruction}],
        system=system, max_tokens=200, temperature=0.8,
    )


async def run_persona_conversation(
    persona: Persona, advertiser: User, db: AsyncSession
) -> list[dict]:
    """Simulate up to `persona.max_turns` exchanges. Returns the transcript
    as [{"role": "user"|"assistant", "content": ...}, ...] — "user" is the
    simulated customer, "assistant" is the real bot's reply."""
    business_context = {
        "business_name": advertiser.business_name or "el negocio",
        "business_category": advertiser.business_category,
    }
    history: list[dict] = []

    for _ in range(persona.max_turns):
        try:
            customer_msg = await generate_persona_message(persona, business_context, history)
        except Exception as e:
            logger.warning("[LAB] Persona message generation failed for %s: %s", persona.key, e)
            break

        if not customer_msg or customer_msg.strip() == _END_MARKER:
            break

        history.append({"role": "user", "content": customer_msg})

        try:
            bot_reply = await answer_with_rag(
                advertiser_id=str(advertiser.id),
                query=customer_msg,
                conversation_history=history[:-1],
                db=db,
                business_name=advertiser.business_name or "el negocio",
                bot_name=advertiser.bot_name or "Asistente",
                bot_personality=advertiser.bot_personality or "amigable y profesional",
            )
        except Exception as e:
            logger.warning("[LAB] Bot reply failed for persona=%s: %s", persona.key, e)
            bot_reply = "[ERROR: el bot no pudo responder]"

        history.append({"role": "assistant", "content": bot_reply})

    return history
