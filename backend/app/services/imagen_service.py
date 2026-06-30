"""
Google Imagen 3 — flyer generation service.
Uses a GCP service account (JSON stored in env var) for OAuth2.
"""
import base64
import json
import logging

import httpx

from app.config import settings
from app.services.storage_service import upload_bytes

logger = logging.getLogger(__name__)

# Category-specific visual styles for flyer prompts
_CATEGORY_STYLE: dict[str, str] = {
    "restaurante": "Warm appetizing food photography style, rich textures, soft natural lighting, rustic elegant table setting. ",
    "comida": "Warm appetizing food photography style, rich textures, soft natural lighting, rustic elegant table setting. ",
    "pizzeria": "Warm appetizing food photography style, Italian-inspired, soft candlelight ambiance. ",
    "cafeteria": "Cozy coffee shop aesthetic, warm brown tones, artisanal presentation, soft morning light. ",
    "bar": "Dim sophisticated lounge atmosphere, amber lighting, premium spirits photography, sleek dark tones. ",
    "salud": "Clean clinical aesthetic, fresh and pure, soft white and blue palette, natural daylight, wellness photography. ",
    "farmacia": "Clean clinical aesthetic, trustworthy professional look, soft blue and white tones. ",
    "fitness": "Dynamic athletic photography, energetic composition, bold contrast, motivational lighting. ",
    "gimnasio": "Dynamic athletic photography, energetic composition, bold contrast, motivational lighting. ",
    "belleza": "High-end beauty editorial, glamorous lighting, flawless skin tones, luxury cosmetic aesthetic. ",
    "salon": "High-end beauty editorial, glamorous lighting, luxury salon aesthetic, elegant mirrors and decor. ",
    "spa": "Serene spa retreat atmosphere, soft earthy tones, natural stone and wood textures, peaceful composition. ",
    "tienda": "Retail lifestyle photography, vibrant but sophisticated, product-focused composition, clean commercial look. ",
    "ropa": "Fashion editorial photography, elegant mannequin or fabric styling, boutique aesthetic, premium lighting. ",
    "moda": "High-fashion editorial photography, dramatic lighting, avant-garde composition, luxury brand aesthetic. ",
    "electronica": "Sleek tech product photography, dark sophisticated background, blue and silver accents, modern minimalist. ",
    "tecnologia": "Sleek tech product photography, dark sophisticated background, blue and silver accents, modern minimalist. ",
    "celulares": "Sleek tech product photography, dark sophisticated background, blue and silver accents, modern minimalist. ",
    "inmobiliaria": "Architectural photography, elegant property staging, natural light through windows, premium real estate aesthetic. ",
    "construccion": "Architectural photography, modern building materials, blue sky professional construction aesthetic. ",
    "automotriz": "Automotive photography, sleek vehicle styling, dramatic lighting reflecting off metal surfaces, premium car aesthetic. ",
    "autos": "Automotive photography, sleek vehicle styling, dramatic lighting reflecting off metal surfaces, premium car aesthetic. ",
    "educacion": "Academic and professional setting, warm library light, books and learning materials, inspirational educational aesthetic. ",
    "escuela": "Academic and professional setting, warm library light, books and learning materials, inspirational educational aesthetic. ",
    "colegio": "Academic and professional setting, warm library light, books and learning materials, inspirational educational aesthetic. ",
    "joyeria": "Luxury jewelry photography, macro detail shots, sparkling gemstones, velvet and gold accent styling. ",
    "flores": "Fresh floral photography, soft pastel palette, natural daylight, romantic garden aesthetic. ",
    "mascotas": "Warm pet photography style, playful and loving composition, soft natural light, pet-friendly setting. ",
    "veterinaria": "Warm pet photography style, clean clinical setting with pet comfort, professional care aesthetic. ",
    "juguetes": "Colorful playful composition, child-friendly aesthetic, bright but not harsh lighting, fun product photography. ",
    "deportes": "Dynamic sports photography, action-ready composition, bold team colors, athletic lifestyle aesthetic. ",
    "viajes": "Travel photography, dreamy landscape or cityscape, golden hour lighting, wanderlust aesthetic. ",
    "hotel": "Luxury hospitality photography, elegant room staging, warm ambient lighting, premium travel aesthetic. ",
    "eventos": "Event photography style, elegant party lighting, celebratory atmosphere, sophisticated decoration. ",
    "musica": "Music lifestyle photography, stage lighting aesthetic, artistic composition, creative atmosphere. ",
    "arte": "Art gallery aesthetic, creative composition, dramatic lighting on textures, museum-quality presentation. ",
    "servicios": "Professional corporate photography, clean modern office setting, trustworthy executive aesthetic. ",
    "financiero": "Professional corporate photography, sophisticated boardroom setting, trust and stability aesthetic, navy and gold tones. ",
    "seguros": "Professional corporate photography, trustworthy and caring aesthetic, family protection visual theme. ",
    "corporativo": "Professional corporate photography, modern office architecture, confident business aesthetic. ",
    "abarrotes": "Fresh grocery photography, colorful product arrangement, clean market aesthetic, bright natural lighting. ",
    "supermercado": "Fresh grocery photography, colorful product arrangement, clean market aesthetic, bright natural lighting. ",
    "panaderia": "Warm bakery photography, golden crust textures, rustic wooden surfaces, fresh-from-oven aesthetic. ",
}


