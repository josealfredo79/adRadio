"""Validación de campañas — única fuente de verdad, compartida entre REST y
el Copiloto: contenido completo antes de lanzar (resume_campaign /
_execute_launch_campaign) y lo mínimo para crear una (create_campaign /
send_promo).

REST ya validaba esto antes de sacar una campaña "draft" de ese estado; el
Copiloto reimplementaba el resto del flujo de lanzamiento (dueño, estado,
gate anti-baneo, schedule_campaign.delay()) pero le faltaba justo esta
validación — se podía lanzar por chat una campaña sin audio/banner/mensaje
según su modo.
"""
import uuid

from app.models.campaign import Campaign
from app.models.user import User

# Los 7 estilos de cuña: todos se mandan como el audio que el dueño escuchó
# (campaign_ops.send_radio_messages). Antes solo radio/comunitaria; los otros
# 5 caían al envío de texto y no llegaban por web (2026-10-28).
RADIO_MODES = ("radio", "comunitaria", "capsula", "trivia", "historia", "alerta", "estacional")


class CampaignContentIncompleteError(Exception):
    """La campaña no tiene el contenido requerido por su modo para lanzarse."""


def check_content_complete(campaign: Campaign) -> None:
    """Lanza CampaignContentIncompleteError si a *campaign* le falta el
    contenido que su campaign_mode requiere. Solo aplica mientras la campaña
    sigue en "draft" — una vez que salió de ahí ya se validó."""
    if campaign.status != "draft":
        return

    mode = (campaign.ab_test or {}).get("campaign_mode", "regular")

    if mode in RADIO_MODES and not (campaign.ab_test or {}).get("audio_url"):
        raise CampaignContentIncompleteError("Completa la generación de audio antes de enviar la campaña")
    if mode == "banner" and not campaign.image_url:
        raise CampaignContentIncompleteError("Completa la generación del banner antes de enviar la campaña")
    if mode == "regular" and not campaign.message_text:
        raise CampaignContentIncompleteError("Agrega un mensaje a la campaña antes de enviarla")


VALID_TYPES = {"promo", "reminder", "launch", "event", "voces"}


class CampaignValidationError(Exception):
    """La campaña nueva no se puede crear; `status` es el código HTTP que usa REST."""

    def __init__(self, detail: str, status: int = 422):
        super().__init__(detail)
        self.detail = detail
        self.status = status


def check_segment(segment: dict | None) -> None:
    """"Los que compraron en los últimos N días": N entero de 1 a 365; "uno":
    ids válidos. Si no, el envío truena después en recipients_query."""
    segment = segment or {}
    days = segment.get("bought_days")
    if days is not None and (isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 365):
        raise CampaignValidationError("Los días de compra deben ser de 1 a 365")
    try:
        [uuid.UUID(str(c)) for c in segment.get("specific_contacts") or []]
    except ValueError:
        raise CampaignValidationError("Cliente inválido") from None


def validate_new_campaign(
    user: User, *, name: str, message_text: str, type_: str, status: str, segment: dict | None,
) -> None:
    """Lo mínimo para crear una campaña — única fuente de verdad para REST
    (create_campaign) y el Copiloto (send_promo)."""
    from app.services.trial_lifecycle import is_paused

    if user.subscription_status not in ("active", "trial") or is_paused(user):
        raise CampaignValidationError("Necesitas un plan activo para crear campañas", status=402)
    if not name or not name.strip():
        raise CampaignValidationError("El nombre de la campaña es obligatorio")
    if not message_text or not message_text.strip():
        raise CampaignValidationError("El mensaje de la campaña es obligatorio")
    if type_ not in VALID_TYPES:
        raise CampaignValidationError(f"Tipo de campaña inválido. Debe ser uno de: {', '.join(sorted(VALID_TYPES))}")
    if status not in ("draft", "scheduled"):
        raise CampaignValidationError("El estado debe ser 'draft' o 'scheduled'")
    check_segment(segment)
