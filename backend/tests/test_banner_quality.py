"""El cartel de colores del Copiloto salía con el título en letra de 10 px
(fuente que no existía en la imagen web) y con "¡Hola, !" sin nombre."""
import io
import json
import os
from itertools import pairwise
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image, ImageFont

from app.services import banner_service as bs


def test_fuentes_existen_en_el_servidor():
    # Las dos vienen en fonts-dejavu-core (Dockerfile y Dockerfile.worker).
    assert os.path.exists(bs._FONT_BOLD)
    assert os.path.exists(bs._FONT_REGULAR)
    assert "dejavu" in bs._FONT_BOLD.lower()
    assert isinstance(bs._load_font(bs._FONT_BOLD, 78), ImageFont.FreeTypeFont)


def test_fuente_faltante_no_sale_diminuta():
    f = bs._load_font("/no/existe.ttf", 60)
    bbox = f.getbbox("CARGADOR")
    assert bbox[3] - bbox[1] > 30


def test_saludo_sin_nombre():
    assert bs._greeting("") == "¡Hola!"
    assert bs._greeting("  ") == "¡Hola!"
    assert bs._greeting("Ana") == "¡Hola, Ana!"
    assert bs._greeting("", formal=True) == "Hola."


def test_titulo_largo_se_achica_y_cabe():
    font = bs._load_font(bs._FONT_BOLD, 78)
    text = "CARGADOR MARCA A $100 SOLO MAÑANA EN TIENDA"
    fitted = bs._fit_font(text, font, 680, 2)
    lines = bs._wrap_text(text, fitted, 680)
    assert len(lines) <= 2
    assert fitted.size < 78


def test_palabra_sola_ancha_se_achica():
    font = bs._load_font(bs._FONT_BOLD, 66)
    fitted = bs._fit_font("CARGADOR", font, 340, 3)
    assert fitted.getlength("CARGADOR") <= 340


def test_todos_los_disenos_generan_png_sin_nombre():
    copy = bs.BannerCopy(headline="Cargador marca a $100", subheadline="Solo mañana",
                         cta="Pídelo aquí", contact_name="", business_name="CityCell")
    for layout in bs._RENDERERS:
        png = bs.generate_banner_png(copy, "rojo", layout)
        assert png[:8] == b"\x89PNG\r\n\x1a\n"


# ── Cartel de oferta (estrella con precio) ───────────────────────────────────
def test_fuente_de_oferta_viene_en_el_repo():
    assert os.path.exists(bs._FONT_OFFER)
    f = bs._offer_font(80, 900)
    assert "Montserrat" in f.getname()[0]


def test_oferta_sin_ia_saca_precios_del_texto():
    o = bs._offer_from_text("Cargador marca de $120 a $100", "CityCell")
    assert o.price == "$100" and o.old_price == "$120"
    o = bs._offer_from_text("2x1 en micas", "CityCell")
    assert o.price == "" and o.product == "Micas" and o.price_note == "2x1"


def test_precio_sin_centavos():
    assert bs._clean_price("$100.00") == "$100"
    assert bs._clean_price("$1500") == "$1,500"


async def _offer(raw: str, promo: str) -> "bs.OfferCopy":
    with patch("app.services.llm_client.chat_completion", AsyncMock(return_value=raw)):
        return await bs.generate_offer_copy("CityCell", promo)


@pytest.mark.asyncio
async def test_ia_separa_la_promo():
    raw = json.dumps({"product": "Cargador marca", "price": "$100.00", "old_price": "$120",
                      "when": "Solo mañana", "price_note": "", "sub": "Aprovecha", "cta": "Pídelo"})
    o = await _offer(raw, "cargador marca baja de $120 a $100 solo mañana")
    assert (o.product, o.price, o.old_price, o.when) == ("Cargador marca", "$100", "$120", "Solo mañana")


@pytest.mark.asyncio
async def test_precio_inventado_por_la_ia_no_se_dibuja():
    raw = json.dumps({"product": "Micas", "price": "$99", "old_price": "$150", "when": ""})
    o = await _offer("```json\n" + raw + "\n```", "2x1 en micas este viernes")
    assert o.price == "" and o.old_price == ""


