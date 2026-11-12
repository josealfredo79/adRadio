"""
Banner visual service — genera imágenes PNG personalizadas por contacto.

Pipeline:
  1. Claude genera el copy del anuncio (headline + subheadline + CTA)
  2. Según categoría del negocio y tipo de campaña, se selecciona layout y paleta
  3. Pillow renderiza el banner con variaciones por contacto
  4. Se retorna bytes PNG listo para subir a R2
"""
import io
import json
import logging
import math
import random
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

logger = logging.getLogger(__name__)

# ── Fuentes del sistema ───────────────────────────────────────────────────────
# DejaVu viene en fonts-dejavu-core, instalado en las dos imágenes (web y
# worker). La Ubuntu que se usaba antes no existía en la imagen web: Pillow
# caía a su letra de emergencia de 10 px y el título salía diminuto.
_FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
_FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

# Dimensiones WhatsApp-friendly (ratio ~1:1)
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
    "calido":   [(191, 87, 0),   (243, 146, 0),   (255, 255, 255)],
    "helado":   [(0, 96, 100),   (0, 131, 143),   (224, 247, 250)],
}

# ── Mapeo categoría de negocio → diseño ───────────────────────────────────────
BUSINESS_STYLE = {
    # ── Comida y bebida ────────────────────────────────────────────────────
    "restaurante":    {"layout": "clasico",  "palette": "naranja",  "vibe": "calido"},
    "comida":         {"layout": "ticker",   "palette": "naranja",  "vibe": "urgente"},
    "panaderia":      {"layout": "clasico",  "palette": "calido",   "vibe": "calido"},
    "cafeteria":      {"layout": "clasico",  "palette": "calido",   "vibe": "calido"},
    "bar":            {"layout": "neon",     "palette": "oscuro",   "vibe": "nocturno"},
    "club":           {"layout": "neon",     "palette": "morado",   "vibe": "nocturno"},
    "entretenimiento":{"layout": "neon",     "palette": "rojo",     "vibe": "emocionante"},
    # ── Belleza y bienestar ────────────────────────────────────────────────
    "salon":          {"layout": "centrado", "palette": "elegante", "vibe": "elegante"},
    "belleza":        {"layout": "centrado", "palette": "morado",   "vibe": "moderno"},
    "barberia":       {"layout": "split",    "palette": "oscuro",   "vibe": "nocturno"},
    "spa":            {"layout": "arco",     "palette": "helado",   "vibe": "calma"},
    "yoga":           {"layout": "arco",     "palette": "helado",   "vibe": "calma"},
    # ── Salud ─────────────────────────────────────────────────────────────
    "salud":          {"layout": "arco",     "palette": "azul",     "vibe": "confianza"},
    "farmacia":       {"layout": "arco",     "palette": "verde",    "vibe": "confianza"},
    "dental":         {"layout": "arco",     "palette": "azul",     "vibe": "confianza"},
    "veterinaria":    {"layout": "arco",     "palette": "verde",    "vibe": "amigable"},
    "optica":         {"layout": "arco",     "palette": "azul",     "vibe": "confianza"},
    "guarderia":      {"layout": "arco",     "palette": "verde",    "vibe": "amigable"},
    # ── Deporte ───────────────────────────────────────────────────────────
    "fitness":        {"layout": "split",    "palette": "naranja",  "vibe": "energico"},
    # ── Retail y moda ─────────────────────────────────────────────────────
    "tienda":         {"layout": "ticker",   "palette": "promo",    "vibe": "urgente"},
    "supermercado":   {"layout": "ticker",   "palette": "verde",    "vibe": "urgente"},
    "ferreteria":     {"layout": "ticker",   "palette": "naranja",  "vibe": "urgente"},
    "ropa":           {"layout": "centrado", "palette": "elegante", "vibe": "moderno"},
    "zapateria":      {"layout": "centrado", "palette": "elegante", "vibe": "moderno"},
    "joyeria":        {"layout": "minimal",  "palette": "elegante", "vibe": "exclusivo"},
    "muebleria":      {"layout": "minimal",  "palette": "elegante", "vibe": "exclusivo"},
    "fotografia":     {"layout": "minimal",  "palette": "oscuro",   "vibe": "elegante"},
    # ── Tecnología ────────────────────────────────────────────────────────
    "electronica":    {"layout": "split",    "palette": "azul",     "vibe": "tecnologico"},
    "tecnologia":     {"layout": "split",    "palette": "azul",     "vibe": "innovador"},
    # ── Automotriz y construcción ──────────────────────────────────────────
    "automotriz":     {"layout": "split",    "palette": "rojo",     "vibe": "potente"},
    "construccion":   {"layout": "split",    "palette": "rojo",     "vibe": "potente"},
    # ── Servicios generales ────────────────────────────────────────────────
    "servicios":      {"layout": "clasico",  "palette": "azul",     "vibe": "profesional"},
    "plomeria":       {"layout": "clasico",  "palette": "azul",     "vibe": "profesional"},
    "lavanderia":     {"layout": "clasico",  "palette": "azul",     "vibe": "profesional"},
    # ── Educación ─────────────────────────────────────────────────────────
    "educacion":      {"layout": "centrado", "palette": "azul",     "vibe": "confiable"},
    # ── Finanzas e inmobiliaria ────────────────────────────────────────────
    "inmobiliaria":   {"layout": "minimal",  "palette": "elegante", "vibe": "exclusivo"},
    "financiero":     {"layout": "minimal",  "palette": "elegante", "vibe": "serio"},
    "seguros":        {"layout": "minimal",  "palette": "elegante", "vibe": "serio"},
    # ── Ocio y viajes ─────────────────────────────────────────────────────
    "eventos":        {"layout": "centrado", "palette": "morado",   "vibe": "festivo"},
    "viajes":         {"layout": "split",    "palette": "azul",     "vibe": "aventura"},
}

# ── Mapeo tipo de campaña → diseño ────────────────────────────────────────────
CAMPAIGN_STYLE = {
    "promo":    {"vibe": "urgente"},
    "launch":   {"vibe": "emocionante"},
    "event":    {"vibe": "elegante"},
    "reminder": {"vibe": "amigable"},
    "voces":    {"vibe": "comunitario"},
}

LAYOUTS = list(BUSINESS_STYLE.keys())
VIBE_TONES = {
    "calido":      "Tono cálido y cercano, como de amigos.",
    "nocturno":    "Tono moderno, audaz, ligeramente nocturno.",
    "elegante":    "Tono sofisticado y exclusivo.",
    "moderno":     "Tono moderno, trendy, juvenil.",
    "calma":       "Tono tranquilo, relajante, natural.",
    "confianza":   "Tono profesional que inspire confianza.",
    "energico":    "Tono enérgico y motivacional.",
    "urgente":     "Tono de urgencia, aprovecha la oportunidad.",
    "tecnologico": "Tono innovador, preciso, tecnológico.",
    "profesional": "Tono formal, serio y profesional.",
    "exclusivo":   "Tono premium, exclusivo, aspiracional.",
    "potente":     "Tono contundente, fuerte y directo.",
    "confiable":   "Tono seguro, honesto y confiable.",
    "innovador":   "Tono creativo, innovador y fresco.",
    "serio":       "Tono serio, formal, de confianza.",
    "festivo":     "Tono alegre, divertido, festivo.",
    "aventura":    "Tono aventurero, inspirador, libre.",
    "comunitario": "Tono cercano, comunitario, familiar.",
    "amigable":    "Tono amigable, suave y cordial.",
    "emocionante": "Tono emocionante, expectativa, sorpresa.",
}


class BannerCopy:
    headline: str
    subheadline: str
    cta: str
    contact_name: str
    business_name: str

    def __init__(
        self,
        headline: str = "",
        subheadline: str = "",
        cta: str = "",
        contact_name: str = "",
        business_name: str = "",
    ):
        self.headline = headline
        self.subheadline = subheadline
        self.cta = cta
        self.contact_name = contact_name
        self.business_name = business_name


class BannerDesign:
    layout: str
    palette: str
    vibe: str

    def __init__(self, layout: str = "clasico", palette: str = "promo", vibe: str = "profesional"):
        self.layout = layout
        self.palette = palette
        self.vibe = vibe


# ── Utilidades gráficas ───────────────────────────────────────────────────────

def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        logger.exception("[BANNER] Failed to load font %s", path)
        # Con tamaño: la de emergencia sin tamaño mide 10 px y no se lee.
        return ImageFont.load_default(size=size)


def _greeting(name: str, formal: bool = False) -> str:
    """El cartel del Copiloto es uno para todos y no trae nombre: sin nombre
    se saluda solo "¡Hola!", nunca "¡Hola, !"."""
    name = (name or "").strip()
    if formal:
        return f"Hola, {name}." if name else "Hola."
    return f"¡Hola, {name}!" if name else "¡Hola!"


