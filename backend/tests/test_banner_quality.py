"""El cartel de colores del Copiloto salía con el título en letra de 10 px
(fuente que no existía en la imagen web) y con "¡Hola, !" sin nombre."""
import os

from PIL import ImageFont

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