@pytest.mark.asyncio
async def test_ia_caida_usa_el_texto():
    with patch("app.services.llm_client.chat_completion", AsyncMock(side_effect=RuntimeError("429"))):
        o = await bs.generate_offer_copy("CityCell", "Tacos al pastor 3 por $50")
    assert o.price == "$50" and o.product


@pytest.mark.parametrize("price", ["$100", ""])
def test_cartel_de_oferta_1080(price):
    o = bs.OfferCopy(product="Corte de cabello degradado premium extra largo", price=price,
                     old_price="$120" if price else "", when="Hasta el sábado por la tarde",
                     price_note="3 tacos", sub="Aparta tu lugar desde el chat", cta="Pídelo por WhatsApp",
                     business_name="Taquería y Barbería Don Pepe de Tlaxiaco")
    for palette in bs.PALETTES:
        png = bs.offer_banner_png(o, palette)
        assert Image.open(io.BytesIO(png)).size == (1080, 1080)


@pytest.mark.asyncio
async def test_limpia_palabras_sueltas_y_frase_repetida():
    raw = json.dumps({"product": "Cargador marca baja", "price": "$100", "price_note": "3 por",
                      "sub": "Cargador marca baja de $120 a $100", "cta": "Pídelo"})
    o = await _offer(raw, "cargador marca baja de $120 a $100")
    assert o.product == "Cargador marca" and o.price_note == "" and o.sub == ""


def test_dos_por_uno_va_en_la_estrella():
    con = bs.offer_banner_png(bs.OfferCopy(product="Micas", price_note="2x1", business_name="CityCell"))
    sin = bs.offer_banner_png(bs.OfferCopy(product="Micas", business_name="CityCell"))
    assert con != sin


def test_precios_con_punto_o_coma():
    assert bs._clean_price("$1.500") == "$1,500"
    assert bs._clean_price("$1,500") == "$1,500"
    assert bs._clean_price("$1,50") == "$1.50"


@pytest.mark.asyncio
async def test_oferta_o_fecha_inventadas_no_salen():
    raw = json.dumps({"product": "Micas", "price": "", "price_note": "30%", "when": "Solo hoy"})
    o = await _offer(raw, "Micas en oferta este viernes")
    # El "Solo hoy" inventado no sale; sale la fecha que sí escribió el dueño.
    assert o.price_note == "" and o.when == "Este viernes"
    raw = json.dumps({"product": "Micas", "price_note": "2x1", "when": "Este viernes"})
    o = await _offer(raw, "2x1 en micas este viernes")
    assert o.price_note == "2x1" and o.when == "Este viernes"
    raw = json.dumps({"product": "Tacos", "price": "$50", "price_note": "3 tacos", "when": "Hasta el sábado"})
    o = await _offer(raw, "Tacos al pastor 3 por $50 hasta el sábado")
    assert o.price_note == "3 tacos" and o.when == "Hasta el sábado"


@pytest.mark.asyncio
async def test_precios_al_reves_se_acomodan():
    raw = json.dumps({"product": "Cargador", "price": "$120", "old_price": "$100"})
    o = await _offer(raw, "cargador de $120 a $100")
    assert o.price == "$100" and o.old_price == "$120"


def test_fecha_concreta():
    import datetime as dt
    today, send = dt.date(2026, 11, 11), dt.date(2026, 11, 12)  # escrito miércoles de noche
    assert bs.concrete_when("Solo mañana", today, send) == "Solo hoy · jueves 12"
    assert bs.concrete_when("Hasta el sábado", today, send) == "Hasta el sábado 14"
    assert bs.concrete_when("Este viernes", today, send) == "El viernes 13"
    assert bs.concrete_when("en la mañana", today, send) == "en la mañana"
    assert bs.concrete_when("todo noviembre", today, send) == "todo noviembre"
    assert bs.concrete_when("Solo mañana", today, today + dt.timedelta(days=0)) == "Solo el jueves 12"


def test_cartel_con_foto_y_logo():
    buf = io.BytesIO()
    Image.new("RGB", (640, 480), (200, 200, 200)).save(buf, "JPEG")
    o = bs.OfferCopy(product="Cargador marca", price="$100", old_price="$120", when="Solo hoy · jueves 12",
                     business_name="CityCell")
    png = bs.offer_banner_png(o, "rojo", buf.getvalue(), buf.getvalue())
    assert Image.open(io.BytesIO(png)).size == (1080, 1080)
    # Una foto rota no tumba el cartel.
    assert bs.offer_banner_png(o, "rojo", b"no es imagen", b"tampoco")[:3] == b"\xff\xd8\xff"


