"""
Banner visual service — genera imágenes PNG personalizadas por contacto.

Pipeline:
  1. Claude genera el copy del anuncio (headline + subheadline + CTA)
  2. Pillow renderiza el banner con gradiente + nombre del contacto incrustado
  3. Se retorna bytes PNG listo para subir a R2
"""
import io
import logging
import random
from typing import NamedTuple

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# ── Fuentes del sistema ───────────────────────────────────────────────────────
_FONT_BOLD = "/usr/share/fonts/truetype/ubuntu/UbuntuSans[wdth,wght].ttf"
_FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

# Dimensiones WhatsApp-friendly (ratio ~1:1 o 4:5)
BANNER_W = 800
BANNER_H = 800

# ── Paletas de color (tema → (color1, color2, accent)) ───────────────────────
PALETTES = {
    "promo":    [(29, 53, 87),   (69, 123, 157),  (230, 57, 70)],
    "verde":    [(27, 94, 32),   (56, 142, 60),   (255, 238, 88)],
    "naranja":  [(230, 81, 0),   (255, 143, 0),   (255, 255, 255)],
    "morado":   [(74, 20, 140),  (123, 31, 162),  (240, 98, 146)],
    "azul":     [(13, 71, 161),  (21, 101, 192),  (100, 221, 255)],
    "oscuro":   [(18, 18, 18),   (33, 33, 33),    (0, 230, 118)],
    "rojo":     [(183, 28, 28),  (229, 57, 53),   (255, 235, 59)],
    "elegante": [(26, 26, 46),   (22, 33, 62),    (232, 197, 71)],
}


class BannerCopy(NamedTuple):
    headline: str       # Línea principal grande
    subheadline: str    # Línea secundaria
    cta: str            # Botón/llamada a la acción
    contact_name: str   # Nombre del contacto (incrustado en imagen)
    business_name: str  # Nombre del negocio


def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        logger.warning("[BANNER] Failed to load font, using default", exc_info=True)
        return ImageFont.load_default()


def _gradient_background(draw: ImageDraw.ImageDraw, w: int, h: int, c1: tuple, c2: tuple):
    """Rellena el fondo con un gradiente diagonal suave."""
    for y in range(h):
        t = y / h
        r = int(c1[0] + (c2[0] - c1[0]) * t)
        g = int(c1[1] + (c2[1] - c1[1]) * t)
        b = int(c1[2] + (c2[2] - c1[2]) * t)
        draw.line([(0, y), (w, y)], fill=(r, g, b))