def _fit_font(text: str, font: ImageFont.FreeTypeFont, max_width: int, max_lines: int,
              min_size: int = 40) -> ImageFont.FreeTypeFont:
    """Achica la letra del título hasta que quepa en max_lines renglones, para
    que el precio o el "solo mañana" del final no se corten."""
    size = int(getattr(font, "size", 0) or 0)
    path = getattr(font, "path", None)
    def too_big(f: ImageFont.FreeTypeFont) -> bool:
        lines = _wrap_text(text, f, max_width)
        # Una palabra sola más ancha que el espacio tampoco cabe (se sale).
        return len(lines) > max_lines or any(f.getlength(ln) > max_width for ln in lines)

    while path and size > min_size and too_big(font):
        size -= 4
        font = _load_font(path, size)
    return font


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
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


def _draw_rounded_rect(draw: ImageDraw.ImageDraw, xy: tuple, radius: int, fill: tuple) -> None:
    x0, y0, x1, y1 = xy
    draw.rectangle([x0 + radius, y0, x1 - radius, y1], fill=fill)
    draw.rectangle([x0, y0 + radius, x1, y1 - radius], fill=fill)
    draw.ellipse([x0, y0, x0 + 2 * radius, y0 + 2 * radius], fill=fill)
    draw.ellipse([x1 - 2 * radius, y0, x1, y0 + 2 * radius], fill=fill)
    draw.ellipse([x0, y1 - 2 * radius, x0 + 2 * radius, y1], fill=fill)
    draw.ellipse([x1 - 2 * radius, y1 - 2 * radius, x1, y1], fill=fill)


def _gradient_background(draw: ImageDraw.ImageDraw, w: int, h: int, c1: tuple, c2: tuple) -> None:
    for y in range(h):
        t = y / h
        r = int(c1[0] + (c2[0] - c1[0]) * t)
        g = int(c1[1] + (c2[1] - c1[1]) * t)
        b = int(c1[2] + (c2[2] - c1[2]) * t)
        draw.line([(0, y), (w, y)], fill=(r, g, b))


def _draw_deco_circles(draw: ImageDraw.ImageDraw, w: int, h: int, accent: tuple, seed: int = 42) -> None:
    rng = random.Random(seed)
    for _ in range(3):
        cx = rng.randint(50, w - 50)
        cy = rng.randint(50, h - 50)
        cr = rng.randint(60, 200)
        for pr in range(cr, 0, -8):
            alpha_val = max(0, int(20 * (1 - pr / cr)))
            color = tuple(min(255, c + alpha_val) for c in accent)
            draw.ellipse([cx - pr, cy - pr, cx + pr, cy + pr],
                         outline=(*color, 255), width=1)


def _draw_particles(draw: ImageDraw.ImageDraw, w: int, h: int, accent: tuple, seed: int = 42) -> None:
    rng = random.Random(seed + 1)
    for _ in range(15):
        x = rng.randint(0, w)
        y = rng.randint(0, h)
        size = rng.randint(2, 5)
        alpha = rng.randint(30, 70)
        color = tuple(min(255, c + alpha) for c in accent)
        draw.ellipse([x - size, y - size, x + size, y + size], fill=(*color, 255))


# ── Renderizadores de layout ──────────────────────────────────────────────────

def _render_clasico(draw: ImageDraw.ImageDraw, copy: BannerCopy, c1: tuple, c2: tuple, accent: tuple, rng: random.Random) -> None:
    """
    Layout BLOQUES: Split horizontal al 55%.
    Bloque superior oscuro con headline grande.
    Bloque inferior en color acento con subheadline y CTA.
    """
    pad = 60
    split_y = int(BANNER_H * 0.56)

    font_greeting = _load_font(_FONT_REGULAR, 30)
    font_headline = _load_font(_FONT_BOLD, 78)
    font_sub = _load_font(_FONT_REGULAR, 32)
    font_biz = _load_font(_FONT_BOLD, 24)
    font_cta = _load_font(_FONT_BOLD, 32)

    # Fondo: bloque superior con gradiente
    _gradient_background(draw, BANNER_W, split_y, c1, c2)
    # Bloque inferior en c2 sólido (color secundario del palette, siempre propio)
    for y in range(split_y, BANNER_H):
        t = (y - split_y) / (BANNER_H - split_y)
        r = int(c2[0] * (1 - t * 0.3))
        g = int(c2[1] * (1 - t * 0.3))
        b = int(c2[2] * (1 - t * 0.3))
        draw.line([(0, y), (BANNER_W, y)], fill=(r, g, b))

    # Línea divisora blanca
    draw.rectangle([0, split_y - 4, BANNER_W, split_y + 4], fill=(255, 255, 255))

    # BLOQUE SUPERIOR: Greeting + Headline
    greeting = _greeting(copy.contact_name)
    # greeting en accent; si accent es muy claro usar blanco
    greet_color = accent if sum(accent) < 600 else (255, 255, 255)
    draw.text((pad, 46), greeting, font=font_greeting, fill=greet_color)

    shadow_color = tuple(max(0, c - 40) for c in c1)  # sombra: tono más oscuro del fondo
    font_headline = _fit_font(copy.headline.upper(), font_headline, BANNER_W - pad * 2, 2)
    lines = _wrap_text(copy.headline.upper(), font_headline, BANNER_W - pad * 2)
    y_cur = 100
    for line in lines[:2]:
        draw.text((pad + 3, y_cur + 3), line, font=font_headline, fill=shadow_color)
        draw.text((pad, y_cur), line, font=font_headline, fill=(255, 255, 255))
        bbox = draw.textbbox((0, 0), line, font=font_headline)
        y_cur += bbox[3] - bbox[1] + 10

    # BLOQUE INFERIOR: Sub + CTA a la derecha
    # texto oscuro si c2 es claro, blanco si c2 es oscuro
    txt_dark = tuple(max(0, c - 60) for c in c2) if sum(c2) > 400 else (255, 255, 255)
    sub_y = split_y + 30
    sub_lines = _wrap_text(copy.subheadline, font_sub, BANNER_W - pad * 2)
    for line in sub_lines[:2]:
        draw.text((pad, sub_y), line, font=font_sub, fill=txt_dark)
        bbox = draw.textbbox((0, 0), line, font=font_sub)
        sub_y += bbox[3] - bbox[1] + 6

    # Nombre del negocio
    biz_color = tuple(max(0, c - 80) for c in c2) if sum(c2) > 400 else (255, 255, 255)
    draw.text((pad, BANNER_H - 110), copy.business_name.upper(), font=font_biz, fill=biz_color)

    # CTA alineado a la derecha
    cta_bbox = draw.textbbox((0, 0), copy.cta, font=font_cta)
    cta_w = cta_bbox[2] - cta_bbox[0]
    cta_h = cta_bbox[3] - cta_bbox[1]
    bpx, bpy = 28, 14
    bx0 = BANNER_W - cta_w - bpx * 2 - pad
    by0 = BANNER_H - 84
    bx1 = BANNER_W - pad
    by1 = by0 + cta_h + bpy * 2
    _draw_rounded_rect(draw, (bx0, by0, bx1, by1), 14, c1)
    draw.text((bx0 + bpx, by0 + bpy), copy.cta, font=font_cta, fill=accent)