def test_rangos_de_dias_no_se_acortan():
    import datetime as dt
    today, send = dt.date(2026, 11, 11), dt.date(2026, 11, 12)  # miércoles
    for t in ("De lunes a viernes", "Sábado y domingo", "Todos los martes", "Desde mañana",
              "Hoy y mañana", "Hasta el miércoles"):
        assert bs.concrete_when(t, today, send) == t


def test_texto_dice_la_misma_fecha_que_el_cartel():
    import datetime as dt
    today, send = dt.date(2026, 11, 11), dt.date(2026, 11, 12)  # miércoles de noche
    t = "🔋 Cargador marca a $100 solo mañana. Es tu oportunidad. Pídelo aquí."
    assert bs.concrete_caption(t, today, send) == "🔋 Cargador marca a $100 solo hoy, jueves 12. Es tu oportunidad. Pídelo aquí."
    assert bs.concrete_caption("Mañana 2x1 en micas", today, send) == "Hoy, jueves 12 2x1 en micas"
    for same in ("Te esperamos en la mañana", "Desde mañana 2x1", "Hoy y mañana 2x1", "Solo hoy 2x1", ""):
        assert bs.concrete_caption(same, today, send) == same
    # De día sale hoy mismo: "mañana" es el jueves, sin "hoy".
    assert bs.concrete_caption("Solo mañana", today, today) == "Solo el jueves 12"


def test_sin_ia_la_fecha_no_se_pega_al_producto():
    """La cadena gratis no contestó: "a solo mañana" salía como parte del nombre."""
    o = bs._offer_from_text("cargador marca a $100 solo mañana", "CityCell")
    assert (o.product, o.price, o.when) == ("Cargador marca", "$100", "Solo mañana")
    o = bs._offer_from_text("2x1 en micas hasta el sábado", "CityCell")
    assert (o.product, o.price_note, o.when) == ("Micas", "2x1", "Hasta el sábado")
    o = bs._offer_from_text("Tacos al pastor 3 por $50 de lunes a viernes", "X")
    assert (o.product, o.price_note, o.when) == ("Tacos al pastor", "3 por", "De lunes a viernes")
    o = bs._offer_from_text("Reparación de pantalla en la mañana $500", "X")
    assert o.when == "" and o.product == "Reparación de pantalla en la mañana"


@pytest.mark.asyncio
async def test_con_ia_la_fecha_tampoco_va_en_el_nombre():
    raw = json.dumps({"product": "Cargador marca a solo mañana", "price": "$100", "when": ""})
    o = await _offer(raw, "cargador marca a $100 solo mañana")
    assert o.product == "Cargador marca" and o.when == "Solo mañana"


# ── Cartel que convence (docs/specs/2026-11-12-cartel-que-convence.md) ─────────

def _photo(color=(0, 200, 0), size=(800, 800)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "JPEG")
    return buf.getvalue()


def _px(png: bytes, xy: tuple) -> tuple:
    return Image.open(io.BytesIO(png)).convert("RGB").getpixel(xy)


OFERTA = bs.OfferCopy(product="Cargador marca", price="$100", old_price="$120",
                      when="Solo hoy · jueves 12", business_name="CityCell")


def test_caso6_con_foto_la_foto_ocupa_el_cartel():
    png = bs.offer_banner_png(OFERTA, "rojo", _photo((0, 200, 0)))
    r, g, b = _px(png, (540, 380))  # el centro de arriba es la foto, sin tapar
    assert g > 150 and r < 60 and b < 60
    r, g, b = _px(png, (900, 700))  # abajo a la derecha, el sello con el precio
    assert (r, g, b) != _px(png, (540, 380))


