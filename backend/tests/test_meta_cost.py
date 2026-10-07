"""Ahorro que se le muestra al dueño: lo que Meta habría cobrado por las
respuestas que se dieron por la web, contando las 1,000 gratis del mes."""
from app.config import settings
from app.services.meta_cost import web_savings_mxn


def test_no_savings_while_everything_fits_in_the_free_thousand():
    assert web_savings_mxn(300, 400) == 0


def test_only_the_web_replies_past_the_free_thousand_count():
    # 900 por WhatsApp + 300 por web: sin la web habrían sido 1,200 → 200 cobrados.
    assert web_savings_mxn(900, 300) == round(200 * settings.META_SERVICE_PRICE_MXN, 2)


def test_all_web_replies_count_when_whatsapp_already_passed_the_thousand():
    assert web_savings_mxn(2000, 500) == round(500 * settings.META_SERVICE_PRICE_MXN, 2)
