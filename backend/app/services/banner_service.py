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


# ── Cartel de oferta (Copiloto; con foto del producto o sin foto) ────────────
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
                 contact: str = ""):
        self.contact = contact  # "WhatsApp 953 172 4341": lo pone el sistema, nunca la IA
        self.product = product
        self.price = price
        self.old_price = old_price
        self.when = when
        self.price_note = price_note
        self.sub = sub
        self.cta = cta
        self.business_name = business_name


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
    if target is None or target < send_day:
        return when  # nunca dibujar una fecha que ya pasó cuando llegue el mensaje
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


_DAY_WORDS = r"(?:pasado\s+mañana|mañana|hoy|lunes|martes|miércoles|miercoles|jueves|viernes|sábado|sabado|domingo|fin\s+de\s+semana)"
_WHEN_RE = re.compile(
    rf"(?<!\bla )(?<!\blas )(?<!\bpor )\b(?:(?:solo|sólo|únicamente|unicamente|hasta|desde|de|este|esta|todo\s+el|todos\s+los)\s+)*(?:el\s+|los\s+)?{_DAY_WORDS}\b"
    rf"(?:\s+(?:y|a|al)\s+(?:el\s+)?{_DAY_WORDS}\b)?",
    re.IGNORECASE,
)
_DEAL_RE = re.compile(r"\b(\d+\s*x\s*\d+|\d+\s*%|\d+\s+por(?=\s*\$))", re.IGNORECASE)
_FILLER_RE = re.compile(r"\b(?:a|en|por|de|del|con|solo|sólo|baja|bajan|bajó|llega|llegan|nuevo|precio)\b",
                        re.IGNORECASE)


def _strip_when(product: str, when: str) -> str:
    """Quita del nombre la fecha y las palabras sueltas que quedan ("a", "de")."""
    if when:
        product = re.sub(re.escape(when), " ", product, flags=re.IGNORECASE)
    product = _WHEN_RE.sub(" ", product)
    words = product.split()
    while words and _FILLER_RE.fullmatch(words[-1]):
        words.pop()
    while words and _FILLER_RE.fullmatch(words[0]):
        words.pop(0)
    return " ".join(words).strip(" .,:;-!¡")


def _offer_from_text(promo: str, business_name: str) -> OfferCopy:
    """Sin IA (la cadena gratis no contestó): se separa a mano el precio ($…,
    el último es el de ahora), la fecha ("solo mañana") y la oferta ("2x1")."""
    prices = _prices_in(promo)
    m = _WHEN_RE.search(promo)
    when = m.group(0).strip() if m else ""
    deal = _DEAL_RE.search(promo)
    note = deal.group(1).lower() if deal else ""
    if "por" not in note:
        note = re.sub(r"\s+", "", note)  # "2 x 1" → "2x1"
    rest = _PRICE_RE.sub(" ", promo)
    if deal:
        rest = rest.replace(deal.group(1), " ")
    product = _strip_when(rest, when)
    product = product[:1].upper() + product[1:]
    return OfferCopy(
        product=product[:40] or promo[:40], price=prices[-1] if prices else "",
        old_price=prices[0] if len(prices) > 1 else "", when=when[:1].upper() + when[1:],
        price_note=note, cta="Escríbenos hoy", business_name=business_name,
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
    when = when or fallback.when
    # La fecha va en su cinta, no pegada al nombre ("Cargador marca a solo mañana").
    product = _strip_when(product, when) or fallback.product
    sub = field("sub", 60)
    # La frase de abajo no repite la promo (ya está en grande arriba).
    if _PRICE_RE.search(sub) or (product and product.lower() in sub.lower()):
        sub = ""
    return OfferCopy(
        product=product, price=price, old_price=old, when=when, price_note=note,
        sub=sub, cta=field("cta", 28) or "Escríbenos hoy", business_name=business_name,
    )


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


def _soft(img: Image.Image, box: tuple, blur: float, draw_fn) -> None:
    """Sombra difuminada solo en el pedazo que la necesita (difuminar el
    cartel completo de 2160 px tardaba ~1 s por sombra)."""
    m = int(blur * 3) + 2
    x0, y0 = max(0, int(box[0]) - m), max(0, int(box[1]) - m)
    x1, y1 = min(img.width, int(box[2]) + m), min(img.height, int(box[3]) + m)
    if x1 <= x0 or y1 <= y0:
        return
    lay = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(lay), -x0, -y0)
    lay = lay.filter(ImageFilter.GaussianBlur(blur))
    img.paste(lay, (x0, y0), lay)


