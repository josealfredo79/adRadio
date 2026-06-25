"""
Banner visual service — genera imágenes PNG personalizadas por contacto.

Pipeline:
  1. Claude genera el copy del anuncio (headline + subheadline + CTA)
  2. Según categoría del negocio y tipo de campaña, se selecciona layout y paleta
  3. Pillow renderiza el banner con variaciones por contacto
  4. Se retorna bytes PNG listo para subir a R2
"""
import io
import logging
import random

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# ── Fuentes del sistema ───────────────────────────────────────────────────────
_FONT_BOLD = "/usr/share/fonts/truetype/ubuntu/UbuntuSans[wdth,wght].ttf"
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
    "restaurante":  {"layout": "clasico",  "palette": "naranja", "vibe": "calido"},
    "comida":       {"layout": "clasico",  "palette": "naranja", "vibe": "calido"},
    "bar":          {"layout": "clasico",  "palette": "oscuro",  "vibe": "nocturno"},
    "salon":        {"layout": "centrado", "palette": "elegante","vibe": "elegante"},
    "belleza":      {"layout": "centrado", "palette": "morado",  "vibe": "moderno"},
    "spa":          {"layout": "minimal",  "palette": "helado",  "vibe": "calma"},
    "salud":        {"layout": "minimal",  "palette": "azul",    "vibe": "confianza"},
    "fitness":      {"layout": "split",    "palette": "naranja", "vibe": "energico"},
    "tienda":       {"layout": "clasico",  "palette": "promo",   "vibe": "urgente"},
    "ropa":         {"layout": "centrado", "palette": "elegante","vibe": "moderno"},
    "electronica":  {"layout": "split",    "palette": "azul",    "vibe": "tecnologico"},
    "servicios":    {"layout": "clasico",  "palette": "azul",    "vibe": "profesional"},
    "inmobiliaria": {"layout": "minimal",  "palette": "elegante","vibe": "exclusivo"},
    "automotriz":   {"layout": "split",    "palette": "rojo",    "vibe": "potente"},
    "educacion":    {"layout": "centrado", "palette": "azul",    "vibe": "confiable"},
    "tecnologia":   {"layout": "split",    "palette": "azul",    "vibe": "innovador"},
    "financiero":   {"layout": "minimal",  "palette": "elegante","vibe": "serio"},
    "eventos":      {"layout": "centrado", "palette": "morado",  "vibe": "festivo"},
    "viajes":       {"layout": "split",    "palette": "azul",    "vibe": "aventura"},
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
        logger.warning("[BANNER] Failed to load font %s", path, exc_info=True)
        return ImageFont.load_default()


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
    """Layout clásico: greeting + headline a la izquierda, CTA inferior."""
    pad = 60
    font_greeting = _load_font(_FONT_BOLD, 38)
    font_headline = _load_font(_FONT_BOLD, 68)
    font_sub = _load_font(_FONT_REGULAR, 34)
    font_biz = _load_font(_FONT_BOLD, 28)
    font_cta = _load_font(_FONT_BOLD, 30)

    draw.rectangle([0, 0, BANNER_W, 8], fill=accent)

    greeting = f"¡Hola, {copy.contact_name}!"
    draw.text((42, 62), greeting, font=font_greeting, fill=(0, 0, 0, 80))
    draw.text((40, 60), greeting, font=font_greeting, fill=(*accent, 255))

    draw.rectangle([40, 108, 200, 112], fill=(*accent, 200))

    lines = _wrap_text(copy.headline.upper(), font_headline, BANNER_W - pad * 2)
    y_cursor = 140
    for line in lines[:3]:
        draw.text((pad + 2, y_cursor + 2), line, font=font_headline, fill=(0, 0, 0, 60))
        draw.text((pad, y_cursor), line, font=font_headline, fill=(255, 255, 255))
        bbox = draw.textbbox((0, 0), line, font=font_headline)
        y_cursor += bbox[3] - bbox[1] + 12

    y_cursor += 16
    sub_lines = _wrap_text(copy.subheadline, font_sub, BANNER_W - pad * 2)
    for line in sub_lines[:3]:
        draw.text((pad, y_cursor), line, font=font_sub, fill=(220, 220, 220))
        bbox = draw.textbbox((0, 0), line, font=font_sub)
        y_cursor += bbox[3] - bbox[1] + 8

    draw.text((pad, BANNER_H - 120), copy.business_name.upper(), font=font_biz, fill=(*accent, 255))

    cta_bbox = draw.textbbox((0, 0), copy.cta, font=font_cta)
    cta_w = cta_bbox[2] - cta_bbox[0]
    cta_h = cta_bbox[3] - cta_bbox[1]
    btn_pad_x, btn_pad_y = 28, 14
    btn_x0 = pad
    btn_y0 = BANNER_H - 80
    btn_x1 = btn_x0 + cta_w + btn_pad_x * 2
    btn_y1 = btn_y0 + cta_h + btn_pad_y * 2
    _draw_rounded_rect(draw, (btn_x0, btn_y0, btn_x1, btn_y1), 12, accent)
    txt_color = c1 if sum(accent) > 380 else (255, 255, 255)
    draw.text((btn_x0 + btn_pad_x, btn_y0 + btn_pad_y), copy.cta, font=font_cta, fill=txt_color)

    draw.rectangle([0, BANNER_H - 6, BANNER_W, BANNER_H], fill=accent)