def _draw_noise_circles(draw: ImageDraw.ImageDraw, w: int, h: int, accent: tuple):
    """Agrega círculos decorativos semi-transparentes de fondo."""
    rng = random.Random(42)
    for _ in range(6):
        r = rng.randint(80, 200)
        x = rng.randint(-r, w + r)
        y = rng.randint(-r, h + r)
        alpha = rng.randint(15, 35)
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        od.ellipse([x - r, y - r, x + r, y + r],
                   fill=(*accent, alpha))
        # Compose manually since draw doesn't support alpha directly
        # We'll skip compositing here and use a simpler approach


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Rompe el texto en líneas que quepan en max_width."""
    words = text.split()
    lines = []
    current = ""
    dummy = Image.new("RGB", (1, 1))
    dd = ImageDraw.Draw(dummy)
    for word in words:
        test = f"{current} {word}".strip()
        bbox = dd.textbbox((0, 0), test, font=font)
        if bbox[2] > max_width and current:
            lines.append(current)
            current = word
        else:
            current = test
    if current:
        lines.append(current)
    return lines


def _draw_rounded_rect(draw: ImageDraw.ImageDraw, xy: tuple, radius: int, fill: tuple):
    x0, y0, x1, y1 = xy
    draw.rectangle([x0 + radius, y0, x1 - radius, y1], fill=fill)
    draw.rectangle([x0, y0 + radius, x1, y1 - radius], fill=fill)
    draw.ellipse([x0, y0, x0 + 2 * radius, y0 + 2 * radius], fill=fill)
    draw.ellipse([x1 - 2 * radius, y0, x1, y0 + 2 * radius], fill=fill)
    draw.ellipse([x0, y1 - 2 * radius, x0 + 2 * radius, y1], fill=fill)
    draw.ellipse([x1 - 2 * radius, y1 - 2 * radius, x1, y1], fill=fill)


def generate_banner_png(copy: BannerCopy, palette_name: str = "promo") -> bytes:
    """
    Genera un banner PNG personalizado listo para enviar por WhatsApp.
    Retorna bytes del PNG.
    """
    palette = PALETTES.get(palette_name, PALETTES["promo"])
    c1, c2, accent = palette

    img = Image.new("RGB", (BANNER_W, BANNER_H), c1)
    draw = ImageDraw.Draw(img)

    # Fondo gradiente
    _gradient_background(draw, BANNER_W, BANNER_H, c1, c2)

    # Círculos decorativos (overlay sin alpha, simplificado)
    for cx, cy, cr, opacity in [
        (650, 150, 180, 20), (100, 650, 220, 15), (720, 600, 120, 12)
    ]:
        for pr in range(cr, 0, -8):
            alpha_val = max(0, int(opacity * (1 - pr / cr)))
            color = tuple(min(255, c + alpha_val) for c in accent)
            draw.ellipse([cx - pr, cy - pr, cx + pr, cy + pr],
                         outline=(*color, 255), width=1)

    # ── Franja superior de acento ─────────────────────────────────────────────
    draw.rectangle([0, 0, BANNER_W, 8], fill=accent)

    # ── "Hola, {nombre}!" personalizado ───────────────────────────────────────
    font_greeting = _load_font(_FONT_BOLD, 38)
    greeting = f"¡Hola, {copy.contact_name}!"
    # Sombra
    draw.text((42, 62), greeting, font=font_greeting, fill=(0, 0, 0, 80))
    draw.text((40, 60), greeting, font=font_greeting, fill=(*accent, 255))

    # ── Línea separadora ──────────────────────────────────────────────────────
    draw.rectangle([40, 108, 200, 112], fill=(*accent, 200))

    # ── Headline principal ────────────────────────────────────────────────────
    font_headline = _load_font(_FONT_BOLD, 68)
    pad = 60
    lines = _wrap_text(copy.headline.upper(), font_headline, BANNER_W - pad * 2)
    y_cursor = 140
    for line in lines[:3]:
        draw.text((pad + 2, y_cursor + 2), line, font=font_headline, fill=(0, 0, 0, 60))
        draw.text((pad, y_cursor), line, font=font_headline, fill=(255, 255, 255))
        bbox = draw.textbbox((0, 0), line, font=font_headline)
        y_cursor += bbox[3] - bbox[1] + 12

    # ── Subheadline ───────────────────────────────────────────────────────────
    font_sub = _load_font(_FONT_REGULAR, 34)
    y_cursor += 16
    sub_lines = _wrap_text(copy.subheadline, font_sub, BANNER_W - pad * 2)
    for line in sub_lines[:3]:
        draw.text((pad, y_cursor), line, font=font_sub, fill=(220, 220, 220))
        bbox = draw.textbbox((0, 0), line, font=font_sub)
        y_cursor += bbox[3] - bbox[1] + 8

    # ── Nombre del negocio (pie) ──────────────────────────────────────────────
    font_biz = _load_font(_FONT_BOLD, 28)
    biz_text = copy.business_name.upper()
    draw.text((pad, BANNER_H - 120), biz_text, font=font_biz, fill=(*accent, 255))

    # ── Botón CTA ─────────────────────────────────────────────────────────────
    font_cta = _load_font(_FONT_BOLD, 30)
    cta_bbox = draw.textbbox((0, 0), copy.cta, font=font_cta)
    cta_w = cta_bbox[2] - cta_bbox[0]
    cta_h = cta_bbox[3] - cta_bbox[1]
    btn_pad_x, btn_pad_y = 28, 14
    btn_x0 = pad
    btn_y0 = BANNER_H - 80
    btn_x1 = btn_x0 + cta_w + btn_pad_x * 2
    btn_y1 = btn_y0 + cta_h + btn_pad_y * 2
    _draw_rounded_rect(draw, (btn_x0, btn_y0, btn_x1, btn_y1), 12, accent)
    # Texto del botón en color oscuro para contraste
    txt_color = c1 if sum(accent) > 380 else (255, 255, 255)
    draw.text((btn_x0 + btn_pad_x, btn_y0 + btn_pad_y), copy.cta,
              font=font_cta, fill=txt_color)

    # ── Franja inferior ───────────────────────────────────────────────────────
    draw.rectangle([0, BANNER_H - 6, BANNER_W, BANNER_H], fill=accent)

    # Exportar a bytes
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


async def generate_banner_copy_with_claude(
    business_name: str,
    contact_name: str,
    promo_description: str,
) -> BannerCopy:
    """Usa Claude Haiku para generar el copy del banner en JSON."""
    import json
    from anthropic import AsyncAnthropic
    from app.config import settings

    client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    prompt = f"""Eres un experto en marketing latinoamericano.
Genera el copy para un banner publicitario de WhatsApp.

Negocio: {business_name}
Contacto: {contact_name}
Promoción: {promo_description}

Responde ÚNICAMENTE con un JSON con estas claves (sin texto extra):
{{
  "headline": "Máximo 5 palabras impactantes en mayúsculas",
  "subheadline": "1 oración que explica el beneficio, máximo 12 palabras",
  "cta": "Máximo 4 palabras, acción clara (ej: Ver oferta ahora)"
}}"""

    try:
        response = await client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=120,
            temperature=0.7,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        data = json.loads(raw)
        return BannerCopy(
            headline=data.get("headline", promo_description[:30].upper()),
            subheadline=data.get("subheadline", f"Oferta especial de {business_name}"),
            cta=data.get("cta", "Escríbenos ahora"),
            contact_name=contact_name,
            business_name=business_name,
        )
    except Exception as e:
        logger.warning("[BANNER] Claude copy failed: %s", e)
        return BannerCopy(
            headline=promo_description[:30].upper(),
            subheadline=f"Oferta especial de {business_name}",
            cta="Escríbenos ahora",
            contact_name=contact_name,
            business_name=business_name,
        )
