"""
Independent LLM judge — scores a Laboratorio persona transcript against the
advertiser's real knowledge base and reports structured findings.
"""
import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_base import KnowledgeBase
from app.models.user import User
from app.services.lab.personas import Persona
from app.services.llm_client import chat_completion

logger = logging.getLogger(__name__)

_KB_CONTEXT_CHAR_LIMIT = 6000

VALID_FINDING_TYPES = {"alucinacion", "hueco_conocimiento", "fallo_escalado", "tono", "otro"}
VALID_SEVERITIES = {"alta", "media", "baja"}

JUDGE_SYSTEM_PROMPT = """Eres un evaluador de calidad independiente y estricto para bots de \
atención al cliente por WhatsApp. Vas a revisar una conversación simulada entre un cliente y un \
bot de un negocio, y tu trabajo es encontrar problemas reales, con evidencia — no ser complaciente.

Evalúa específicamente:
1. ALUCINACIÓN: ¿el bot inventó precios, horarios, productos o políticas que NO están en el \
   contexto del negocio que se te da abajo?
2. HUECO DE CONOCIMIENTO: ¿el bot no supo responder algo razonable y no lo manejó con gracia \
   (en vez de admitir que no sabe)?
3. FALLO DE ESCALADO: si el cliente pidió explícitamente hablar con un humano o mostró frustración \
   fuerte, ¿el bot lo reconoció y ofreció escalar, o lo ignoró y siguió como si nada?
4. TONO: ¿el tono del bot fue apropiado (cálido pero profesional), o sonó robótico, cortante, o \
   inapropiado dado el contexto?

Responde SOLO con JSON válido, sin texto antes ni después, con esta forma exacta:
{
  "score": <entero 0-100, qué tan listo está el bot para hablar con clientes reales>,
  "summary": "<una oración resumiendo el resultado>",
  "findings": [
    {
      "type": "<alucinacion|hueco_conocimiento|fallo_escalado|tono|otro>",
      "severity": "<alta|media|baja>",
      "evidence": "<cita textual o paráfrasis corta del mensaje problemático del bot>",
      "suggestion": "<qué cambiar para arreglarlo, una oración>"
    }
  ]
}
Si no hay problemas, "findings" debe ser una lista vacía y el score debe ser alto (85-100)."""


async def _fetch_kb_context(advertiser_id, db: AsyncSession) -> str:
    result = await db.execute(
        select(KnowledgeBase.chunk_text)
        .where(KnowledgeBase.advertiser_id == advertiser_id, KnowledgeBase.is_active == True)
        .order_by(KnowledgeBase.created_at)
    )
    chunks = [row[0] for row in result.all() if row[0]]
    joined = "\n\n".join(chunks)
    return joined[:_KB_CONTEXT_CHAR_LIMIT]


def _parse_judge_json(raw_text: str) -> dict:
    text = raw_text.strip()
    if text.startswith("```json"):
        text = text.replace("```json", "", 1).rsplit("```", 1)[0].strip()
    elif text.startswith("```"):
        text = text.replace("```", "", 1).rsplit("```", 1)[0].strip()
    data = json.loads(text)

    score = int(data.get("score", 0))
    score = max(0, min(100, score))

    findings = []
    for f in data.get("findings", []):
        ftype = f.get("type") if f.get("type") in VALID_FINDING_TYPES else "otro"
        severity = f.get("severity") if f.get("severity") in VALID_SEVERITIES else "media"
        findings.append({
            "type": ftype,
            "severity": severity,
            "evidence": str(f.get("evidence", ""))[:500],
            "suggestion": str(f.get("suggestion", ""))[:300],
        })

    return {
        "score": score,
        "summary": str(data.get("summary", ""))[:300],
        "findings": findings,
    }


async def evaluate_transcript(
    persona: Persona, transcript: list[dict], advertiser: User, db: AsyncSession
) -> dict:
    """Returns {"score": int, "summary": str, "findings": [...]}. Never raises —
    on any failure (API error, malformed JSON) returns a neutral 0-finding
    result with score=None-equivalent (0) and a diagnostic finding instead."""
    if not transcript:
        return {
            "score": 0,
            "summary": "La persona terminó la conversación sin escribir ningún mensaje.",
            "findings": [],
        }

    kb_context = await _fetch_kb_context(advertiser.id, db)
    transcript_text = "\n".join(
        f"{'Cliente' if m['role'] == 'user' else 'Bot'}: {m['content']}" for m in transcript
    )

    user_prompt = f"""NEGOCIO: {advertiser.business_name or 'el negocio'} \
({advertiser.business_category or 'sin categoría'})

CONTEXTO DEL NEGOCIO (lo único que el bot debería saber — cualquier dato fuera de esto es \
alucinación):
{kb_context or '(sin base de conocimiento configurada)'}

OBJETIVO DE ESTA PERSONA SIMULADA ({persona.label}): {persona.goal}

CONVERSACIÓN A EVALUAR:
{transcript_text}"""

    try:
        raw_text = await chat_completion(
            [{"role": "user", "content": user_prompt}],
            system=JUDGE_SYSTEM_PROMPT, max_tokens=1200, temperature=0.0,
            judge=True,
        )
        return _parse_judge_json(raw_text)
    except Exception as e:
        logger.error("[LAB JUDGE] Evaluation failed for persona=%s: %s", persona.key, e, exc_info=True)
        return {
            "score": 0,
            "summary": "El juez no pudo evaluar esta conversación (error técnico).",
            "findings": [{
                "type": "otro",
                "severity": "media",
                "evidence": f"Error del juez: {str(e)[:200]}",
                "suggestion": "Vuelve a correr el Laboratorio.",
            }],
        }
