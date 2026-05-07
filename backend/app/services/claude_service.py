"""
Claude 3.5 Sonnet service — generación de contenido publicitario.
"""
import re
import anthropic

from app.config import settings

_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


CAMPAIGN_SYSTEM_PROMPT = """Eres un experto en marketing digital y publicidad para WhatsApp.
Tu tarea es crear mensajes publicitarios cortos, naturales y efectivos para pequeños negocios en Latinoamérica.

Reglas:
- Máximo 160 caracteres por mensaje
- Tono cercano y conversacional (no robótico)
- Incluir emoji relevante al inicio
- Llamada a la acción clara al final
- No usar mayúsculas en exceso
- No usar signos de exclamación consecutivos
- Cada variante debe ser única en estructura y palabras clave
"""


async def generate_campaign_variants(
    campaign_type: str,
    business_name: str,
    intent: str,
) -> list[str]:
    """Generate 3 unique WhatsApp ad message variants using Claude."""
    client = _get_client()

    prompt = f"""Genera exactamente 3 variantes de mensaje publicitario para WhatsApp.

Tipo de campaña: {campaign_type}
Negocio: {business_name}
Intención del anunciante: {intent}

Devuelve solo las 3 variantes, separadas por "---", sin numeración ni explicaciones adicionales."""

    message = await client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=600,
        temperature=0.7,
        system=CAMPAIGN_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    variants = [v.strip() for v in raw.split("---") if v.strip()]
    return variants[:3]


async def generate_bot_response(
    advertiser_context: str,
    conversation_history: list[dict],
    user_message: str,
    business_name: str,
    bot_name: str = "Asistente",
    bot_personality: str = "amigable y profesional",
) -> str:
    """Generate a RAG-based bot response using Claude."""
    client = _get_client()

    system = f"""Eres {bot_name}, el asistente virtual de {business_name}.
Tu personalidad es: {bot_personality}.

CONTEXTO DE LA EMPRESA (usa SOLO esta información para responder):
{advertiser_context}

Reglas estrictas:
- Responde ÚNICAMENTE con información del contexto anterior
- Si no sabes algo, di: "Déjame consultar y te respondo en breve"
- Máximo 3 oraciones por respuesta
- Tono conversacional de WhatsApp
- No inventes precios, horarios ni datos
- Temperatura baja — respuestas consistentes y confiables
"""

    messages = conversation_history[-20:] + [
        {"role": "user", "content": user_message}
    ]

    response = await client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=300,
        temperature=0.3,
        system=system,
        messages=messages,
    )

    return response.content[0].text.strip()


# ─── Personalización de mensajes ─────────────────────────────────────────────

def personalize_message(template: str, contact: dict, advertiser: dict) -> str:
    """
    Reemplaza variables en el mensaje con datos reales del contacto.

    Variables soportadas:
        {{nombre}}    → nombre del contacto (o "amigo/a" si no tiene)
        {{ciudad}}    → ciudad del contacto o del negocio
        {{negocio}}   → nombre del negocio
        {{primer_nombre}} → solo el primer nombre
    """
    name = contact.get("name") or "amigo"
    first_name = name.split()[0] if name else "amigo"
    city = contact.get("city") or advertiser.get("city") or "tu ciudad"
    business = advertiser.get("business_name") or "nosotros"

    result = template
    result = result.replace("{{nombre}}", name)
    result = result.replace("{{primer_nombre}}", first_name)
    result = result.replace("{{ciudad}}", city)
    result = result.replace("{{negocio}}", business)
    return result


# ─── Campañas en secuencia ────────────────────────────────────────────────────

SEQUENCE_SYSTEM_PROMPT = """Eres experto en marketing de contenidos para WhatsApp.
Crea una secuencia de 3 mensajes para una campaña publicitaria que se envían en días distintos.

Estructura de la secuencia:
1. Mensaje 1 (Día 1) — DESPERTAR EL INTERÉS: presenta el tema, genera intriga, NO revela todo
2. Mensaje 2 (Día 3) — CONSTRUIR DESEO: profundiza en los beneficios, cuenta historia o testimonio
3. Mensaje 3 (Día 5) — LLAMADA A ACCIÓN: urgencia, oferta específica, cómo aprovecharla

Reglas:
- Máximo 180 caracteres por mensaje
- Cada mensaje referencia sutilmente el anterior ("como te comenté...")
- Tono de locutor de radio: cercano, cálido, latinoamericano
- Emoji al inicio de cada mensaje
- Los 3 separados por "---"
"""

async def generate_sequence_messages(
    business_name: str,
    intent: str,
    campaign_type: str = "promo",
) -> list[str]:
    """Genera una secuencia de 3 mensajes para campaña en días distintos."""
    client = _get_client()

    prompt = f"""Crea una secuencia de 3 mensajes WhatsApp para:

Negocio: {business_name}
Tipo: {campaign_type}
Mensaje a comunicar: {intent}

Usa {{{{nombre}}}} para personalizar con el nombre del cliente cuando sea natural.
Devuelve solo los 3 mensajes separados por "---"."""

    message = await client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=800,
        temperature=0.7,
        system=SEQUENCE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    parts = [v.strip() for v in raw.split("---") if v.strip()]
    return parts[:3]


# ─── Campañas en saga / episodios ────────────────────────────────────────────

SAGA_SYSTEM_PROMPT = """Eres un guionista de radionovelas latinoamericanas experto en marketing.
Crea una historia en 4 episodios semanales protagonizada por un cliente ficticio que usa el producto/servicio del negocio.

Estructura:
- Episodio 1: Presentación del personaje y su PROBLEMA antes de conocer el negocio
- Episodio 2: El personaje DESCUBRE el negocio y lo prueba por primera vez
- Episodio 3: Los RESULTADOS — transformación positiva en su vida
- Episodio 4: El personaje RECOMIENDA el negocio y hay llamada a acción con oferta especial

Reglas:
- Máximo 200 caracteres por episodio
- Siempre empieza con "📻 Episodio X:"
- Historia coherente, mismo personaje en los 4
- Tono radionovela: dramático pero simpático
- El negocio se menciona en episodios 2, 3 y 4
- Separar episodios con "---"
"""

async def generate_saga_episodes(
    business_name: str,
    product_description: str,
    protagonist_name: str = "María",
) -> list[str]:
    """Genera 4 episodios de radionovela de marketing para campaña saga."""
    client = _get_client()

    prompt = f"""Crea una saga de 4 episodios para:

Negocio: {business_name}
Producto/servicio: {product_description}
Nombre del protagonista: {protagonist_name}

Usa {{{{nombre}}}} al final del episodio 4 para personalizar la oferta final.
Devuelve solo los 4 episodios separados por "---"."""

    message = await client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=1200,
        temperature=0.8,
        system=SAGA_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    parts = [v.strip() for v in raw.split("---") if v.strip()]
    return parts[:4]