def test_caso7_sin_foto_fondo_liso_sin_rayas():
    png = bs.offer_banner_png(OFERTA, "rojo")
    img = Image.open(io.BytesIO(png)).convert("L")
    row = [img.getpixel((x, 175)) for x in range(560, 1040)]  # zona sin texto
    assert max(abs(a - b) for a, b in pairwise(row)) <= 3  # degradado suave, sin rayas
    col = [img.getpixel((1050, y)) for y in range(20, 900)]  # orilla derecha, de arriba abajo
    assert max(abs(a - b) for a, b in pairwise(col)) <= 3  # sin escalones


@pytest.mark.parametrize("photo", [None, "foto"])
def test_caso8_ningun_texto_mas_chico_que_44_px(monkeypatch, photo):
    sizes = []
    real = bs._offer_font

    def spy(size, weight=900):
        sizes.append(size)
        return real(size, weight)

    monkeypatch.setattr(bs, "_offer_font", spy)
    o = bs.OfferCopy(product="Corte de cabello y barba degradado", price="$1,250", old_price="$1,500",
                     price_note="por persona", when="De lunes a viernes por la tarde",
                     business_name="Barbería El Güero de Tlaxiaco")
    bs.offer_banner_png(o, "elegante", _photo() if photo else None)
    assert min(sizes) >= 44 * 2  # se dibuja al doble y se reduce


def test_caso9_sin_domicilio_ni_barra_de_abajo():
    o = bs.OfferCopy(product="Micas", price="$60", business_name="CityCell", contact="WhatsApp 953 172 4341")
    assert not hasattr(o, "delivery")
    png = bs.offer_banner_png(o, "rojo")
    # Ya no hay franja blanca abajo con "Escríbenos" y el WhatsApp.
    assert sum(_px(png, (540, 1060))) < 600


def test_caso13_telefono_arriba_a_la_derecha():
    sin = bs.offer_banner_png(OFERTA, "rojo")
    o = bs.OfferCopy(product="Micas", price="$60", business_name="CityCell", contact="WhatsApp 953 172 4341")
    con = bs.offer_banner_png(o, "rojo")
    assert _px(con, (1080 - 64 - 20, 64 + 40)) == (255, 255, 255)  # la cinta blanca del teléfono
    assert _px(sin, (1080 - 64 - 20, 64 + 40)) != (255, 255, 255)
    assert _px(con, (64 + 20, 64 + 40)) == (255, 255, 255)  # el nombre sigue a la izquierda


def test_caso13_nombre_largo_no_se_encima_con_el_telefono():
    o = bs.OfferCopy(product="Micas", price="$60", business_name="Refaccionaria y Ferretería Hermanos López",
                     contact="WhatsApp 953 172 4341")
    con = Image.open(io.BytesIO(bs.offer_banner_png(o, "rojo"))).convert("RGB")
    # Entre el nombre y el teléfono queda fondo (no una cinta blanca corrida).
    row = [con.getpixel((x, 64 + 40)) for x in range(64, 1080 - 64)]
    assert any(sum(p) < 600 for p in row)


def test_caso10_logo_en_circulo_o_nombre():
    con = bs.offer_banner_png(OFERTA, "rojo", logo=_photo((0, 0, 255)))
    r, _, b = _px(con, (64 + 70, 64 + 70))  # el centro del círculo es el logo
    assert b > 180 and r < 60
    sin = bs.offer_banner_png(OFERTA, "rojo")
    assert _px(sin, (64 + 20, 64 + 40)) == (255, 255, 255)  # la cinta blanca con el nombre


def test_caso11_foto_vertical_se_recorta_y_una_rota_no_tumba_el_cartel():
    tall = bs.offer_banner_png(OFERTA, "rojo", _photo((0, 200, 0), (600, 1400)))
    assert Image.open(io.BytesIO(tall)).size == (1080, 1080)
    assert bs.offer_banner_png(OFERTA, "rojo", b"no es foto")[:3] == b"\xff\xd8\xff"  # JPEG


def test_caso8_nota_larga_no_se_corta_en_el_sello():
    assert bs._note_fits_seal("3 tacos", 175 * 2, 2)
    assert not bs._note_fits_seal("2 hamburguesas", 175 * 2, 2)
    o = bs.OfferCopy(product="Hamburguesas", price="$99", price_note="2 hamburguesas", when="Solo hoy · jueves 12",
                     business_name="Burger")
    assert bs.offer_banner_png(o, "rojo", _photo())[:3] == b"\xff\xd8\xff"


