"""Detección de intención de escalado a humano — el cliente pide hablar con
una persona real en vez del bot.

Patrón de RESPALDO evaluado sobre el mensaje del cliente ANTES de llamar a
Claude: si matchea, el handoff ocurre aunque el modelo no lo hubiera
detectado por su cuenta (Claude nunca decide activamente escalar en AdRadio
hoy — solo genera texto libre — así que este regex es, de momento, la única
vía de escalado disparada por el cliente). Exige un verbo de contacto cerca
del objeto humano para evitar falsos positivos como "somos 4 personas".

Port del mismo patrón usado en vocero-crm (src/server/ai/handoff.ts).
"""
import re

_HANDOFF_BACKUP_RE = re.compile(
    r"(hablar|comunicar|contactar)[\s\S]{0,40}?(asesor|humano|persona|alguien)"
    r"|un asesor|atenci[oó]n humana",
    re.IGNORECASE,
)


def matches_handoff_intent(text: str | None) -> bool:
    if not text:
        return False
    return bool(_HANDOFF_BACKUP_RE.search(text))
