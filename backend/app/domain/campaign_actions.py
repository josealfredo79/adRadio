"""Validación de contenido completo antes de lanzar una campaña — única
fuente de verdad, compartida entre REST (resume_campaign) y el Copiloto
(_execute_launch_campaign).

REST ya validaba esto antes de sacar una campaña "draft" de ese estado; el
Copiloto reimplementaba el resto del flujo de lanzamiento (dueño, estado,
gate anti-baneo, schedule_campaign.delay()) pero le faltaba justo esta
validación — se podía lanzar por chat una campaña sin audio/banner/mensaje
según su modo.
"""
from app.models.campaign import Campaign


class CampaignContentIncompleteError(Exception):
    """La campaña no tiene el contenido requerido por su modo para lanzarse."""


def check_content_complete(campaign: Campaign) -> None:
    """Lanza CampaignContentIncompleteError si a *campaign* le falta el
    contenido que su campaign_mode requiere. Solo aplica mientras la campaña
    sigue en "draft" — una vez que salió de ahí ya se validó."""
    if campaign.status != "draft":
        return

    mode = (campaign.ab_test or {}).get("campaign_mode", "regular")

    if mode in ("radio", "comunitaria") and not (campaign.ab_test or {}).get("audio_url"):
        raise CampaignContentIncompleteError("Completa la generación de audio antes de enviar la campaña")
    if mode == "banner" and not campaign.image_url:
        raise CampaignContentIncompleteError("Completa la generación del banner antes de enviar la campaña")
    if mode == "regular" and not campaign.message_text:
        raise CampaignContentIncompleteError("Agrega un mensaje a la campaña antes de enviarla")