def _paste_shadow(img: Image.Image, box: tuple, radius: int, S: int, round_: bool = False) -> None:
    x0, y0, x1, y1 = box[0] + 10 * S, box[1] + 18 * S, box[2] + 10 * S, box[3] + 18 * S

    def draw(d, dx, dy):
        b = [x0 + dx, y0 + dy, x1 + dx, y1 + dy]
        if round_:
            d.ellipse(b, fill=(0, 0, 0, 120))
        else:
            d.rounded_rectangle(b, radius=radius, fill=(0, 0, 0, 110))

    _soft(img, (x0, y0, x1, y1), 18 * S, draw)


def _ink(color: tuple) -> tuple:
    """Letra que se lee sobre ese color: oscura sobre claros, blanca sobre oscuros."""
    r, g, b = color[:3]
    return (25, 25, 25) if (0.299 * r + 0.587 * g + 0.114 * b) > 165 else (255, 255, 255)


def _shadow_text(img: Image.Image, xy: tuple, text: str, font, fill, anchor: str, S: int,
                 strength: int = 150) -> None:
    """Texto con sombra suave para que se lea sobre foto o degradado."""
    sx, sy = xy[0] + 3 * S, xy[1] + 5 * S
    box = ImageDraw.Draw(img).textbbox((sx, sy), text, font=font, anchor=anchor)
    _soft(img, box, 8 * S, lambda d, dx, dy: d.text((sx + dx, sy + dy), text, font=font,
                                                    fill=(0, 0, 0, strength), anchor=anchor))
    ImageDraw.Draw(img).text(xy, text, font=font, fill=fill, anchor=anchor)


def _struck(draw: ImageDraw.ImageDraw, xy: tuple, text: str, font, fill, S: int) -> None:
    """"Antes $120" centrado y tachado."""
    draw.text(xy, text, font=font, fill=fill, anchor="mm")
    w = font.getlength(text)
    x, y = xy
    draw.line([(x - w / 2 - 6 * S, y + 6 * S), (x + w / 2 + 6 * S, y - 6 * S)], fill=fill, width=6 * S)