def _get_access_token() -> str | None:
    """Get a short-lived OAuth2 access token from the service account JSON."""
    if not settings.GOOGLE_SERVICE_ACCOUNT_JSON:
        return None
    try:
        from google.oauth2 import service_account  # type: ignore
        import google.auth.transport.requests  # type: ignore

        info = json.loads(settings.GOOGLE_SERVICE_ACCOUNT_JSON)
        creds = service_account.Credentials.from_service_account_info(
            info,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        request = google.auth.transport.requests.Request()
        creds.refresh(request)
        return creds.token
    except Exception:
        logger.warning("[IMAGEN] Failed to get access token, returning None", exc_info=True)
        return None


async def generate_flyer(
    campaign_name: str,
    message_text: str,
    business_name: str,
    business_category: str | None = None,
) -> str | None:
    """
    Generate a promotional flyer using Google Imagen 3.
    Returns the public URL of the uploaded image, or None if not configured.
    """
    token = _get_access_token()
    if not token or not settings.GOOGLE_CLOUD_PROJECT:
        return None

    cat = business_category.strip().lower() if business_category else ""
    category_style = _CATEGORY_STYLE.get(cat, "")

    prompt = (
        f"Professional WhatsApp promotional flyer for '{business_name}'. "
        f"Campaign: {campaign_name}. "
        f"Concept: {message_text}. "
        f"{category_style}"
        "High-end brand advertising photography, editorial quality. "
        "Cinematic lighting with soft gradients and subtle depth of field. "
        "Clean composition with generous negative space in the center and upper area reserved for text overlay and headline. "
        "Minimalist aesthetic with elegant visual hierarchy. "
        "Square 1:1 format optimized for mobile viewing. "
        "No text or letters in the image — leave clean space for typography overlay. "
        "Photo-realistic, 8k quality, commercial product photography style."
    )

    endpoint = (
        f"https://us-central1-aiplatform.googleapis.com/v1/projects/"
        f"{settings.GOOGLE_CLOUD_PROJECT}/locations/us-central1/publishers/google/models/"
        f"imagen-3.0-generate-001:predict"
    )

    payload = {
        "instances": [{"prompt": prompt}],
        "parameters": {
            "sampleCount": 1,
            "aspectRatio": "1:1",
        },
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(endpoint, json=payload, headers=headers)
        if response.status_code != 200:
            return None

        data = response.json()
        b64_image = data["predictions"][0]["bytesBase64Encoded"]
        image_bytes = base64.b64decode(b64_image)

        safe_name = "".join(c if c.isalnum() else "_" for c in campaign_name)[:60]
        return await upload_bytes(image_bytes, f"flyers/{safe_name}.png", "image/png")