def test_otra_version_cambia_colores_y_lado_del_sello():
    """12-nov: «Otra versión» sacaba el mismo cartel; ahora rota colores y lado."""
    looks = [bs.offer_look("rojo", k) for k in range(7)]
    assert looks[0] == ("rojo", False) and looks[1] == ("azul", True)
    assert len({p for p, _ in looks[:6]}) == 6 and looks[6] == looks[0]
    assert bs.offer_look("azul", 0) == ("azul", False) and bs.offer_look("azul", 1)[0] != "azul"
    o = bs.OfferCopy(product="Cargador", price="$99", old_price="$120", when="Solo hoy · jueves 12")
    right = bs.offer_banner_png(o, "rojo", _photo())
    left = bs.offer_banner_png(o, "rojo", _photo(), seal_left=True)
    # El sello (blanco por fuera) cae de un lado o del otro.
    assert _px(left, (64 + 8, 700)) != _px(right, (64 + 8, 700)) or _px(left, (1080 - 64 - 8, 700)) != _px(
        right, (1080 - 64 - 8, 700))


def test_precio_sin_signo_de_pesos():
    """12-nov: "Cargador marca a 99, solo hoy" salió sin precio en el cartel."""
    cases = {
        "Cargador marca a 99, solo hoy": ["$99"], "cargador marca a 99 solo hoy": ["$99"],
        "micas a 1,200 hasta el domingo": ["$1,200"], "fundas 99 pesos": ["$99"], "cargador a 99": ["$99"],
        "cargador de 20 W a 150": ["$150"], "memoria de 64 GB en 199": ["$199"], "iPhone 13 en 2500": ["$2,500"],
        "Promo: mica a 60. Solo hoy": ["$60"], "cargador a $99": ["$99"],
    }
    for text, want in cases.items():
        assert bs._prices_in(text) == want, text


def test_numeros_que_no_son_precio():
    """revisor-dinero 12-nov: un número suelto casi siempre es otra cosa."""
    for text in ("iPhone 13 a 12 msi", "Cambio de pantalla en 40 minutos", "Estamos a 15 min del centro",
                 "Fundas en 10 colores", "Pagos a 10 semanas", "Crédito a 12 quincenas", "Horario de 10 a 7",
                 "Abrimos de 10 a 20 hrs", "Liquidación en 2025", "Galaxy A54 en 128 y 256", "Celulares de 2000 a 5000",
                 "a 3 meses sin intereses", "a las 10", "el 15 de noviembre", "llámame al 953 172 4341",
                 "2x1 en micas", "20% en fundas", "3 por 50 tacos"):
        assert bs._prices_in(text) == [], text
    for text in ("iPhone 15 en 256, solo hoy", "Galaxy A54 en 128"):  # la memoria
        assert bs._prices_in(text) == [], text
    # Miles enteros, nunca cortados ("$15" de "15,999").
    assert bs._prices_in("Galaxy S23 Ultra a 15,999 antes 18,999") == ["$15,999"]
    o = bs._offer_from_text("Galaxy S23 Ultra a 15,999 antes 18,999", "X")
    assert (o.price, o.old_price) == ("$15,999", "")  # "antes 18,999" sin "a": no se adivina
    assert bs._prices_in("Galaxy S23 Ultra a 15,999, antes 18,999") == ["$15,999"]
    assert bs._prices_in("iPhone 14 a 12,500 con funda de regalo") == []
    assert bs._prices_in("Moto Edge a 10.999 solo hoy") == ["$10,999"]
    # Con "$" gana lo que el dueño marcó como precio.
    assert bs._prices_in("Galaxy A54 en 128, a $4,500") == ["$4,500"]
    # Sin "antes" en el texto, dos números no son un "Antes $X" (memoria, rangos).
    for text in ("Galaxy A06 de 64 a 2,499", "Redmi 13C de 128 a 2799 solo hoy", "Cargador a $99 y cable a $50"):
        assert bs._offer_from_text(text, "X").old_price == "", text
    o = bs._offer_from_text("Mica a 99 pesos antes 150 pesos", "X")
    assert (o.price, o.old_price) == ("$99", "$150")
    o = bs._offer_from_text("cargador marca de $120 a $99", "X")
    assert (o.price, o.old_price) == ("$99", "$120")