def _render_centrado(draw: ImageDraw.ImageDraw, copy: BannerCopy, c1: tuple, c2: tuple, accent: tuple, rng: random.Random) -> None:
    """Layout centrado: todo centrado horizontalmente, moderno y limpio."""
    font_greeting = _load_font(_FONT_REGULAR, 32)
    font_headline = _load_font(_FONT_BOLD, 72)
    font_sub = _load_font(_FONT_REGULAR, 32)
    font_biz = _load_font(_FONT_BOLD, 26)
    font_cta = _load_font(_FONT_BOLD, 32)
    pad = 60

    draw.rectangle([0, 0, BANNER_W, 6], fill=accent)
    draw.rectangle([0, BANNER_H - 6, BANNER_W, BANNER_H], fill=accent)

    greeting = f"¡Hola, {copy.contact_name}!"
    g_bbox = draw.textbbox((0, 0), greeting, font=font_greeting)
    g_x = (BANNER_W - (g_bbox[2] - g_bbox[0])) // 2
    draw.text((g_x + 1, 41), greeting, font=font_greeting, fill=(0, 0, 0, 60))
    draw.text((g_x, 40), greeting, font=font_greeting, fill=(255, 255, 255))

    lines = _wrap_text(copy.headline.upper(), font_headline, BANNER_W - pad * 4)
    y_cursor = 140
    for line in lines[:2]:
        l_bbox = draw.textbbox((0, 0), line, font=font_headline)
        l_x = (BANNER_W - (l_bbox[2] - l_bbox[0])) // 2
        draw.text((l_x + 2, y_cursor + 2), line, font=font_headline, fill=(0, 0, 0, 60))
        draw.text((l_x, y_cursor), line, font=font_headline, fill=(255, 255, 255))
        bbox = draw.textbbox((0, 0), line, font=font_headline)
        y_cursor += bbox[3] - bbox[1] + 14

    y_cursor += 20
    sub_lines = _wrap_text(copy.subheadline, font_sub, BANNER_W - pad * 3)
    for line in sub_lines[:2]:
        s_bbox = draw.textbbox((0, 0), line, font=font_sub)
        s_x = (BANNER_W - (s_bbox[2] - s_bbox[0])) // 2
        draw.text((s_x, y_cursor), line, font=font_sub, fill=(200, 200, 200))
        bbox = draw.textbbox((0, 0), line, font=font_sub)
        y_cursor += bbox[3] - bbox[1] + 8

    cta_bbox = draw.textbbox((0, 0), copy.cta, font=font_cta)
    cta_w = cta_bbox[2] - cta_bbox[0]
    cta_h = cta_bbox[3] - cta_bbox[1]
    btn_pad_x, btn_pad_y = 32, 16
    btn_w = cta_w + btn_pad_x * 2
    btn_h = cta_h + btn_pad_y * 2
    btn_x0 = (BANNER_W - btn_w) // 2
    btn_y0 = BANNER_H - 160
    _draw_rounded_rect(draw, (btn_x0, btn_y0, btn_x0 + btn_w, btn_y0 + btn_h), 16, accent)
    txt_color = c1 if sum(accent) > 380 else (255, 255, 255)
    draw.text((btn_x0 + btn_pad_x, btn_y0 + btn_pad_y), copy.cta, font=font_cta, fill=txt_color)

    biz_bbox = draw.textbbox((0, 0), copy.business_name.upper(), font=font_biz)
    biz_x = (BANNER_W - (biz_bbox[2] - biz_bbox[0])) // 2
    draw.text((biz_x, BANNER_H - 80), copy.business_name.upper(), font=font_biz, fill=(*accent, 200))