def _pill(img: Image.Image, center: tuple, text: str, size: int, max_w: int, fill, S: int,
          anchor_left: bool = False, anchor_right: bool = False) -> tuple:
    """Cinta redondeada con texto (la fecha, o el nombre del negocio). Regresa su caja."""
    f, lines = _offer_fit(text, size, max_w - 60 * S, 1, 850, 44 * S)
    t = " ".join(lines) if f.getlength(" ".join(lines)) <= max_w - 60 * S else (lines[0] if lines else text)
    w, h = f.getlength(t) + 60 * S, f.size + 34 * S
    x0 = center[0] if anchor_left else center[0] - w if anchor_right else center[0] - w / 2
    y0 = center[1] - h / 2
    box = (x0, y0, x0 + w, y0 + h)
    _paste_shadow(img, box, int(h / 2), S // 2 or 1)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(box, radius=int(h / 2), fill=fill)
    d.text((x0 + w / 2, y0 + h / 2), t, font=f, fill=_ink(fill), anchor="mm")
    return box


def _header(img: Image.Image, offer: "OfferCopy", logo: bytes | None, c1: tuple, S: int, pad: int) -> None:
    """Arriba a la izquierda: el logo en un círculo, o el nombre en una cinta
    blanca. Arriba a la derecha: el teléfono, para que el cartel sirva aunque
    se reenvíe o se suba a estados sin el texto que lo acompaña."""
    W_ = img.width
    name_w = W_ - 2 * pad
    if offer.contact:
        box = _pill(img, (W_ - pad, pad + 40 * S), offer.contact, 44 * S, W_ - 2 * pad - 200 * S,
                    (255, 255, 255), S, anchor_right=True)
        name_w = int(box[0] - pad - 20 * S)
    logo_img = _square(logo, 128 * S)
    if logo_img:
        ring = 140 * S
        _paste_shadow(img, (pad, pad, pad + ring, pad + ring), 0, S // 2 or 1, round_=True)
        d = ImageDraw.Draw(img)
        d.ellipse([pad, pad, pad + ring, pad + ring], fill=(255, 255, 255))
        m = Image.new("L", logo_img.size, 0)
        ImageDraw.Draw(m).ellipse([0, 0, logo_img.width - 1, logo_img.height - 1], fill=255)
        img.paste(logo_img, (pad + 6 * S, pad + 6 * S), m)
    elif offer.business_name:
        # Lo que quepa junto al teléfono ("REFACCIONARIA Y FERRETERÍA…" →
        # "REFACCIONARIA Y"); si ni una palabra cabe, va solo el teléfono.
        f = _offer_font(44 * S, 850)
        words = offer.business_name.upper().split()
        while words and f.getlength(" ".join(words)) > name_w - 60 * S:
            words.pop()
        if words and words[-1] in {"Y", "DE", "DEL", "LA", "EL", "LOS", "LAS", "E"}:
            words.pop()
        if words:
            _pill(img, (pad, pad + 40 * S), " ".join(words), 44 * S, name_w, (255, 255, 255), S,
                  anchor_left=True)


def _note_fits_seal(note: str, R: float, S: int) -> bool:
    """"3 TACOS" cabe en el sello; "2 HAMBURGUESAS" no (quedaría solo "2")."""
    return _offer_font(44 * S, 800).getlength(note.upper()) <= (R - 12 * S) * 1.3


def _seal(img: Image.Image, cx: float, cy: float, R: float, offer: "OfferCopy", big: str,
          accent: tuple, S: int) -> None:
    """Sello redondo con el precio (y el de antes tachado)."""
    sb = (cx - R + 8 * S, cy - R + 16 * S, cx + R + 8 * S, cy + R + 16 * S)
    _soft(img, sb, 16 * S, lambda d, dx, dy: d.ellipse([sb[0] + dx, sb[1] + dy, sb[2] + dx, sb[3] + dy],
                                                        fill=(0, 0, 0, 130)))
    d = ImageDraw.Draw(img)
    d.ellipse([cx - R, cy - R, cx + R, cy + R], fill=(255, 255, 255))
    r = R - 12 * S
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=accent)
    ink = _ink(accent)
    has_old = bool(offer.old_price and offer.price)
    has_note = bool(offer.price_note and offer.price) and _note_fits_seal(offer.price_note, R, S)
    py = cy + (16 if has_old else 0) * S - (22 if has_note else 0) * S
    pf, _ = _offer_fit(big, int(R * 0.78), int(r * 1.62), 1, 900, 60 * S)
    d.text((cx, py), big, font=pf, fill=ink, anchor="mm")
    if has_old:
        of = _offer_font(48 * S, 750)
        # En el sello cabe ~1.4 radios a esa altura; si no, solo el precio tachado.
        t = f"Antes {offer.old_price}"
        if of.getlength(t) > r * 1.4:
            t = offer.old_price
        _struck(d, (cx, py - pf.size * 0.62), t, of, ink, S)
    if has_note:
        nf, nl = _offer_fit(offer.price_note.upper(), 44 * S, int(r * 1.3), 1, 800, 44 * S)
        d.text((cx, py + pf.size * 0.62), nl[0], font=nf, fill=ink, anchor="mm")


# «Otra versión» del cartel: los colores van rotando desde el del giro y, con
# foto, el sello del precio cambia de lado (antes salía idéntico, 12-nov).
_LOOK_PALETTES = ("rojo", "azul", "verde", "morado", "oscuro", "naranja")


def offer_look(palette_name: str, look: int) -> tuple[str, bool]:
    """(paleta, sello a la izquierda) de la versión `look` (0 = la del giro)."""
    order = [palette_name] + [p for p in _LOOK_PALETTES if p != palette_name]
    return order[look % len(order)], look % 2 == 1


def offer_banner_png(offer: OfferCopy, palette_name: str = "promo", photo: bytes | None = None,
                     logo: bytes | None = None, seal_left: bool = False) -> bytes:
    """Cartel de oferta 1080×1080 (spec docs/specs/2026-11-12-cartel-que-convence.md).
    Con foto: la foto ocupa todo, abajo el producto y la fecha sobre un
    degradado, y el sello con el precio. Sin foto: el precio enorme al centro
    sobre un degradado liso del color del giro. Solo lo esencial y nada más
    chico que 44 px, para que se lea a 300 px en WhatsApp."""
    c1, c2, accent = PALETTES.get(palette_name, PALETTES["promo"])
    S, size = 2, 1080
    W = H = size * S
    pad = 64 * S
    big = offer.price or (offer.price_note if len(offer.price_note) <= 6 else "")
    pic = _square(photo, W)

    if pic:
        img = pic
        # Degradado abajo (para el texto) y uno leve arriba (para el logo).
        fade = Image.new("L", (1, H), 0)
        for y in range(H):
            t = y / H
            a = 235 * max(0.0, (t - 0.42) / 0.58) ** 1.3 + 110 * max(0.0, (0.2 - t) / 0.2)
            fade.putpixel((0, y), int(min(235, a)))
        fade = fade.resize((W, H))
        img = Image.composite(Image.new("RGB", (W, H), _darker(c1, 0.35)), img, fade)
    else:
        # El degradado y el brillo se calculan chicos y se agrandan (son suaves:
        # se ven igual y tarda 0.1 s en vez de 1 s).
        q = W // 4
        g = Image.linear_gradient("L").resize((q * 2, q * 2)).rotate(-35, resample=Image.BICUBIC)
        g = g.crop((q // 2, q // 2, q // 2 + q, q // 2 + q)).resize((W, H), Image.BICUBIC)
        img = Image.composite(Image.new("RGB", (W, H), _darker(c1, 0.55)), Image.new("RGB", (W, H), _darker(c2, 0.9)), g)
        glow = Image.new("L", (q, q), 255)
        # radial_gradient vale 128 en el borde del círculo: ×2 para que llegue a
        # 255 (sin brillo) justo ahí y no quede un escalón.
        disk = Image.radial_gradient("L").point(lambda v: min(255, v * 2))
        glow.paste(disk.resize((int(q * 1.1), int(q * 1.1))), (int(-q * 0.05), int(q * 0.08)))
        glow = glow.point(lambda v: int((255 - v) * 0.2)).resize((W, H), Image.BICUBIC)
        img.paste(Image.new("RGB", (W, H), (255, 255, 255)), (0, 0), glow)

    _header(img, offer, logo, c1, S, pad)
    product = (offer.product or "Oferta").upper()
    pill_fill = accent if sum(accent) < 720 else (255, 255, 255)

    if pic:
        # Abajo, de abajo hacia arriba: la fecha a todo lo ancho; encima, el
        # producto a la izquierda y el sello con el precio a la derecha.
        R = 175 * S if big else 0
        y = H - pad
        # Una nota larga ("2 hamburguesas") no cabe en el sello: va en la cinta.
        note_out = bool(R and offer.price and offer.price_note and not _note_fits_seal(offer.price_note, R, S))
        ribbons = [t for t in ((offer.price_note if note_out else ""), offer.when) if t]
        joined = " · ".join(ribbons).upper()
        if len(ribbons) > 1 and _offer_font(44 * S, 850).getlength(joined) <= W - 2 * pad - 60 * S:
            ribbons = [joined]  # caben juntas en una sola cinta
        for t in reversed(ribbons):  # si no, una encima de otra (la fecha abajo)
            box = _pill(img, (pad, y - 40 * S), t.upper(), 46 * S, W - 2 * pad, pill_fill, S, anchor_left=True)
            y = box[1] - 18 * S
        if ribbons:
            y -= 8 * S
        col_w = W - 2 * pad - (2 * R + 30 * S if R else 0)
        pf, lines = _offer_fit(product, 96 * S, col_w, 3, 900, 48 * S)
        if R:
            _seal(img, pad + R if seal_left else W - pad - R, y - R, R, offer, big, accent, S)
        # Con el sello a la izquierda, el producto se alinea a la derecha.
        tx, anchor = (W - pad, "rs") if seal_left and R else (pad, "ls")
        for ln in reversed(lines):
            _shadow_text(img, (tx, y), ln, pf, (255, 255, 255), anchor, S)
            y -= pf.size * 1.02
    else:
        top = pad + 170 * S
        if big:
            pf, lines = _offer_fit(product, 92 * S, W - 2 * pad, 2, 900, 48 * S)
            y = top
            for ln in lines:
                _shadow_text(img, (W / 2, y), ln, pf, (255, 255, 255), "mt", S)
                y += pf.size * 1.04
            mid = (y + (H - pad - 120 * S)) / 2
            has_old = bool(offer.old_price and offer.price)
            has_note = bool(offer.price_note and offer.price)
            bf, _ = _offer_fit(big, 300 * S, W - 2 * pad, 1, 900, 120 * S)
            py = mid + (30 if has_old else 0) * S - (30 if has_note else 0) * S
            _shadow_text(img, (W / 2, py), big, bf, (255, 255, 255), "mm", S, 170)
            d = ImageDraw.Draw(img)
            if has_old:
                _struck(d, (W / 2, py - bf.size * 0.6), f"Antes {offer.old_price}", _offer_font(56 * S, 750),
                        (255, 255, 255), S)
            if has_note:
                nf, nl = _offer_fit(offer.price_note.upper(), 52 * S, W - 2 * pad, 1, 800, 44 * S)
                d.text((W / 2, py + bf.size * 0.62), nl[0], font=nf, fill=(255, 255, 255), anchor="mm")
        else:
            pf, lines = _offer_fit(product, 150 * S, W - 2 * pad, 3, 900, 60 * S)
            block = len(lines) * pf.size * 1.04
            y = (H - block) / 2 - 20 * S
            for ln in lines:
                _shadow_text(img, (W / 2, y), ln, pf, (255, 255, 255), "mt", S, 170)
                y += pf.size * 1.04
        if offer.when:
            _pill(img, (W / 2, H - pad - 40 * S), offer.when.upper(), 50 * S, W - 2 * pad, pill_fill, S)

    img = img.resize((size, size), Image.LANCZOS)
    buf = io.BytesIO()
    # JPEG: con foto pesa ~1/4 que PNG (datos del cliente) y se guarda en
    # 0.1 s en vez de 2 s. 4:4:4 para que el texto rojo no se vea borroso.
    img.save(buf, format="JPEG", quality=90, subsampling=0, optimize=True)
    return buf.getvalue()
