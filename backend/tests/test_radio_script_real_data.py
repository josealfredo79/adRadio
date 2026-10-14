"""Guion de la cuña con los datos reales del negocio (2026-10-13): la IA
inventaba teléfonos ("55 1234 5678") y usaba el nombre de la campaña como si
fuera el negocio. La IA se simula; aquí se revisa qué se le manda."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.radio.scripts import (
    NO_INVENTAR,
    generate_radio_script,
    radio_business,
)


def _user(**kw):
    base = {"business_name": "CityCell", "city": "Tlaxiaco", "whatsapp_number": "+529531953182",
            "phone": "+529531953182", "meta_connection_status": None, "meta_display_phone_number": None}
    return SimpleNamespace(**{**base, **kw})


def test_uses_the_real_business_name_not_the_campaign_name():
    name, _ = radio_business(_user(), fallback_name="Promo Micas")
    assert name == "CityCell"


def test_never_uses_the_owners_personal_number():
    _, contact = radio_business(_user())
    assert "9531953182" not in contact
    assert contact == "en Tlaxiaco"


def test_uses_the_connected_whatsapp_business_number():
    _, contact = radio_business(_user(meta_connection_status="connected", meta_display_phone_number="+52 55 1111 2222"))
    assert contact == "WhatsApp +52 55 1111 2222, en Tlaxiaco"


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["classic", "comunitaria", "capsula", "trivia", "historia", "alerta", "estacional"])
async def test_every_mode_forbids_inventing_contact_data(mode):
    llm = AsyncMock(return_value="guion")
    with patch("app.services.llm_client.chat_completion", llm):
        await generate_radio_script("CityCell", "2 micas por 1", mode=mode, contact="")
    system = llm.await_args.kwargs["system"]
    prompt = llm.await_args.args[0][0]["content"]
    assert system.endswith(NO_INVENTAR)
    assert "Negocio: CityCell" in prompt
    assert "Contacto: ninguno" in prompt


@pytest.mark.parametrize("raw,spoken", [
    ("*[Música suave de fondo]*\n\n---\n\n¿Sabías que cargar el cel **toda la noche** daña la batería?",
     "¿Sabías que cargar el cel toda la noche daña la batería?"),
    ("*Inhala.*\n\nValeria tenía entrevista. (pausa) Se le rompió la pantalla.",
     "Valeria tenía entrevista. Se le rompió la pantalla."),
    ("(Efecto: ding) En CityCell te ayudan.", "En CityCell te ayudan."),
    ("Lleva 2x1 (solo esta semana) en CityCell.", "Lleva 2x1 (solo esta semana) en CityCell."),
])
def test_stage_directions_are_not_read_aloud(raw, spoken):
    from app.services.radio.scripts import clean_script

    assert clean_script(raw) == spoken


@pytest.mark.asyncio
async def test_generated_script_comes_out_clean():
    with patch("app.services.llm_client.chat_completion", AsyncMock(return_value="*[Jingle]*\n¡Hola, Tlaxiaco! (pausa) Esto es CityCell.")):
        assert await generate_radio_script("CityCell", "promo") == "¡Hola, Tlaxiaco! Esto es CityCell."
