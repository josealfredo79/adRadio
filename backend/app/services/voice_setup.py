"""Configurar el bot por voz: "Cuéntame de tu negocio".

El dueño habla 1–3 minutos (o escribe, si no puede usar el micrófono); la IA
ORDENA lo que dijo — nunca inventa precios ni horarios — en un perfil
estructurado que él revisa antes de guardar. Correcciones ("no, el sábado
cerramos a las 6") se dictan igual: se manda el borrador actual y la IA lo
devuelve completo con el cambio aplicado.

Por qué: configurar el bot era escribir mucho, y el dueño de una pyme no lo
hace (el dashboard tiene ~18 opciones). Hablar 2 minutos, sí. Lección de las
pruebas de campo de Raíz (TecNM Tlaxiaco): la voz quita la barrera del teclado.

Todo lo que regresa el modelo se valida aquí (horas HH:MM, precios ≥ 0,
largos máximos) antes de mostrarse o guardarse.
"""
import json
import logging
import re
from decimal import Decimal, InvalidOperation

from app.services.llm_client import chat_completion

logger = logging.getLogger(__name__)

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DAY_LABELS = {"mon": "Lunes", "tue": "Martes", "wed": "Miércoles", "thu": "Jueves",
              "fri": "Viernes", "sat": "Sábado", "sun": "Domingo"}
_HOUR_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
MAX_SERVICES = 40
MAX_ITEMS = 12
MAX_INSTRUCTIONS = 2000  # mismo límite que el campo en Configuración

EMPTY_PROFILE: dict = {
    "business_category": None,
    "city": None,
    "address": None,
    "business_hours": None,
    "services": [],
    "payment_methods": [],
    "policies": [],
    "faqs": [],
    "notes": [],
}

_SYSTEM = """Eres el asistente de configuración de IaRadio. Un dueño de negocio en México te cuenta de su negocio
(transcripción de una nota de voz, puede tener muletillas o errores de transcripción). Tu trabajo es ORDENAR lo que dijo
en un JSON. Reglas estrictas:
- NUNCA inventes datos. Si no dijo algo, déjalo en null o lista vacía. No completes precios ni horarios "típicos".
- Precios en pesos como número (150, no "$150"). Si dijo "desde 150", usa 150 y pon "desde" en la descripción.
- Horario por día con claves mon,tue,wed,thu,fri,sat,sun: ["HH:MM","HH:MM"] en 24 h, o null si cierra ese día.
  Si no mencionó horario, business_hours es null. Si dijo "de lunes a viernes de 9 a 6", sábado y domingo quedan null.
- Si te dan un BORRADOR ACTUAL, devuelve el perfil COMPLETO con lo nuevo aplicado: corrige lo que el dueño corrige,
  agrega lo nuevo, y conserva todo lo demás tal cual.
- Escribe en español claro y breve, como lo diría el dueño. Nada de texto fuera del JSON.

Formato exacto:
{"business_category": str|null, "city": str|null, "address": str|null,
 "business_hours": {"mon": ["09:00","18:00"]|null, ...}|null,
 "services": [{"name": str, "price": number|null, "description": str|null}],
 "payment_methods": [str], "policies": [str], "faqs": [{"q": str, "a": str}], "notes": [str]}"""


def _parse_json(raw: str) -> dict:
    """El modelo a veces envuelve el JSON en ```json ... ``` o agrega una frase:
    tomar del primer { al último }."""
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("La respuesta no trae JSON")
    return json.loads(raw[start:end + 1])


def _clean_str(v, limit: int) -> str | None:
    if not isinstance(v, str):
        return None
    v = " ".join(v.split()).strip()
    return v[:limit] if v else None