def _render_split(draw: ImageDraw.ImageDraw, copy: BannerCopy, c1: tuple, c2: tuple, accent: tuple, rng: random.Random) -> None:
    """Layout split: mitad superior e inferior con colores distintos."""
    font_greeting = _load_font(_FONT_BOLD, 34)
    font_headline = _load_font(_FONT_BOLD, 74)
    font_sub = _load_font(_FONT_REGULAR, 30)
    font_biz = _load_font(_FONT_BOLD, 24)
    font_cta = _load_font(_FONT_BOLD, 30)
    pad = 60

    mid_y = BANNER_H // 2
    for y in range(mid_y):
        t = y / mid_y
        r = int(c1[0] + (accent[0] - c1[0]) * t)
        g = int(c1[1] + (accent[1] - c1[1]) * t)
        b = int(c1[2] + (accent[2] - c1[2]) * t)
        draw.line([(0, y), (BANNER_W, y)], fill=(r, g, b))
    for y in range(mid_y, BANNER_H):
        t = (y - mid_y) / mid_y
        r = int(accent[0] + (c2[0] - accent[0]) * t)
        g = int(accent[1] + (c2[1] - accent[1]) * t)
        b = int(accent[2] + (c2[2] - accent[2]) * t)
        draw.line([(0, y), (BANNER_W, y)], fill=(r, g, b))

    draw.rectangle([0, mid_y - 3, BANNER_W, mid_y + 3], fill=(255, 255, 255, 60))

    greeting = f"¡Hola, {copy.contact_name}!"
    draw.text((42, 52), greeting, font=font_greeting, fill=(0, 0, 0, 60))
    draw.text((40, 50), greeting, font=font_greeting, fill=(255, 255, 255))

    lines = _wrap_text(copy.headline.upper(), font_headline, BANNER_W - pad * 2)
    y_cursor = 130
    for line in lines[:2]:
        draw.text((pad + 2, y_cursor + 2), line, font=font_headline, fill=(0, 0, 0, 60))
        draw.text((pad, y_cursor), line, font=font_headline, fill=(255, 255, 255))
        bbox = draw.textbbox((0, 0), line, font=font_headline)
        y_cursor += bbox[3] - bbox[1] + 10

    biz_y = mid_y + 50
    draw.text((pad, biz_y), copy.business_name.upper(), font=font_biz, fill=(255, 255, 255, 200))

    sub_y = biz_y + 50
    sub_lines = _wrap_text(copy.subheadline, font_sub, BANNER_W - pad * 2)
    for line in sub_lines[:2]:
        draw.text((pad, sub_y), line, font=font_sub, fill=(220, 220, 220))
        bbox = draw.textbbox((0, 0), line, font=font_sub)
        sub_y += bbox[3] - bbox[1] + 6

    cta_bbox = draw.textbbox((0, 0), copy.cta, font=font_cta)
    cta_w = cta_bbox[2] - cta_bbox[0]
    cta_h = cta_bbox[3] - cta_bbox[1]
    btn_pad_x, btn_pad_y = 28, 14
    btn_x0 = pad
    btn_y0 = BANNER_H - 90
    btn_x1 = btn_x0 + cta_w + btn_pad_x * 2
    btn_y1 = btn_y0 + cta_h + btn_pad_y * 2
    _draw_rounded_rect(draw, (btn_x0, btn_y0, btn_x1, btn_y1), 12, accent)
    txt_color = c1 if sum(accent) > 380 else (255, 255, 255)
    draw.text((btn_x0 + btn_pad_x, btn_y0 + btn_pad_y), copy.cta, font=font_cta, fill=txt_color)