def _render_centrado(draw: ImageDraw.ImageDraw, copy: BannerCopy, c1: tuple, c2: tuple, accent: tuple, rng: random.Random) -> None:
    """
    Layout DIAGONAL: Polígono diagonal en acento cubre la esquina inferior-izquierda.
    Texto del headline en zona oscura (arriba-derecha).
    CTA y negocio en la zona acento.
    """
    pad = 60

    # Fondo base oscuro
    _gradient_background(draw, BANNER_W, BANNER_H, c1, c2)

    # Polígono diagonal: triángulo grande esquina inferior-izquierda
    diag_pts = [
        (0, int(BANNER_H * 0.38)),
        (int(BANNER_W * 0.72), BANNER_H),
        (0, BANNER_H),
    ]
    draw.polygon(diag_pts, fill=accent)

    # Línea diagonal decorativa (borde del polígono) ligeramente más brillante
    bright = tuple(min(255, c + 40) for c in accent)
    draw.line([(0, int(BANNER_H * 0.38)), (int(BANNER_W * 0.72), BANNER_H)], fill=bright, width=4)

    font_greeting = _load_font(_FONT_REGULAR, 28)
    font_headline = _load_font(_FONT_BOLD, 76)
    font_sub = _load_font(_FONT_REGULAR, 30)
    font_biz = _load_font(_FONT_BOLD, 26)
    font_cta = _load_font(_FONT_BOLD, 32)

    # Greeting — zona oscura (arriba)
    greeting = _greeting(copy.contact_name)
    draw.text((pad, 46), greeting, font=font_greeting, fill=(*accent, 200))

    # Headline grande — zona oscura (arriba-derecha)
    shadow_diag = tuple(max(0, c - 40) for c in c1)
    font_headline = _fit_font(copy.headline.upper(), font_headline, BANNER_W - pad * 2, 2)
    lines = _wrap_text(copy.headline.upper(), font_headline, BANNER_W - pad * 2)
    y_cur = 100
    for line in lines[:2]:
        draw.text((pad + 2, y_cur + 2), line, font=font_headline, fill=shadow_diag)
        draw.text((pad, y_cur), line, font=font_headline, fill=(255, 255, 255))
        bbox = draw.textbbox((0, 0), line, font=font_headline)
        y_cur += bbox[3] - bbox[1] + 10

    # Subheadline — zona de transición
    txt_on_accent = c1 if sum(accent) > 400 else (255, 255, 255)
    sub_y = int(BANNER_H * 0.60)
    sub_lines = _wrap_text(copy.subheadline, font_sub, int(BANNER_W * 0.55) - pad)
    for line in sub_lines[:2]:
        draw.text((pad, sub_y), line, font=font_sub, fill=txt_on_accent)
        bbox = draw.textbbox((0, 0), line, font=font_sub)
        sub_y += bbox[3] - bbox[1] + 6

    # Business name
    draw.text((pad, BANNER_H - 110), copy.business_name.upper(), font=font_biz,
              fill=(*c1, 180) if sum(accent) > 400 else (255, 255, 255, 180))

    # CTA — zona acento (abajo izquierda)
    cta_bbox = draw.textbbox((0, 0), copy.cta, font=font_cta)
    cta_w = cta_bbox[2] - cta_bbox[0]
    cta_h = cta_bbox[3] - cta_bbox[1]
    bpx, bpy = 28, 14
    bx0, by0 = pad, BANNER_H - 80
    bx1 = bx0 + cta_w + bpx * 2
    by1 = by0 + cta_h + bpy * 2
    _draw_rounded_rect(draw, (bx0, by0, bx1, by1), 14, c1)
    draw.text((bx0 + bpx, by0 + bpy), copy.cta, font=font_cta, fill=accent)


def _render_split(draw: ImageDraw.ImageDraw, copy: BannerCopy, c1: tuple, c2: tuple, accent: tuple, rng: random.Random) -> None:
    """
    Layout VERTICAL: División izquierda-derecha con separador ligeramente inclinado.
    Columna izquierda = acento (nombre + CTA).
    Columna derecha = oscuro (headline + subheadline).
    """
    divider_x_top = int(BANNER_W * 0.38)
    divider_x_bot = int(BANNER_W * 0.42)
    pad_l = 32
    pad_r = 56

    font_greeting = _load_font(_FONT_REGULAR, 26)
    font_headline = _load_font(_FONT_BOLD, 66)
    font_sub = _load_font(_FONT_REGULAR, 28)

    # Columna derecha — fondo oscuro
    _gradient_background(draw, BANNER_W, BANNER_H, c1, c2)

    # Columna izquierda — acento sólido (polígono ligeramente inclinado)
    left_pts = [
        (0, 0),
        (divider_x_top, 0),
        (divider_x_bot, BANNER_H),
        (0, BANNER_H),
    ]
    draw.polygon(left_pts, fill=accent)

    # Línea de borde del separador
    bright = tuple(min(255, c + 50) for c in accent)
    draw.line([(divider_x_top, 0), (divider_x_bot, BANNER_H)], fill=bright, width=5)

    # COLUMNA IZQUIERDA: nombre del negocio y CTA
    txt_l = c1 if sum(accent) > 400 else (255, 255, 255)

    # Nombre del negocio — texto pequeño arriba
    biz_font = _load_font(_FONT_BOLD, 20)
    biz_lines = _wrap_text(copy.business_name.upper(), biz_font, divider_x_top - pad_l * 2)
    biz_y = 40
    biz_color = tuple(max(0, c - 60) for c in accent) if sum(accent) > 400 else (255, 255, 255)
    for bl in biz_lines[:3]:
        draw.text((pad_l, biz_y), bl, font=biz_font, fill=biz_color)
        bb = draw.textbbox((0, 0), bl, font=biz_font)
        biz_y += bb[3] - bb[1] + 4

    # CTA centrado verticalmente en columna izquierda
    cta_font = _load_font(_FONT_BOLD, 28)
    cta_lines = _wrap_text(copy.cta, cta_font, divider_x_top - pad_l * 2)
    total_h = sum(draw.textbbox((0, 0), l, font=cta_font)[3] - draw.textbbox((0, 0), l, font=cta_font)[1] + 8 for l in cta_lines)
    cy = (BANNER_H - total_h) // 2
    for line in cta_lines:
        lb = draw.textbbox((0, 0), line, font=cta_font)
        lx = (divider_x_top - (lb[2] - lb[0])) // 2
        draw.text((lx, cy), line, font=cta_font, fill=txt_l)
        cy += lb[3] - lb[1] + 8

    # COLUMNA DERECHA: greeting + headline + subheadline
    rx = divider_x_bot + pad_r
    max_w = BANNER_W - rx - 30

    greeting = _greeting(copy.contact_name)
    draw.text((rx, 50), greeting, font=font_greeting, fill=(*accent, 190))

    shadow_sp = tuple(max(0, c - 40) for c in c1)
    font_headline = _fit_font(copy.headline.upper(), font_headline, max_w, 3)
    lines = _wrap_text(copy.headline.upper(), font_headline, max_w)
    y_cur = 98
    for line in lines[:3]:
        draw.text((rx + 2, y_cur + 2), line, font=font_headline, fill=shadow_sp)
        draw.text((rx, y_cur), line, font=font_headline, fill=(255, 255, 255))
        bbox = draw.textbbox((0, 0), line, font=font_headline)
        y_cur += bbox[3] - bbox[1] + 8

    y_cur += 16
    sub_lines = _wrap_text(copy.subheadline, font_sub, max_w)
    for line in sub_lines[:3]:
        draw.text((rx, y_cur), line, font=font_sub, fill=(200, 200, 200))
        bbox = draw.textbbox((0, 0), line, font=font_sub)
        y_cur += bbox[3] - bbox[1] + 6

    # Línea decorativa inferior derecha
    draw.rectangle([rx, BANNER_H - 12, BANNER_W - 20, BANNER_H - 8], fill=accent)


