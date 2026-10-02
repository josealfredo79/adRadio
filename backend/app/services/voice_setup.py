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


async def extract_profile(
    transcript: str, current: dict | None = None, business_name: str = "", question_text: str | None = None,
) -> dict:
    """Transcripción (+ borrador actual, si es una corrección o la respuesta a
    una pregunta de la carita) → perfil validado. Con `question_text` el
    modelo sabe a qué responde un "de 9 a 7" suelto."""
    parts = []
    if business_name:
        parts.append(f"Negocio: {business_name}")
    if current:
        parts.append("BORRADOR ACTUAL:\n" + json.dumps(sanitize_profile(current), ensure_ascii=False))
    if question_text:
        parts.append(f"LE PREGUNTASTE: {question_text}")
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


# ─── La carita que platica (paso 2 del rediseño de voz) ─────────────────────
# Para que configurar se sienta como platicar con alguien: después de cada
# nota de voz la carita dice qué anotó y pregunta lo que falta, de a una
# cosa. Todo esto es determinista (sin IA): instantáneo, gratis y nunca dice
# algo inesperado.

# Prioridad: sin servicios y horario el bot no sirve; ubicación y pagos ayudan.
FOLLOW_UPS: tuple[tuple[str, str], ...] = (
    ("services", "¿Qué vendes o qué servicios das, y cuánto cuestan?"),
    ("hours", "¿En qué horario atiendes? Por ejemplo: de lunes a sábado de 9 a 7."),
    ("location", "¿Dónde está tu negocio? Dime la calle o una referencia."),
    ("payments", "¿Cómo te pueden pagar tus clientes? ¿Efectivo, tarjeta, transferencia?"),
)
QUESTION_TEXT = dict(FOLLOW_UPS)


def _has(profile: dict, field: str) -> bool:
    return {
        "services": bool(profile["services"]),
        "hours": bool(profile["business_hours"]),
        "location": bool(profile["address"] or profile["city"]),
        "payments": bool(profile["payment_methods"]),
    }[field]


def pending_questions(profile: dict, asked: list[str]) -> list[dict]:
    """Lo importante que falta y no se ha preguntado (ni saltado), en orden."""
    p = sanitize_profile(profile)
    return [{"field": f, "text": t} for f, t in FOLLOW_UPS if f not in asked and not _has(p, f)]


def next_question(profile: dict, asked: list[str]) -> dict | None:
    """La siguiente pregunta, o None si ya está todo lo esencial."""
    pending = pending_questions(profile, asked)
    return pending[0] if pending else None


def speak_time(hhmm: str) -> str:
    """'19:00' → '7', '09:30' → '9 y media': como lo dice la gente, no como
    lo leería una voz sintética ("diecinueve horas")."""
    h, m = (int(x) for x in hhmm.split(":"))
    h12 = h % 12 or 12
    if m == 0:
        return str(h12)
    if m == 30:
        return f"{h12} y media"
    return f"{h12}:{m:02d}"


def _speak_hours(hours: dict | None, we: bool = False) -> str | None:
    """Agrupa días seguidos con el mismo horario: 'de martes a sábado de 9 a
    7, y el domingo de 10 a 2; los lunes cierras'. `we=True` lo dice como el
    negocio a su cliente ("Abrimos… cerramos")."""
    if not hours:
        return None
    groups: list[tuple[list[str], list | None]] = []
    for day in DAYS:
        rng = hours.get(day)
        if groups and groups[-1][1] == rng:
            groups[-1][0].append(day)
        else:
            groups.append(([day], rng))
    open_parts, closed = [], []
    for days, rng in groups:
        names = [DAY_LABELS[d].lower() for d in days]
        if rng is None:
            # "los domingos", "los sábados" (lunes a viernes no cambian en plural)
            closed.extend(n if n.endswith("s") else n + "s" for n in names)
            continue
        when = f"el {names[0]}" if len(names) == 1 else f"de {names[0]} a {names[-1]}"
        open_parts.append(f"{when} de {speak_time(rng[0])} a {speak_time(rng[1])}")
    opens, closes = ("Abrimos", "cerramos") if we else ("Abres", "cierras")
    text = f"{opens} " + ", y ".join(open_parts) if open_parts else ""
    if closed:
        text += ("; " if text else "") + "los " + " y ".join(closed) + f" {closes}"
    return text or None


def _speak_money(p: float | None) -> str:
    if p is None:
        return ""
    return f" en {int(p)} pesos" if float(p).is_integer() else f" en {p:.2f} pesos"


