"""
WhatsApp message templates on the business's own WABA: list them (status
straight from Meta, so it's never stale) and submit new ones for approval.

Before this, owners had to create templates in WhatsApp Manager and paste
the name into AdRadio. Meta's App Review for whatsapp_business_management
also asks to see a template being created from the app.
"""
import logging
import re
from dataclasses import dataclass, field
from typing import Literal

from app.services.meta_client import MetaApiError, graph_request

logger = logging.getLogger(__name__)

TemplateCategory = Literal["MARKETING", "UTILITY"]
TemplateLanguage = Literal["es_MX", "es", "en_US"]

NAME_RE = re.compile(r"^[a-z0-9_]{1,512}$")
VARIABLE_RE = re.compile(r"\{\{(\d+)\}\}")
BODY_MAX = 1024
FOOTER_MAX = 60


class TemplateValidationError(ValueError):
    pass


@dataclass
class TemplateSummary:
    id: str
    name: str
    language: str
    category: str
    status: str
    body: str
    rejected_reason: str | None = None


@dataclass
class TemplateResult:
    ok: bool
    code: Literal["meta_unavailable", "meta_error"] | None = None
    message: str | None = None
    data: dict = field(default_factory=dict)


def normalize_name(raw: str) -> str:
    """Meta only accepts lowercase letters, digits and underscores."""
    name = re.sub(r"\s+", "_", raw.strip().lower())
    if not NAME_RE.match(name):
        raise TemplateValidationError("El nombre solo puede tener minúsculas, números y guiones bajos (ej. recordatorio_cita)")
    return name


def body_variables(body: str) -> list[int]:
    """The {{n}} numbers in the body, in order of appearance."""
    return [int(n) for n in VARIABLE_RE.findall(body)]


def build_components(body: str, examples: list[str], footer: str | None) -> list[dict]:
    body = body.strip()
    if not body:
        raise TemplateValidationError("El mensaje no puede ir vacío")
    if len(body) > BODY_MAX:
        raise TemplateValidationError(f"El mensaje no puede pasar de {BODY_MAX} caracteres")

    variables = body_variables(body)
    distinct = sorted(set(variables))
    if distinct != list(range(1, len(distinct) + 1)):
        raise TemplateValidationError("Las variables deben ir numeradas en orden: {{1}}, {{2}}, {{3}}…")
    if body.startswith("{{") or body.endswith("}}"):
        # Meta rejects templates that start or end with a variable.
        raise TemplateValidationError("El mensaje no puede empezar ni terminar con una variable")
    examples = [e.strip() for e in examples]
    if len(examples) != len(distinct) or not all(examples):
        raise TemplateValidationError("Escribe un ejemplo para cada variable (Meta lo pide para revisarla)")

    component: dict = {"type": "BODY", "text": body}
    if examples:
        component["example"] = {"body_text": [examples]}
    components = [component]

    footer = (footer or "").strip()
    if footer:
        if len(footer) > FOOTER_MAX:
            raise TemplateValidationError(f"El pie no puede pasar de {FOOTER_MAX} caracteres")
        components.append({"type": "FOOTER", "text": footer})
    return components


def _error(e: MetaApiError) -> TemplateResult:
    if e.status == 0 or e.status >= 500:
        return TemplateResult(ok=False, code="meta_unavailable", message="Meta no está disponible en este momento; intenta de nuevo")
    details = e.details if isinstance(e.details, dict) else {}
    # error_user_msg is Meta's human-readable reason (e.g. duplicate name).
    return TemplateResult(ok=False, code="meta_error", message=details.get("error_user_msg") or str(e))


def _summary(raw: dict) -> TemplateSummary:
    body = next((c.get("text", "") for c in raw.get("components") or [] if c.get("type") == "BODY"), "")
    reason = raw.get("rejected_reason")
    return TemplateSummary(
        id=str(raw.get("id", "")),
        name=raw.get("name", ""),
        language=raw.get("language", ""),
        category=raw.get("category", ""),
        status=raw.get("status", ""),
        body=body,
        rejected_reason=reason if reason and reason != "NONE" else None,
    )


async def list_templates(waba_id: str, token: str) -> tuple[list[TemplateSummary] | None, TemplateResult | None]:
    """Templates on the WABA, newest first as Meta returns them."""
    try:
        data = await graph_request(
            f"{waba_id}/message_templates",
            token=token,
            params={"fields": "name,language,category,status,rejected_reason,components", "limit": 100},
        )
    except MetaApiError as e:
        logger.warning("[META TEMPLATES] list failed waba=%s: %s", waba_id, e)
        return None, _error(e)
    return [_summary(t) for t in data.get("data") or []], None


async def create_template(
    waba_id: str,
    token: str,
    *,
    name: str,
    category: TemplateCategory,
    language: TemplateLanguage,
    components: list[dict],
) -> TemplateResult:
    """Submit a template for Meta's review. It starts as PENDING."""
    try:
        data = await graph_request(
            f"{waba_id}/message_templates",
            token=token,
            method="POST",
            body={"name": name, "category": category, "language": language, "components": components},
        )
    except MetaApiError as e:
        logger.warning("[META TEMPLATES] create failed waba=%s name=%s: %s", waba_id, name, e)
        return _error(e)
    return TemplateResult(ok=True, data=data)