def _clean_price(v) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        d = Decimal(str(v).replace("$", "").replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None
    if d < 0 or d > Decimal(10000000):
        return None
    return float(d.quantize(Decimal("0.01")))


def _clean_hours(v) -> dict | None:
    if not isinstance(v, dict):
        return None
    out: dict = {}
    for day in DAYS:
        rng = v.get(day)
        if (
            isinstance(rng, list) and len(rng) == 2
            and all(isinstance(h, str) and _HOUR_RE.match(h) for h in rng)
            and rng[0] < rng[1]
        ):
            out[day] = [rng[0], rng[1]]
        else:
            out[day] = None
    # Todo cerrado = el modelo no entendió un horario; mejor no tocar el actual.
    return out if any(out.values()) else None


def sanitize_profile(data) -> dict:
    """Perfil seguro para mostrar y guardar, venga del modelo o del navegador."""
    data = data if isinstance(data, dict) else {}
    services = []
    for s in (data.get("services") or [])[:MAX_SERVICES]:
        if not isinstance(s, dict):
            continue
        name = _clean_str(s.get("name"), 200)
        if name:
            services.append({
                "name": name,
                "price": _clean_price(s.get("price")),
                "description": _clean_str(s.get("description"), 300),
            })
    faqs = []
    for f in (data.get("faqs") or [])[:MAX_ITEMS]:
        if isinstance(f, dict):
            q, a = _clean_str(f.get("q"), 200), _clean_str(f.get("a"), 400)
            if q and a:
                faqs.append({"q": q, "a": a})

    def str_list(key: str, limit: int = 200) -> list[str]:
        items = [_clean_str(x, limit) for x in (data.get(key) or [])[:MAX_ITEMS]]
        return [x for x in items if x]

    return {
        "business_category": _clean_str(data.get("business_category"), 100),
        "city": _clean_str(data.get("city"), 100),
        "address": _clean_str(data.get("address"), 300),
        "business_hours": _clean_hours(data.get("business_hours")),
        "services": services,
        "payment_methods": str_list("payment_methods", 100),
        "policies": str_list("policies"),
        "faqs": faqs,
        "notes": str_list("notes"),
    }


async def extract_profile(transcript: str, current: dict | None = None, business_name: str = "") -> dict:
    """Transcripción (+ borrador actual, si es una corrección) → perfil validado."""
    parts = []
    if business_name:
        parts.append(f"Negocio: {business_name}")
    if current:
        parts.append("BORRADOR ACTUAL:\n" + json.dumps(sanitize_profile(current), ensure_ascii=False))
    parts.append("LO QUE DIJO EL DUEÑO:\n" + transcript.strip()[:6000])
    raw = await chat_completion(
        [{"role": "user", "content": "\n\n".join(parts)}],
        system=_SYSTEM, max_tokens=1800, temperature=0.1,
    )
    return sanitize_profile(_parse_json(raw))


def _money(p: float | None) -> str:
    if p is None:
        return ""
    return f" — ${p:,.0f}" if float(p).is_integer() else f" — ${p:,.2f}"


def render_hours(hours: dict | None) -> str | None:
    if not hours:
        return None
    return "; ".join(
        f"{DAY_LABELS[d]} {r[0]}–{r[1]}" if r else f"{DAY_LABELS[d]} cerrado" for d, r in hours.items()
    )


def render_instructions(profile: dict) -> str:
    """Texto para bot_instructions, determinista (sin IA) y dentro del límite
    del campo. Es lo que el bot usa como contexto en cada respuesta."""
    p = sanitize_profile(profile)
    blocks: list[str] = []
    if p["address"] or p["city"]:
        blocks.append("Ubicación: " + ", ".join(x for x in (p["address"], p["city"]) if x))
    if hours := render_hours(p["business_hours"]):
        blocks.append(f"Horario: {hours}")
    if p["services"]:
        lines = [f"- {s['name']}{_money(s['price'])}" + (f" ({s['description']})" if s["description"] else "")
                 for s in p["services"]]
        blocks.append("Servicios y precios:\n" + "\n".join(lines))
    if p["payment_methods"]:
        blocks.append("Formas de pago: " + ", ".join(p["payment_methods"]))
    if p["policies"]:
        blocks.append("Políticas:\n" + "\n".join(f"- {x}" for x in p["policies"]))
    if p["faqs"]:
        blocks.append("Preguntas frecuentes:\n" + "\n".join(f"P: {f['q']}\nR: {f['a']}" for f in p["faqs"]))
    if p["notes"]:
        blocks.append("Otros datos:\n" + "\n".join(f"- {x}" for x in p["notes"]))
    text = "\n\n".join(blocks)
    if len(text) > MAX_INSTRUCTIONS:
        text = text[:MAX_INSTRUCTIONS - 1].rsplit("\n", 1)[0] + "…"
    return text
