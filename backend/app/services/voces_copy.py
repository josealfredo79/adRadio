"""Textos de "Voces del Barrio" — español, tono de barrio. Centralizados aquí
porque el pipeline (acuse al cliente) y el endpoint de aprobación ("ya estás
al aire") los comparten."""

DEFAULT_CONSENT = (
    "Al enviar tu nota de voz autorizas que la publiquemos con tu nombre de "
    "pila en la página de {business}."
)


def consent_line(raw: str | None, business_name: str) -> str:
    template = (raw or DEFAULT_CONSENT).strip() or DEFAULT_CONSENT
    return template.replace("{business}", business_name).replace("{negocio}", business_name)


def story_ack(first_name: str, business_name: str) -> str:
    hi = f"¡Gracias {first_name}!" if first_name else "¡Gracias!"
    return (
        f"{hi} 🎙️ Tu historia para *{business_name}* ya quedó registrada. "
        "En cuanto la revisemos te avisamos y vas a aparecer en la página del negocio."
    )


def story_published(first_name: str, business_name: str, site_url: str) -> str:
    hi = f"{first_name}, ¡" if first_name else "¡"
    return (
        f"{hi}ya estás al aire en *{business_name}*! 🔊\n"
        f"Escúchate y compártelo con tu gente:\n{site_url}"
    )


def owner_new_story(first_name: str, business_name: str) -> str:
    who = first_name or "un cliente"
    return (
        f"🎙️ *Nueva historia para revisar*\n"
        f"{who} mandó una nota de voz para {business_name}. "
        "Ábrela en tu campaña de Voces del Barrio para aprobarla o descartarla."
    )