def _render_minimal(draw: ImageDraw.ImageDraw, copy: BannerCopy, c1: tuple, c2: tuple, accent: tuple, rng: random.Random) -> None:
    """
    Layout EDITORIAL: Banda de acento en la parte superior (30%).
    Zona oscura con headline grande y subheadline debajo.
    CTA con botón outlined premium.
    Como portada de revista.
    """
    pad = 60
    band_h = int(BANNER_H * 0.30)

    font_greeting = _load_font(_FONT_REGULAR, 28)
    font_headline = _load_font(_FONT_BOLD, 72)
    font_sub = _load_font(_FONT_REGULAR, 30)
    font_biz = _load_font(_FONT_BOLD, 22)
    font_cta = _load_font(_FONT_BOLD, 28)

    # Banda superior en acento
    for y in range(band_h):
        t = y / band_h
        r = int(accent[0] * (1 - t * 0.15))
        g = int(accent[1] * (1 - t * 0.15))
        b = int(accent[2] * (1 - t * 0.15))
        draw.line([(0, y), (BANNER_W, y)], fill=(r, g, b))

    # Cuerpo inferior oscuro
    _gradient_background(draw, BANNER_W, BANNER_H - band_h, c1, c2)
    # (el gradiente se dibuja en (0,0) del canvas pero está desplazado)
    for y in range(band_h, BANNER_H):
        t = (y - band_h) / (BANNER_H - band_h)
        r = int(c1[0] + (c2[0] - c1[0]) * t)
        g = int(c1[1] + (c2[1] - c1[1]) * t)
        b = int(c1[2] + (c2[2] - c1[2]) * t)
        draw.line([(0, y), (BANNER_W, y)], fill=(r, g, b))

    # Línea divisora nítida
    draw.rectangle([0, band_h - 4, BANNER_W, band_h + 4], fill=(255, 255, 255))

    # BANDA SUPERIOR: greeting + nombre del negocio
    txt_band = c1 if sum(accent) > 400 else (255, 255, 255)
    greeting = _greeting(copy.contact_name, formal=True)
    draw.text((pad, band_h // 2 - 40), greeting, font=font_greeting, fill=txt_band)
    draw.text((pad, band_h // 2 + 4), copy.business_name.upper(), font=font_biz, fill=(*c1, 180) if sum(accent) > 400 else (255, 255, 255, 200))

    # Año / badge decorativo en la esquina derecha de la banda
    badge_font = _load_font(_FONT_BOLD, 26)
    draw.text((BANNER_W - 90, band_h // 2 - 14), ">>>", font=badge_font, fill=txt_band)

    # CUERPO: headline grande
    shadow_ed = tuple(max(0, c - 50) for c in c1)
    font_headline = _fit_font(copy.headline.upper(), font_headline, BANNER_W - pad * 2, 2)
    lines = _wrap_text(copy.headline.upper(), font_headline, BANNER_W - pad * 2)
    y_cur = band_h + 40
    for line in lines[:2]:
        draw.text((pad + 2, y_cur + 2), line, font=font_headline, fill=shadow_ed)
        draw.text((pad, y_cur), line, font=font_headline, fill=(255, 255, 255))
        bbox = draw.textbbox((0, 0), line, font=font_headline)
        y_cur += bbox[3] - bbox[1] + 10

    # Separator line
    draw.rectangle([pad, y_cur + 14, pad + 80, y_cur + 18], fill=accent)
    y_cur += 44

    # Subheadline
    sub_lines = _wrap_text(copy.subheadline, font_sub, BANNER_W - pad * 2)
    for line in sub_lines[:2]:
        draw.text((pad, y_cur), line, font=font_sub, fill=(185, 185, 185))
        bbox = draw.textbbox((0, 0), line, font=font_sub)
        y_cur += bbox[3] - bbox[1] + 6

    # CTA outlined — esquina inferior derecha
    cta_bbox = draw.textbbox((0, 0), copy.cta, font=font_cta)
    cta_w = cta_bbox[2] - cta_bbox[0]
    cta_h_px = cta_bbox[3] - cta_bbox[1]
    bpx, bpy = 26, 14
    bx0 = BANNER_W - cta_w - bpx * 2 - pad
    by0 = BANNER_H - 90
    bx1 = BANNER_W - pad
    by1 = by0 + cta_h_px + bpy * 2
    draw.rounded_rectangle([bx0, by0, bx1, by1], radius=8, outline=accent, width=2)
    draw.text((bx0 + bpx, by0 + bpy), copy.cta, font=font_cta, fill=accent)


# ── Mapeo de layouts a renderizadores ───────────────────────────────────────────────

def _render_ticker(draw: ImageDraw.ImageDraw, copy: BannerCopy, c1: tuple, c2: tuple, accent: tuple, rng: random.Random) -> None:
    """
    Layout TICKER: Barra gruesa de acento en la parte inferior (urgencia/promo).
    Parte superior oscura con headline muy grande. Para tiendas y promos rápidas.
    """
    pad = 60
    ticker_h = 138
    ticker_y = BANNER_H - ticker_h

    _gradient_background(draw, BANNER_W, BANNER_H, c1, c2)

    # Líneas horizontales decorativas sutiles en zona oscura
    line_hi = tuple(min(255, c + 18) for c in c1)
    for y in range(0, ticker_y, 44):
        draw.line([(0, y), (BANNER_W, y)], fill=line_hi, width=1)

    # Ticker bar solida en color acento
    for y in range(ticker_y, BANNER_H):
        t = (y - ticker_y) / (BANNER_H - ticker_y)
        r = int(accent[0] * (1 - t * 0.18))
        g = int(accent[1] * (1 - t * 0.18))
        b = int(accent[2] * (1 - t * 0.18))
        draw.line([(0, y), (BANNER_W, y)], fill=(r, g, b))

    # Divisor brillante entre zona oscura y ticker
    bright = tuple(min(255, c + 50) for c in accent)
    draw.rectangle([0, ticker_y - 4, BANNER_W, ticker_y + 4], fill=bright)

    font_greeting = _load_font(_FONT_REGULAR, 26)
    font_headline = _load_font(_FONT_BOLD, 90)
    font_biz = _load_font(_FONT_BOLD, 24)
    font_cta = _load_font(_FONT_BOLD, 36)

    # Greeting
    greet_col = accent if sum(accent) < 600 else (255, 255, 255)
    draw.text((pad, 50), _greeting(copy.contact_name), font=font_greeting, fill=greet_col)

    # Headline extra grande en zona oscura
    shadow = tuple(max(0, c - 30) for c in c1)
    font_headline = _fit_font(copy.headline.upper(), font_headline, BANNER_W - pad * 2, 2)
    lines = _wrap_text(copy.headline.upper(), font_headline, BANNER_W - pad * 2)
    y_cur = 110
    for line in lines[:2]:
        draw.text((pad + 3, y_cur + 3), line, font=font_headline, fill=shadow)
        draw.text((pad, y_cur), line, font=font_headline, fill=(255, 255, 255))
        bbox = draw.textbbox((0, 0), line, font=font_headline)
        y_cur += bbox[3] - bbox[1] + 8

    # Ticker bar: nombre del negocio a la izquierda, CTA a la derecha
    txt_tk = tuple(max(0, c - 70) for c in accent) if sum(accent) > 400 else (255, 255, 255)
    draw.text((pad, ticker_y + 14), copy.business_name.upper(), font=font_biz, fill=txt_tk)

    cta_bbox = draw.textbbox((0, 0), copy.cta, font=font_cta)
    cta_w = cta_bbox[2] - cta_bbox[0]
    cta_h = cta_bbox[3] - cta_bbox[1]
    cx = BANNER_W - cta_w - pad
    cy = ticker_y + (ticker_h - cta_h) // 2
    arrow_w = draw.textbbox((0, 0), ">> ", font=font_cta)[2]
    draw.text((cx - arrow_w, cy), ">>", font=font_cta, fill=txt_tk)
    draw.text((cx, cy), copy.cta, font=font_cta, fill=txt_tk)


def _render_neon(draw: ImageDraw.ImageDraw, copy: BannerCopy, c1: tuple, c2: tuple, accent: tuple, rng: random.Random) -> None:
    """
    Layout NEON: Efecto de texto brillante sobre fondo muy oscuro.
    Marco doble de neón. Para bares nocturnos y negocios de entretenimiento.
    """
    pad = 56

    # Fondo muy oscuro (más oscuro que c1)
    dark = tuple(max(0, c - 25) for c in c1)
    for y in range(BANNER_H):
        draw.line([(0, y), (BANNER_W, y)], fill=dark)

    # Marco doble neon
    draw.rectangle([8, 8, BANNER_W - 8, BANNER_H - 8], outline=accent, width=3)
    bright_border = tuple(min(255, c + 70) for c in accent)
    draw.rectangle([16, 16, BANNER_W - 16, BANNER_H - 16], outline=bright_border, width=1)

    font_greeting = _load_font(_FONT_REGULAR, 28)
    font_headline = _load_font(_FONT_BOLD, 72)
    font_sub = _load_font(_FONT_REGULAR, 30)
    font_biz = _load_font(_FONT_BOLD, 24)
    font_cta = _load_font(_FONT_BOLD, 32)

    glow = tuple(min(255, c + 90) for c in accent)

    # Greeting
    draw.text((pad, 48), _greeting(copy.contact_name), font=font_greeting, fill=accent)

    # Headline con efecto glow: 8 trazos desplazados en color brillante + texto blanco encima
    font_headline = _fit_font(copy.headline.upper(), font_headline, BANNER_W - pad * 2, 2)
    lines = _wrap_text(copy.headline.upper(), font_headline, BANNER_W - pad * 2)
    y_cur = 106
    for line in lines[:2]:
        for dx, dy in [(-2, 0), (2, 0), (0, -2), (0, 2), (-2, -2), (2, 2), (-2, 2), (2, -2)]:
            draw.text((pad + dx, y_cur + dy), line, font=font_headline, fill=glow)
        draw.text((pad, y_cur), line, font=font_headline, fill=(255, 255, 255))
        bbox = draw.textbbox((0, 0), line, font=font_headline)
        y_cur += bbox[3] - bbox[1] + 10

    # Línea neón separadora
    y_cur += 18
    draw.rectangle([pad, y_cur, pad + 70, y_cur + 3], fill=accent)
    y_cur += 22

    # Subheadline
    sub_lines = _wrap_text(copy.subheadline, font_sub, BANNER_W - pad * 2)
    for line in sub_lines[:2]:
        draw.text((pad, y_cur), line, font=font_sub, fill=(165, 165, 165))
        bbox = draw.textbbox((0, 0), line, font=font_sub)
        y_cur += bbox[3] - bbox[1] + 6

    # Business name
    draw.text((pad, BANNER_H - 110), copy.business_name.upper(), font=font_biz, fill=accent)

    # CTA botón sólido en acento
    cta_bbox = draw.textbbox((0, 0), copy.cta, font=font_cta)
    cta_w = cta_bbox[2] - cta_bbox[0]
    cta_h = cta_bbox[3] - cta_bbox[1]
    bpx, bpy = 28, 14
    bx0 = BANNER_W - cta_w - bpx * 2 - pad
    by0 = BANNER_H - 80
    bx1 = BANNER_W - pad
    by1 = by0 + cta_h + bpy * 2
    _draw_rounded_rect(draw, (bx0, by0, bx1, by1), 12, accent)
    txt_cta = dark if sum(accent) > 400 else (255, 255, 255)
    draw.text((bx0 + bpx, by0 + bpy), copy.cta, font=font_cta, fill=txt_cta)


def _render_arco(draw: ImageDraw.ImageDraw, copy: BannerCopy, c1: tuple, c2: tuple, accent: tuple, rng: random.Random) -> None:
    """
    Layout ARCO: Portal/arco en la parte superior con anillo de acento.
    Contenido centrado debajo. Para spas, salud, bienestar y farmacias.
    """
    pad = 60

    _gradient_background(draw, BANNER_W, BANNER_H, c1, c2)

    # Arco: círculo grande centrado con su parte superior visible
    arch_r = 320
    arch_cx = BANNER_W // 2
    arch_cy = -arch_r + 210  # centro sobre el canvas: solo la parte inferior del círculo es visible

    # Arco exterior (acento)
    draw.ellipse(
        [arch_cx - arch_r, arch_cy, arch_cx + arch_r, arch_cy + arch_r * 2],
        fill=accent,
    )
    # Círculo interior (fondo) crea el anillo
    inner_r = arch_r - 48
    draw.ellipse(
        [arch_cx - inner_r, arch_cy + 8, arch_cx + inner_r, arch_cy + inner_r * 2 + 8],
        fill=c1,
    )
    # Segundo gradiente encima del círculo interior para suavizar la transición
    for y in range(min(210, BANNER_H)):
        t = y / BANNER_H
        r2 = int(c1[0] + (c2[0] - c1[0]) * t)
        g2 = int(c1[1] + (c2[1] - c1[1]) * t)
        b2 = int(c1[2] + (c2[2] - c1[2]) * t)
        # Solo pinta dentro del círculo interior
        half_chord = int((inner_r ** 2 - max(0, (y - (arch_cy + inner_r))) ** 2) ** 0.5) if abs(y - (arch_cy + inner_r)) <= inner_r else 0
        if half_chord > 0:
            x0 = max(0, arch_cx - half_chord)
            x1 = min(BANNER_W, arch_cx + half_chord)
            draw.line([(x0, y), (x1, y)], fill=(r2, g2, b2))

    font_greeting = _load_font(_FONT_REGULAR, 26)
    font_headline = _load_font(_FONT_BOLD, 68)
    font_sub = _load_font(_FONT_REGULAR, 28)
    font_biz = _load_font(_FONT_BOLD, 22)
    font_cta = _load_font(_FONT_BOLD, 30)

    # Greeting dentro del arco (zona acento visible)
    txt_arch = tuple(max(0, c - 70) for c in accent) if sum(accent) > 400 else (255, 255, 255)
    greeting = _greeting(copy.contact_name, formal=True)
    g_bbox = draw.textbbox((0, 0), greeting, font=font_greeting)
    g_x = (BANNER_W - (g_bbox[2] - g_bbox[0])) // 2
    draw.text((g_x, 36), greeting, font=font_greeting, fill=txt_arch)

    # Headline centrado debajo del arco
    shadow = tuple(max(0, c - 40) for c in c1)
    font_headline = _fit_font(copy.headline.upper(), font_headline, BANNER_W - pad * 2, 2)
    lines = _wrap_text(copy.headline.upper(), font_headline, BANNER_W - pad * 2)
    y_cur = 228
    for line in lines[:2]:
        l_bbox = draw.textbbox((0, 0), line, font=font_headline)
        lx = (BANNER_W - (l_bbox[2] - l_bbox[0])) // 2
        draw.text((lx + 2, y_cur + 2), line, font=font_headline, fill=shadow)
        draw.text((lx, y_cur), line, font=font_headline, fill=(255, 255, 255))
        bbox = draw.textbbox((0, 0), line, font=font_headline)
        y_cur += bbox[3] - bbox[1] + 10

    y_cur += 18
    sub_lines = _wrap_text(copy.subheadline, font_sub, BANNER_W - pad * 2)
    for line in sub_lines[:2]:
        s_bbox = draw.textbbox((0, 0), line, font=font_sub)
        sx = (BANNER_W - (s_bbox[2] - s_bbox[0])) // 2
        draw.text((sx, y_cur), line, font=font_sub, fill=(175, 175, 175))
        bbox = draw.textbbox((0, 0), line, font=font_sub)
        y_cur += bbox[3] - bbox[1] + 6

    # Business name centrado
    biz_bbox = draw.textbbox((0, 0), copy.business_name.upper(), font=font_biz)
    biz_x = (BANNER_W - (biz_bbox[2] - biz_bbox[0])) // 2
    draw.text((biz_x, BANNER_H - 110), copy.business_name.upper(), font=font_biz, fill=accent)

    # CTA centrado sólido
    cta_bbox = draw.textbbox((0, 0), copy.cta, font=font_cta)
    cta_w = cta_bbox[2] - cta_bbox[0]
    cta_h = cta_bbox[3] - cta_bbox[1]
    bpx, bpy = 30, 14
    bx0 = (BANNER_W - cta_w - bpx * 2) // 2
    by0 = BANNER_H - 78
    bx1 = bx0 + cta_w + bpx * 2
    by1 = by0 + cta_h + bpy * 2
    _draw_rounded_rect(draw, (bx0, by0, bx1, by1), 16, accent)
    txt_cta = c1 if sum(accent) > 400 else (255, 255, 255)
    draw.text((bx0 + bpx, by0 + bpy), copy.cta, font=font_cta, fill=txt_cta)


# ── Mapeo de layouts a renderizadores ─────────────────────────────────────────
_RENDERERS = {
    "clasico":  _render_clasico,
    "centrado": _render_centrado,
    "split":    _render_split,
    "minimal":  _render_minimal,
    "ticker":   _render_ticker,
    "neon":     _render_neon,
    "arco":     _render_arco,
}


# ── Selección de diseño según negocio y campaña ───────────────────────────────

def select_design(business_category: str | None, campaign_type: str | None) -> BannerDesign:
    """Elige layout, paleta y vibe según categoría del negocio y tipo de campaña."""
    biz_key = (business_category or "").lower().strip()
    biz_style = BUSINESS_STYLE.get(biz_key)
    camp_style = CAMPAIGN_STYLE.get(campaign_type or "")

    if biz_style:
        layout = biz_style["layout"]
        palette = biz_style["palette"]
    else:
        if camp_style:
            fallback = {
                "elegante":    ("centrado", "elegante"),
                "urgente":     ("clasico",  "rojo"),
                "emocionante": ("split",    "promo"),
            }
            layout, palette = fallback.get(camp_style["vibe"], ("clasico", "promo"))
        else:
            layout, palette = "clasico", "promo"

    final_vibe = camp_style["vibe"] if camp_style else (biz_style["vibe"] if biz_style else "profesional")
    return BannerDesign(layout=layout, palette=palette, vibe=final_vibe)


# ── Generación de banner ──────────────────────────────────────────────────────

def generate_banner_png(
    copy: BannerCopy,
    palette_name: str = "promo",
    layout: str = "clasico",
    contact_id: str | None = None,
) -> bytes:
    """
    Genera un banner PNG personalizado.
    contact_id se usa como seed para que cada contacto reciba variaciones únicas.
    """
    palette = PALETTES.get(palette_name, PALETTES["promo"])
    c1, c2, accent = palette

    renderer = _RENDERERS.get(layout, _RENDERERS["clasico"])

    img = Image.new("RGB", (BANNER_W, BANNER_H), c1)
    draw = ImageDraw.Draw(img)

    seed = abs(hash(str(contact_id))) % 10000 if contact_id else 42
    rng = random.Random(seed)

    # Cada renderer maneja su propio fondo — no aplicar fondo global aquí
    renderer(draw, copy, c1, c2, accent, rng)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ── Generación de copy con IA ─────────────────────────────────────────────────

async def generate_banner_copy_with_claude(
    business_name: str,
    contact_name: str,
    promo_description: str,
    business_category: str | None = None,
    campaign_type: str | None = None,
) -> BannerCopy:
    """Genera el copy del banner, adaptado al negocio y campaña."""
    import json

    from app.services.llm_client import chat_completion

    design = select_design(business_category, campaign_type)
    vibe_tone = VIBE_TONES.get(design.vibe, "Tono profesional y atractivo.")

    prompt = f"""Eres un experto en marketing latinoamericano.
Genera el copy para un banner publicitario de WhatsApp.

Negocio: {business_name}
Contacto: {contact_name}
Promoción: {promo_description}
Estilo: {vibe_tone}

Reglas:
- Usa SOLO lo que dice la promoción. No agregues adjetivos ni datos que no
  estén ahí (nada de "premium", "original", "garantía", "envío gratis").
- Si la promoción trae precio, el headline lo lleva EXACTO, sin centavos ($100, no $100.00).
- Si dice cuándo vale ("solo mañana", "hasta el sábado"), ponlo en el subheadline.

Responde ÚNICAMENTE con un JSON con estas claves (sin texto extra):
{{
  "headline": "Máximo 5 palabras impactantes, alineadas al estilo",
  "subheadline": "1 oración que explica el beneficio, máximo 12 palabras",
  "cta": "Máximo 4 palabras, acción clara (ej: Ver oferta ahora)"
}}"""

    try:
        # 350, no 120: algunos modelos gratis de OpenRouter razonan antes
        # de responder (tokens ocultos que sí cuentan contra max_tokens) —
        # un techo muy ajustado los corta antes de escribir el JSON visible.
        raw = await chat_completion(
            [{"role": "user", "content": prompt}],
            max_tokens=350, temperature=0.7,
        )
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


# ── Cartel de oferta (Copiloto, "Cartel de colores") ─────────────────────────
# Precio grande en estrella, precio de antes tachado y cinta de "cuándo".
# La IA solo SEPARA el texto del dueño en partes; nada se inventa: un precio
# que no está en su texto no se dibuja (spec: el bot no inventa precios).

_FONT_OFFER = str(Path(__file__).resolve().parents[1] / "assets" / "fonts" / "Montserrat-Variable.ttf")
_PRICE_RE = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?")
# Palabras sueltas al final que la IA arrastra: "Cargador marca baja", "3 por".
_TRAILING_RE = re.compile(r"(?:\s+(?:a|en|por|de|x|baja|bajan|solo|desde|hasta))+\s*$", re.IGNORECASE)


class OfferCopy:
    def __init__(self, product: str = "", price: str = "", old_price: str = "", when: str = "",
                 price_note: str = "", sub: str = "", cta: str = "", business_name: str = "",
                 contact: str = "", delivery: str = ""):
        self.product = product
        self.price = price
        self.old_price = old_price
        self.when = when
        self.price_note = price_note
        self.sub = sub
        self.cta = cta
        self.business_name = business_name
        # Datos reales del negocio para la barra de abajo (no de la IA).
        self.contact = contact
        self.delivery = delivery


_DAYS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
_DAYS_PLAIN = ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo")


def concrete_when(when: str, today, send_day) -> str:
    """"Solo mañana" escrito de noche sale a las 8:00 del día siguiente: el
    cliente leería "mañana" = pasado mañana. Se cambia por la fecha concreta
    contada desde el día en que el dueño la escribió (today), y se dice "hoy"
    si cae el día en que llega el mensaje (send_day)."""
    from datetime import timedelta

    if not when:
        return when
    low = when.lower()
    plain = low.translate(str.maketrans("áéíóúñ", "aeioun"))
    # Rangos o repeticiones ("de lunes a viernes", "todos los martes", "hoy y
    # mañana", "desde mañana") se dejan tal cual: una sola fecha los acortaría.
    named = sum(1 for d in (*_DAYS_PLAIN, "hoy", "manana") if re.search(rf"\b{d}\b", plain))
    if named > 1 or re.search(r"\b(a|al|y|e|o|todos|todas|los|las|desde|cada|entre|diario|semana)\b", plain):
        return when
    target = None
    if "pasado manana" in plain:
        target = today + timedelta(days=2)
    elif re.search(r"\bmanana\b", plain) and not re.search(r"\b(la|las|en|por|de)\s+manana", plain):
        target = today + timedelta(days=1)
    elif re.search(r"\bhoy\b", plain):
        target = today
    else:
        for i, day in enumerate(_DAYS_PLAIN):
            if re.search(rf"\b{day}\b", plain):
                if i == today.weekday():
                    return when  # "hasta el lunes" dicho en lunes: ¿hoy o el otro? No se adivina.
                target = today + timedelta(days=(i - today.weekday()) % 7)
                break
    if target is None:
        return when
    label = f"{_DAYS[target.weekday()]} {target.day}"
    if "hasta" in plain:
        return f"Hasta hoy · {label}" if target == send_day else f"Hasta el {label}"
    solo = "Solo " if "solo" in plain or "unicamente" in plain else ""
    if target == send_day:
        return f"{solo}hoy · {label}".capitalize()
    return f"{solo}el {label}".capitalize()


_CAPTION_DAY_RE = re.compile(r"\b((?:solo|sólo|únicamente|hasta)\s+)?(pasado\s+mañana|mañana)\b", re.IGNORECASE)


def concrete_caption(text: str, today, send_day) -> str:
    """El texto que acompaña al cartel debe decir la misma fecha que el
    cartel: "solo mañana" escrito de noche → "solo hoy, jueves 12". Solo se
    toca un "mañana" suelto (no "en la mañana", "desde mañana", "hoy y mañana")."""
    if not text:
        return text
    hits = list(_CAPTION_DAY_RE.finditer(text))
    if len(hits) != 1:
        return text
    m = hits[0]
    before = text[:m.start()].lower().rstrip()
    if re.search(r"\b(la|las|en|por|de|desde|partir|y|a)$", before) or re.search(r"\bhoy\b", text, re.IGNORECASE):
        return text
    new = concrete_when(m.group(0), today, send_day)
    if new == m.group(0):
        return text
    new = new.replace(" · ", ", ")
    if not text[:m.start()].strip() or text[:m.start()].rstrip().endswith((".", "!", "?")):
        new = new[0].upper() + new[1:]
    else:
        new = new[0].lower() + new[1:]
    return text[:m.start()] + new + text[m.end():]


def _offer_font(size: int, weight: int = 900) -> ImageFont.FreeTypeFont:
    try:
        f = ImageFont.truetype(_FONT_OFFER, size)
        f.set_variation_by_axes([weight])
        return f
    except Exception:
        logger.exception("[BANNER] offer font failed")
        return _load_font(_FONT_BOLD if weight >= 700 else _FONT_REGULAR, size)


def _offer_fit(text: str, size: int, max_width: int, max_lines: int, weight: int = 900,
               min_size: int = 40) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    while True:
        f = _offer_font(size, weight)
        lines = _wrap_text(text, f, max_width)
        fits = len(lines) <= max_lines and all(f.getlength(ln) <= max_width for ln in lines)
        if fits or size <= min_size:
            return f, lines[:max_lines]
        size -= 4


def _clean_price(value: str) -> str:
    """"$100.00" → "$100"; "$1500" y "$1.500" → "$1,500"; "$1,50" → "$1.50"."""
    raw = re.sub(r"[^\d.,]", "", value or "").strip(".,")
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", raw):  # punto de miles: 1.500
        raw = raw.replace(".", "")
    elif re.fullmatch(r"\d+,\d{1,2}", raw):  # coma decimal: 1,50
        raw = raw.replace(",", ".")
    digits = raw.replace(",", "")
    if not digits:
        return ""
    try:
        n = float(digits)
    except ValueError:
        return ""
    return f"${n:,.0f}" if n.is_integer() else f"${n:,.2f}"


def _amount(price: str) -> float:
    try:
        return float(price.replace("$", "").replace(",", ""))
    except ValueError:
        return 0.0


def _said(value: str, text: str, numbers_only: bool = False) -> bool:
    """¿Lo que puso la IA viene del texto del dueño? Números siempre; palabras
    (de 3+ letras) solo si numbers_only es False."""
    if not value:
        return True
    low = (text or "").lower()
    nums = re.findall(r"\d+", value)
    if numbers_only:
        squeezed = re.sub(r"\s+", "", low)
        return bool(nums) and all(n in re.findall(r"\d+", low) for n in nums) and (
            "x" not in value.lower() or re.sub(r"\s+", "", value.lower()) in squeezed)
    words = [w for w in re.findall(r"[a-záéíóúñü]+", value.lower()) if len(w) > 2]
    return all(n in low for n in nums) and all(w in low for w in words)


def _prices_in(text: str) -> list[str]:
    return [_clean_price(m) for m in _PRICE_RE.findall(text or "")]


def _offer_from_text(promo: str, business_name: str) -> OfferCopy:
    """Sin IA: el precio sale del texto ($…); el último es el de ahora."""
    prices = _prices_in(promo)
    product = _PRICE_RE.sub("", promo).strip(" .,:;-!¡")
    product = re.sub(r"\s+(a|en|por|de)\s*$", "", product, flags=re.IGNORECASE)
    return OfferCopy(
        product=product[:40] or promo[:40], price=prices[-1] if prices else "",
        old_price=prices[0] if len(prices) > 1 else "", cta="Escríbenos hoy", business_name=business_name,
    )


async def generate_offer_copy(business_name: str, promo_description: str) -> OfferCopy:
    from app.services.llm_client import chat_completion

    prompt = f"""Separa esta promoción de un negocio en partes para un cartel.
Negocio: {business_name}
Promoción: {promo_description}

Reglas:
- Usa SOLO palabras de la promoción. No agregues adjetivos ni datos (nada de
  "premium", "original", "garantía", "envío gratis").
- product: SOLO el nombre del producto o servicio (máx. 4 palabras), sin
  verbos ("baja", "llega"), precio ni fecha. "cargador marca baja a $100" →
  "Cargador marca".
- price: el precio de AHORA tal como está escrito ($100). Vacío si no hay.
- old_price: el precio de antes solo si la promoción lo dice. Si no, vacío.
- when: cuándo vale ("Solo mañana", "Hasta el sábado"). Vacío si no lo dice.
- price_note: cantidad o tipo de oferta si lo dice: "3 tacos" (de "3 por
  $50"), "2x1", "20%". Si no, vacío.
- sub: frase corta (máx. 7 palabras) que invite SIN repetir producto, precio
  ni fecha (ej: "Aprovecha antes de que se acabe"). Puede ir vacía.
- cta: acción de máx. 3 palabras (ej: "Pídelo por WhatsApp", "Aparta el tuyo").

Ejemplo. Promoción: "Tacos al pastor 3 por $50 hasta el sábado"
{{"product": "Tacos al pastor", "price": "$50", "old_price": "", "when": "Hasta el sábado", "price_note": "3 tacos", "sub": "Recién hechos, ven por los tuyos", "cta": "Haz tu pedido"}}

Responde ÚNICAMENTE con el JSON de la promoción de arriba (las 7 claves, sub y cta siempre llenos)."""
    fallback = _offer_from_text(promo_description, business_name)
    try:
        raw = await chat_completion([{"role": "user", "content": prompt}], max_tokens=400, temperature=0.3)
        match = re.search(r"\{.*\}", raw or "", re.DOTALL)
        data = json.loads(match.group(0) if match else raw)
    except Exception as e:
        logger.warning("[BANNER] offer copy failed: %s", e)
        return fallback

    def field(key: str, limit: int) -> str:
        value = data.get(key) or ""
        return str(value).strip()[:limit] if isinstance(value, (str, int, float)) else ""

    in_text = set(_prices_in(promo_description))
    # Un precio que no está en el texto del dueño no se dibuja.
    price = _clean_price(field("price", 20))
    price = price if price in in_text else fallback.price
    old = _clean_price(field("old_price", 20))
    old = old if old in in_text and old != price else ""
    if old and price and _amount(old) < _amount(price):  # vinieron al revés
        price, old = old, price
    product = _TRAILING_RE.sub("", field("product", 40)) or fallback.product
    note = _TRAILING_RE.sub("", field("price_note", 20))
    if note.isdigit():  # "3" solo no dice nada; "3 tacos" sí
        note = ""
    # Ni la oferta ("30%", "2x1") ni el "cuándo" se inventan: sus números y
    # palabras tienen que venir en el texto del dueño.
    if not _said(note, promo_description, numbers_only=True):
        note = ""
    when = field("when", 24)
    if not _said(when, promo_description):
        when = ""
    sub = field("sub", 60)
    # La frase de abajo no repite la promo (ya está en grande arriba).
    if _PRICE_RE.search(sub) or (product and product.lower() in sub.lower()):
        sub = ""
    return OfferCopy(
        product=product, price=price, old_price=old, when=when, price_note=note,
        sub=sub, cta=field("cta", 28) or "Escríbenos hoy", business_name=business_name,
    )


def _star(cx: float, cy: float, r_out: float, r_in: float, n: int = 18, rot: float = 0.1) -> list:
    pts = []
    for i in range(n * 2):
        r = r_out if i % 2 == 0 else r_in
        a = rot + math.pi * i / n
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def _darker(c: tuple, k: float = 0.55) -> tuple:
    return tuple(int(v * k) for v in c)


def _square(photo: bytes | None, side: int) -> Image.Image | None:
    if not photo:
        return None
    try:
        img = Image.open(io.BytesIO(photo)).convert("RGB")
    except Exception:
        logger.warning("[BANNER] offer photo unreadable", exc_info=True)
        return None
    m = min(img.size)
    left, top = (img.width - m) // 2, (img.height - m) // 2
    return img.crop((left, top, left + m, top + m)).resize((side, side), Image.LANCZOS)


def _rounded(img: Image.Image, radius: int) -> Image.Image:
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, img.width - 1, img.height - 1], radius=radius, fill=255)
    out = img.convert("RGBA")
    out.putalpha(mask)
    return out


def _paste_shadow(img: Image.Image, box: tuple, radius: int, S: int, round_: bool = False) -> None:
    x0, y0, x1, y1 = box
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(sh)
    if round_:
        d.ellipse([x0 + 10 * S, y0 + 18 * S, x1 + 10 * S, y1 + 18 * S], fill=(0, 0, 0, 120))
    else:
        d.rounded_rectangle([x0 + 10 * S, y0 + 18 * S, x1 + 10 * S, y1 + 18 * S], radius=radius, fill=(0, 0, 0, 110))
    sh = sh.filter(ImageFilter.GaussianBlur(18 * S))
    img.paste(sh, (0, 0), sh)


def offer_banner_png(offer: OfferCopy, palette_name: str = "promo", photo: bytes | None = None,
                     logo: bytes | None = None) -> bytes:
    """Cartel de oferta 1080×1080, dibujado al doble y reducido (bordes suaves).
    Con foto: la foto del producto en una tarjeta y la estrella encima de su
    esquina. Sin foto: la estrella grande a la derecha."""
    c1, c2, accent = PALETTES.get(palette_name, PALETTES["promo"])
    S, size = 2, 1080
    W = H = size * S
    deep = _darker(c1, 0.6)
    pad = 70 * S
    bar_h = 200 * S
    bar_y = H - bar_h

    # Fondo: degradado radial, rayas diagonales y semitono en una esquina.
    mask = Image.radial_gradient("L").resize((int(W * 1.6), int(H * 1.6)))
    mask = mask.crop((int(W * 0.15), int(H * 0.25), int(W * 0.15) + W, int(H * 0.25) + H))
    img = Image.composite(Image.new("RGB", (W, H), deep), Image.new("RGB", (W, H), c2), mask)
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld = ImageDraw.Draw(lay)
    for x in range(-H, W, 70 * S):
        ld.line([(x, H), (x + H, 0)], fill=(255, 255, 255, 14), width=18 * S)
    for gy in range(0, 380 * S, 26 * S):
        for gx in range(0, 380 * S, 26 * S):
            r = max(0.0, (380 * S - math.hypot(gx, gy)) / (380 * S)) * 6 * S
            if r > 0.6 * S:
                x, y = gx, bar_y - 20 * S - gy
                ld.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, 30))
    img.paste(lay, (0, 0), lay)
    draw = ImageDraw.Draw(img)

    big = offer.price or (offer.price_note if len(offer.price_note) <= 6 else "")
    pic = _square(photo, 420 * S)
    text_w = (450 if (big or pic) else 940) * S
    if pic:
        text_w = 470 * S

    # Encabezado: logo redondo + nombre, o la etiqueta blanca con el nombre.
    logo_img = _square(logo, 104 * S)
    top = 60 * S
    if logo_img:
        ring = 112 * S
        _paste_shadow(img, (pad, top, pad + ring, top + ring), 0, S // 2 or 1, round_=True)
        draw = ImageDraw.Draw(img)
        draw.ellipse([pad, top, pad + ring, top + ring], fill=(255, 255, 255))
        lm = Image.new("L", logo_img.size, 0)
        ImageDraw.Draw(lm).ellipse([0, 0, logo_img.width - 1, logo_img.height - 1], fill=255)
        img.paste(logo_img, (pad + 4 * S, top + 4 * S), lm)
        if offer.business_name:
            nf, nl = _offer_fit(offer.business_name.upper(), 34 * S, 760 * S, 1, 800, 20 * S)
            draw.text((pad + ring + 24 * S, top + ring / 2), nl[0], font=nf, fill=(255, 255, 255), anchor="lm")
        y = top + ring + 50 * S
    else:
        if offer.business_name:
            bf, blines = _offer_fit(offer.business_name.upper(), 30 * S, 760 * S, 1, 800, 20 * S)
            bw = bf.getlength(blines[0])
            draw.rounded_rectangle([pad, top + 4 * S, pad + bw + 56 * S, top + 66 * S], radius=31 * S,
                                   fill=(255, 255, 255))
            draw.text((pad + 28 * S, top + 35 * S), blines[0], font=bf, fill=deep, anchor="lm")
        y = top + 130 * S

    # Producto + cinta, centrados en el alto libre de la izquierda.
    pf, lines = _offer_fit((offer.product or "Oferta").upper(), 116 * S, text_w, 3, 900, 48 * S)
    block = len(lines) * pf.size * 1.02 + (130 * S if offer.when else 0)
    free_top, free_bot = y, bar_y - 40 * S
    y = max(free_top, free_top + (free_bot - free_top - block) / 2 - 30 * S)
    for ln in lines:
        draw.text((pad + 5 * S, y + 6 * S), ln, font=pf, fill=_darker(deep, 0.6))
        draw.text((pad, y), ln, font=pf, fill=(255, 255, 255))
        y += pf.size * 1.02
    if offer.when:
        wf, wl = _offer_fit(offer.when.upper(), 40 * S, text_w - 70 * S, 1, 900, 24 * S)
        tw = wf.getlength(wl[0])
        tag = Image.new("RGBA", (int(tw + 70 * S), 84 * S), (0, 0, 0, 0))
        td = ImageDraw.Draw(tag)
        td.rounded_rectangle([0, 0, tag.width - 1, tag.height - 1], radius=14 * S, fill=(255, 255, 255))
        td.text((tag.width / 2, tag.height / 2), wl[0], font=wf, fill=c1, anchor="mm")
        tag = tag.rotate(4, expand=True, resample=Image.BICUBIC)
        img.paste(tag, (pad - 6 * S, int(y + 30 * S)), tag)
        draw = ImageDraw.Draw(img)

    # Foto del producto en tarjeta blanca (derecha).
    if pic:
        px, py = W - pad - pic.width, 130 * S
        card = (px - 12 * S, py - 12 * S, px + pic.width + 12 * S, py + pic.height + 12 * S)
        _paste_shadow(img, card, 34 * S, S)
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle(card, radius=34 * S, fill=(255, 255, 255))
        rp = _rounded(pic, 26 * S)
        img.paste(rp, (px, py), rp)
        draw = ImageDraw.Draw(img)

    # Estrella con el precio: grande sola, o más chica sobre la esquina de la foto.
    if big:
        if pic:
            cx, cy, ro = W - pad - pic.width / 2, 130 * S + pic.height + 90 * S, 165 * S
        else:
            cx, cy, ro = 790 * S, (free_top + free_bot) / 2, 255 * S
        sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(sh).polygon(_star(cx + 14 * S, cy + 20 * S, ro, ro * 0.86), fill=(0, 0, 0, 120))
        sh = sh.filter(ImageFilter.GaussianBlur(18 * S))
        img.paste(sh, (0, 0), sh)
        draw = ImageDraw.Draw(img)
        draw.polygon(_star(cx, cy, ro, ro * 0.86), fill=accent)
        draw.ellipse([cx - ro * 0.74, cy - ro * 0.74, cx + ro * 0.74, cy + ro * 0.74],
                     outline=_darker(accent, 0.85), width=4 * S)
        price_col = _darker(c1, 0.75) if sum(accent) > 400 else (255, 255, 255)
        k = ro / (255 * S)
        if offer.old_price and offer.price:
            of = _offer_font(int(40 * S * k), 700)
            t = f"Antes {offer.old_price}"
            oy = cy - 112 * S * k
            draw.text((cx, oy), t, font=of, fill=price_col, anchor="mm")
            tw = of.getlength(t)
            draw.line([(cx - tw / 2 - 6 * S, oy + 4 * S), (cx + tw / 2 + 6 * S, oy - 4 * S)],
                      fill=price_col, width=max(3, int(5 * S * k)))
        prf, _ = _offer_fit(big, int(170 * S * k), int(330 * S * k), 1, 900, 40 * S)
        draw.text((cx, cy + 10 * S * k), big, font=prf, fill=price_col, anchor="mm")
        if offer.price_note and offer.price:
            nf, nl = _offer_fit(offer.price_note.upper(), int(30 * S * k), int(300 * S * k), 1, 800, 16 * S)
            draw.text((cx, cy + 120 * S * k), nl[0], font=nf, fill=price_col, anchor="mm")

    # Barra de abajo: la acción y cómo comprar (datos reales del negocio).
    draw.rectangle([0, bar_y, W, H], fill=(255, 255, 255))
    draw.rectangle([0, bar_y, W, bar_y + 10 * S], fill=accent if sum(accent) < 700 else c2)
    info = [t for t in (offer.delivery, offer.contact) if t] or ([offer.sub] if offer.sub else [])
    text_max = W - pad * 2 - 130 * S
    cf, cl = _offer_fit((offer.cta or "Escríbenos hoy").upper(), 44 * S, text_max, 1, 900, 26 * S)
    cta_y = bar_y + (62 if info else 105) * S
    draw.text((pad, cta_y), cl[0], font=cf, fill=c1, anchor="lm")
    iy = cta_y + 56 * S
    for t in info[:2]:
        f, tl = _offer_fit(t, 28 * S, text_max, 1, 600, 18 * S)
        draw.text((pad, iy), tl[0], font=f, fill=(80, 80, 80), anchor="lm")
        iy += 40 * S
    # Flecha (no ▶: en WhatsApp parece video y la gente lo toca).
    ax, ay = W - pad - 50 * S, bar_y + 105 * S
    draw.ellipse([ax - 50 * S, ay - 50 * S, ax + 50 * S, ay + 50 * S], fill=c1)
    draw.line([(ax - 22 * S, ay), (ax + 18 * S, ay)], fill=(255, 255, 255), width=9 * S)
    draw.polygon([(ax + 26 * S, ay), (ax + 4 * S, ay - 20 * S), (ax + 4 * S, ay + 20 * S)], fill=(255, 255, 255))

    img = img.resize((size, size), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ── Foto real del producto con la promo encima (campaña que pregunta) ──────────

def photo_banner_png(photo: bytes, headline: str, price: str = "", business_name: str = "") -> bytes:
    """La foto del producto del dueño, cuadrada, con una franja abajo con la
    promo y el precio. Nada inventado: la foto es la suya y el texto sale de
    su catálogo (spec docs/specs/2026-10-29-campana-que-pregunta.md)."""
    size = 1080
    img = Image.open(io.BytesIO(photo)).convert("RGB")
    side = min(img.size)
    left, top = (img.width - side) // 2, (img.height - side) // 2
    img = img.crop((left, top, left + side, top + side)).resize((size, size))

    band_h = 330 if price else 260
    overlay = Image.new("RGBA", (size, band_h), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for y in range(band_h):  # degradado: transparente arriba, oscuro abajo
        od.line([(0, y), (size, y)], fill=(0, 0, 0, int(40 + 190 * y / band_h)))
    img.paste(overlay, (0, size - band_h), overlay)

    draw = ImageDraw.Draw(img)
    font = _load_font(_FONT_BOLD, 64)
    lines = _wrap_text(headline.strip(), font, size - 120)[:3]
    y = size - band_h + 40
    for line in lines:
        draw.text((60, y), line, font=font, fill=(255, 255, 255))
        y += 76
    if price:
        pf = _load_font(_FONT_BOLD, 72)
        bbox = draw.textbbox((0, 0), price, font=pf)
        pw, ph = bbox[2] - bbox[0] + 48, bbox[3] - bbox[1] + 36
        _draw_rounded_rect(draw, (60, y + 6, 60 + pw, y + 6 + ph), 20, (230, 57, 70))
        draw.text((84, y + 14), price, font=pf, fill=(255, 255, 255))
    if business_name:
        bf = _load_font(_FONT_REGULAR, 34)
        bbox = draw.textbbox((0, 0), business_name, font=bf)
        draw.text((size - 60 - (bbox[2] - bbox[0]), size - 60), business_name, font=bf, fill=(230, 230, 230))

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return buf.getvalue()