def _render_minimal(draw: ImageDraw.ImageDraw, copy: BannerCopy, c1: tuple, c2: tuple, accent: tuple, rng: random.Random) -> None:
    """Layout minimal: mucho espacio, borde sutil, diseño premium."""
    font_greeting = _load_font(_FONT_REGULAR, 28)
    font_headline = _load_font(_FONT_BOLD, 56)
    font_sub = _load_font(_FONT_REGULAR, 28)
    font_biz = _load_font(_FONT_BOLD, 22)
    font_cta = _load_font(_FONT_BOLD, 26)
    pad = 80

    draw.rectangle([15, 15, BANNER_W - 15, BANNER_H - 15], outline=(*accent, 180), width=2)
    draw.rectangle([0, 0, BANNER_W, 4], fill=accent)
    draw.rectangle([0, BANNER_H - 4, BANNER_W, BANNER_H], fill=accent)

    greeting = f"Hola, {copy.contact_name}."
    draw.text((pad, 50), greeting, font=font_greeting, fill=(*accent, 180))

    lines = _wrap_text(copy.headline.upper(), font_headline, BANNER_W - pad * 2)
    y_cursor = 140
    for line in lines[:2]:
        draw.text((pad, y_cursor), line, font=font_headline, fill=(255, 255, 255))
        bbox = draw.textbbox((0, 0), line, font=font_headline)
        y_cursor += bbox[3] - bbox[1] + 10

    draw.rectangle([pad, y_cursor + 10, pad + 60, y_cursor + 12], fill=(*accent, 150))

    y_cursor += 40
    sub_lines = _wrap_text(copy.subheadline, font_sub, BANNER_W - pad * 2)
    for line in sub_lines[:2]:
        draw.text((pad, y_cursor), line, font=font_sub, fill=(180, 180, 180))
        bbox = draw.textbbox((0, 0), line, font=font_sub)
        y_cursor += bbox[3] - bbox[1] + 6

    draw.text((pad, BANNER_H - 120), copy.business_name.upper(), font=font_biz, fill=(*accent, 150))

    cta_bbox = draw.textbbox((0, 0), copy.cta, font=font_cta)
    cta_w = cta_bbox[2] - cta_bbox[0]
    cta_h = cta_bbox[3] - cta_bbox[1]
    btn_pad_x, btn_pad_y = 24, 10
    btn_x0 = pad
    btn_y0 = BANNER_H - 80
    btn_x1 = btn_x0 + cta_w + btn_pad_x * 2
    btn_y1 = btn_y0 + cta_h + btn_pad_y * 2
    draw.rounded_rectangle([btn_x0, btn_y0, btn_x1, btn_y1], radius=20, outline=(*accent, 200), width=2)
    draw.text((btn_x0 + btn_pad_x, btn_y0 + btn_pad_y), copy.cta, font=font_cta, fill=(*accent, 200))


# ── Mapeo de layouts a renderizadores ─────────────────────────────────────────
_RENDERERS = {
    "clasico":  _render_clasico,
    "centrado": _render_centrado,
    "split":    _render_split,
    "minimal":  _render_minimal,
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
        vibe = biz_style["vibe"]
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

    if layout != "split":
        _gradient_background(draw, BANNER_W, BANNER_H, c1, c2)

    if layout in ("clasico",):
        _draw_deco_circles(draw, BANNER_W, BANNER_H, accent, seed)
        if rng.random() < 0.5:
            _draw_particles(draw, BANNER_W, BANNER_H, accent, seed + 1)

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
    """Usa Claude Sonnet para generar el copy del banner, adaptado al negocio y campaña."""
    import json
    from anthropic import AsyncAnthropic
    from app.config import settings

    design = select_design(business_category, campaign_type)
    vibe_tone = VIBE_TONES.get(design.vibe, "Tono profesional y atractivo.")

    client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    prompt = f"""Eres un experto en marketing latinoamericano.
Genera el copy para un banner publicitario de WhatsApp.

Negocio: {business_name}
Contacto: {contact_name}
Promoción: {promo_description}
Estilo: {vibe_tone}

Responde ÚNICAMENTE con un JSON con estas claves (sin texto extra):
{{
  "headline": "Máximo 5 palabras impactantes, alineadas al estilo",
  "subheadline": "1 oración que explica el beneficio, máximo 12 palabras",
  "cta": "Máximo 4 palabras, acción clara (ej: Ver oferta ahora)"
}}"""

    try:
        response = await client.messages.create(
            model=settings.ANTHROPIC_MODEL,
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
