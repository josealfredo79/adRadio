"""Fallas que encontró la simulación del 2026-10-31: un "ok pero..." confirmaba
el pedido viejo, dirección que el cliente no escribió, domicilio negado."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services import customer_agent
from app.services.customer_agent import _clean_yes_no, _customer_wrote, delivery_fact


@pytest.mark.parametrize("said", [
    "si", "Sí", "sí!", "ok", "va", "dale", "Sí, confírmalo", "confirmalo", "si por favor", "ok gracias",
    "claro que si", "esta bien si", "sale", "de acuerdo si", "está bien", "de acuerdo", "por favor", "mándalo",
    "sí, ya",
])
def test_a_clean_yes_confirms(said):
    assert _clean_yes_no(said) is True


@pytest.mark.parametrize("said", ["cancélalo", "sí, cancélalo", "cancela", "si"])
def test_cancel_confirms_a_pending_cancellation(said):
    assert _clean_yes_no(said, cancelling=True) is True


@pytest.mark.parametrize("said", ["no", "mejor no"])
def test_no_keeps_what_was_going_to_be_cancelled(said):
    assert _clean_yes_no(said, cancelling=True) is False


@pytest.mark.parametrize("said", ["no", "No", "no gracias", "mejor no", "todavia no", "cancela", "cancelalo"])
def test_a_clean_no_cancels(said):
    assert _clean_yes_no(said) is False


@pytest.mark.parametrize("said", [
    "ok la de vidrio", "si pero mejor la de vidrio", "va pero son 2", "ok cuanto sale el envio",
    "ok la hidrogel, una pa recoger", "no, mejor la de vidrio", "si no", "gracias", "",
    "como la pago", "donde estan?", "¿está listo?", "si?",
])
def test_anything_else_keeps_talking(said):
    assert _clean_yes_no(said) is None


def _ctx(*said):
    return SimpleNamespace(customer_text=" ".join(said))


def test_the_address_must_come_from_the_customer():
    assert _customer_wrote(_ctx("mandalo a calle hidalgo 25 centro"), "Calle Hidalgo 25, Centro")
    assert _customer_wrote(_ctx("av independencia 12"), "Avenida Independencia 12")
    assert _customer_wrote(_ctx("hidalgo 25"), "Calle Hidalgo 25, Centro, Tlaxiaco")
    assert not _customer_wrote(_ctx("quiero 2 micas a domicilio"), "Calle Hidalgo 25, Centro")
    assert not _customer_wrote(_ctx("quiero 2 micas"), "")


@pytest.mark.parametrize("value,text", [(True, "SÍ entrega"), (False, "NO entrega"), (None, "avisar al dueño")])
def test_delivery_fact_never_guesses(value, text):
    assert text in delivery_fact(SimpleNamespace(delivers_home=value))


@pytest.mark.asyncio
async def test_asking_for_delivery_brings_the_fact():
    ctx = SimpleNamespace(
        db=None, message="me lo traen?",
        advertiser=SimpleNamespace(id="x", bot_instructions=None, delivers_home=True),
    )
    with patch("app.services.rag_service.search_knowledge", AsyncMock(return_value="")):
        out = await customer_agent._tool_consultar_negocio(ctx, {"pregunta": "entregas"})
    assert "SÍ entrega" in out["informacion"]
