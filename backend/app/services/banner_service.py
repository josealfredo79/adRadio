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
    "restaurante":   {"layout": "clasico",  "palette": "naranja",  "vibe": "calido"},
    "comida":        {"layout": "ticker",   "palette": "naranja",  "vibe": "urgente"},
    "bar":           {"layout": "neon",     "palette": "oscuro",   "vibe": "nocturno"},
    "salon":         {"layout": "centrado", "palette": "elegante", "vibe": "elegante"},
    "belleza":       {"layout": "centrado", "palette": "morado",   "vibe": "moderno"},
    "spa":           {"layout": "arco",     "palette": "helado",   "vibe": "calma"},
    "salud":         {"layout": "arco",     "palette": "azul",     "vibe": "confianza"},
    "farmacia":      {"layout": "arco",     "palette": "verde",    "vibe": "confianza"},
    "fitness":       {"layout": "split",    "palette": "naranja",  "vibe": "energico"},
    "tienda":        {"layout": "ticker",   "palette": "promo",    "vibe": "urgente"},
    "supermercado":  {"layout": "ticker",   "palette": "verde",    "vibe": "urgente"},
    "ropa":          {"layout": "centrado", "palette": "elegante", "vibe": "moderno"},
    "electronica":   {"layout": "split",    "palette": "azul",     "vibe": "tecnologico"},
    "servicios":     {"layout": "clasico",  "palette": "azul",     "vibe": "profesional"},
    "inmobiliaria":  {"layout": "minimal",  "palette": "elegante", "vibe": "exclusivo"},
    "automotriz":    {"layout": "split",    "palette": "rojo",     "vibe": "potente"},
    "educacion":     {"layout": "centrado", "palette": "azul",     "vibe": "confiable"},
    "tecnologia":    {"layout": "split",    "palette": "azul",     "vibe": "innovador"},
    "financiero":    {"layout": "minimal",  "palette": "elegante", "vibe": "serio"},
    "eventos":       {"layout": "centrado", "palette": "morado",   "vibe": "festivo"},
    "club":          {"layout": "neon",     "palette": "morado",   "vibe": "nocturno"},
    "entretenimiento":{"layout": "neon",    "palette": "rojo",     "vibe": "emocionante"},
    "viajes":        {"layout": "split",    "palette": "azul",     "vibe": "aventura"},
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
    greeting = f"¡Hola, {copy.contact_name}!"
    # greeting en accent; si accent es muy claro usar blanco
    greet_color = accent if sum(accent) < 600 else (255, 255, 255)
    draw.text((pad, 46), greeting, font=font_greeting, fill=greet_color)

    shadow_color = tuple(max(0, c - 40) for c in c1)  # sombra: tono más oscuro del fondo
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
    greeting = f"¡Hola, {copy.contact_name}!"
    draw.text((pad, 46), greeting, font=font_greeting, fill=(*accent, 200))

    # Headline grande — zona oscura (arriba-derecha)
    shadow_diag = tuple(max(0, c - 40) for c in c1)
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
    font_biz = _load_font(_FONT_BOLD, 22)
    font_cta = _load_font(_FONT_BOLD, 30)

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

    greeting = f"¡Hola, {copy.contact_name}!"
    draw.text((rx, 50), greeting, font=font_greeting, fill=(*accent, 190))

    shadow_sp = tuple(max(0, c - 40) for c in c1)
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
    greeting = f"Hola, {copy.contact_name}."
    draw.text((pad, band_h // 2 - 40), greeting, font=font_greeting, fill=txt_band)
    draw.text((pad, band_h // 2 + 4), copy.business_name.upper(), font=font_biz, fill=(*c1, 180) if sum(accent) > 400 else (255, 255, 255, 200))

    # Año / badge decorativo en la esquina derecha de la banda
    badge_font = _load_font(_FONT_BOLD, 26)
    draw.text((BANNER_W - 90, band_h // 2 - 14), ">>>", font=badge_font, fill=txt_band)

    # CUERPO: headline grande
    shadow_ed = tuple(max(0, c - 50) for c in c1)
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
    draw.text((pad, 50), f"¡Hola, {copy.contact_name}!", font=font_greeting, fill=greet_col)

    # Headline extra grande en zona oscura
    shadow = tuple(max(0, c - 30) for c in c1)
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
    draw.text((cx - 46, cy), ">>", font=font_cta, fill=txt_tk)
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
    draw.text((pad, 48), f"¡Hola, {copy.contact_name}!", font=font_greeting, fill=accent)

    # Headline con efecto glow: 8 trazos desplazados en color brillante + texto blanco encima
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
    for y in range(0, min(210, BANNER_H)):
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
    greeting = f"Hola, {copy.contact_name}."
    g_bbox = draw.textbbox((0, 0), greeting, font=font_greeting)
    g_x = (BANNER_W - (g_bbox[2] - g_bbox[0])) // 2
    draw.text((g_x, 36), greeting, font=font_greeting, fill=txt_arch)

    # Headline centrado debajo del arco
    shadow = tuple(max(0, c - 40) for c in c1)
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