def spoken_summary(profile: dict) -> str:
    """Lo que la carita lee en voz alta para que el dueño revise escuchando."""
    p = sanitize_profile(profile)
    parts: list[str] = []
    if p["services"]:
        items = [f"{s['name'].lower()}{_speak_money(s['price'])}" for s in p["services"][:8]]
        more = f", y {len(p['services']) - 8} cosas más" if len(p["services"]) > 8 else ""
        parts.append("Vendes " + ", ".join(items) + more + ".")
    if hours := _speak_hours(p["business_hours"]):
        parts.append(hours + ".")
    if p["address"] or p["city"]:
        parts.append("Estás en " + ", ".join(x for x in (p["address"], p["city"]) if x) + ".")
    if p["payment_methods"]:
        parts.append("Te pagan con " + " y ".join(m.lower() for m in p["payment_methods"]) + ".")
    return " ".join(parts) or "Todavía no anoté nada de tu negocio."


def spoken_reply(profile: dict, previous: dict | None, question: dict | None) -> str:
    """Lo que dice la carita justo después de escuchar: qué anotó (en corto)
    y, si falta algo, la siguiente pregunta."""
    p = sanitize_profile(profile)
    before = sanitize_profile(previous) if previous else None
    got = []
    if p["services"] and (not before or len(p["services"]) != len(before["services"])):
        n = len(p["services"])
        got.append(f"{n} {'servicio' if n == 1 else 'servicios'}")
    if p["business_hours"] and (not before or p["business_hours"] != before["business_hours"]):
        got.append("tu horario")
    if (p["address"] or p["city"]) and (not before or (p["address"], p["city"]) != (before["address"], before["city"])):
        got.append("dónde estás")
    if p["payment_methods"] and (not before or p["payment_methods"] != before["payment_methods"]):
        got.append("cómo te pagan")
    if got:
        listed = got[0] if len(got) == 1 else ", ".join(got[:-1]) + " y " + got[-1]
        opener = f"¡Muy bien! Ya anoté {listed}."
    elif before:
        opener = "¡Anotado!"
    else:
        opener = "Te escuché, pero no alcancé a sacar datos de tu negocio."
    if question:
        return f"{opener} {question['text']}"
    return f"{opener} Ya tengo lo principal. Revisa que esté bien."



# ─── Demo pública en la landing ("Pruébalo en 30 segundos") ─────────────────
# Un visitante sin cuenta dicta su negocio y ve cómo contestaría SU bot.

DEMO_GREETING = (
    "¡Hola! ¿Tienes un negocio? Cuéntame de él: qué vendes, tus precios y tu horario, "
    "y te enseño cómo contestaría tu bot."
)
DEMO_CLOSING = "Así contestaría tu bot a tus clientes, día y noche. Crea tu cuenta y quédatelo: ya guardé lo que me contaste."
_SIGN_DOMAIN = b"voice-demo-line:v1:"


def sign_line(text: str) -> str:
    """Firma una frase que generó el servidor. /public/voice-demo/speak solo
    pronuncia frases firmadas: sin esto sería un servicio de voz gratis y
    abierto para cualquier texto."""
    import hashlib
    import hmac

    from app.config import settings

    return hmac.new(settings.SECRET_KEY.encode(), _SIGN_DOMAIN + text.encode(), hashlib.sha256).hexdigest()[:24]


def verify_line(text: str, sig: str) -> bool:
    import hmac

    from app.config import settings

    return bool(settings.SECRET_KEY) and hmac.compare_digest(sign_line(text), sig or "")


def demo_chat(profile: dict) -> list[dict]:
    """Una plática de ejemplo cliente ↔ bot con los datos que dictó el
    visitante. Determinista (sin IA): instantánea, gratis y fiel a lo que dijo."""
    p = sanitize_profile(profile)
    turns: list[dict] = []
    if p["services"]:
        s = p["services"][0]
        turns.append({"from": "cliente", "text": f"Hola, ¿cuánto cuesta {s['name'].lower()}?"})
        if s["price"] is not None:
            price = f"${s['price']:,.0f}" if float(s["price"]).is_integer() else f"${s['price']:,.2f}"
            turns.append({"from": "bot", "text": f"¡Hola! {s['name']} cuesta {price}. ¿Te gustaría apartar? 😊"})
        else:
            turns.append({"from": "bot", "text": f"¡Hola! Sí tenemos {s['name'].lower()}. Te confirmo el precio enseguida. 😊"})
    if hours := _speak_hours(p["business_hours"], we=True):
        turns.append({"from": "cliente", "text": "¿A qué hora abren?"})
        turns.append({"from": "bot", "text": hours + "."})
    if p["payment_methods"]:
        methods = [m.lower() for m in p["payment_methods"]]
        turns.append({"from": "cliente", "text": "¿Aceptan tarjeta?"})
        if any("tarjeta" in m for m in methods):
            turns.append({"from": "bot", "text": "¡Sí! Aceptamos " + " y ".join(methods) + "."})
        else:
            turns.append({"from": "bot", "text": "Por ahora aceptamos " + " y ".join(methods) + "."})
    elif p["address"] or p["city"]:
        turns.append({"from": "cliente", "text": "¿Dónde están?"})
        turns.append({"from": "bot", "text": "Estamos en " + ", ".join(x for x in (p["address"], p["city"]) if x) + "."})
    return turns
