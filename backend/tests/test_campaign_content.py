"""El mensaje de campaña que arma la IA (POST /campaigns/generate-content) ve
el catálogo real del negocio, para no inventar productos ni precios en una
promo que se manda a todos los clientes (docs/PLAN-CAMPANAS-SIMPLES.md, Fase 0)."""
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete

from app.api.v1.campaigns import generate_content
from app.database import AsyncSessionLocal
from app.models.product import Product
from app.models.user import User
from app.schemas.campaign import GenerateContentRequest
from tests.test_web_push import (  # noqa: F401 — _keys es fixture autouse
    _cleanup,
    _keys,
    _seed,
)

BODY = GenerateContentRequest(campaign_type="promo", business_name="CityCell", intent="2x1 en fundas el sábado")


async def _generate(user_id) -> str:
    """Corre el endpoint con la IA simulada y devuelve el prompt que recibió."""
    chat = AsyncMock(return_value="🔥 Uno\n---\n✨ Dos\n---\n🎉 Tres")
    with patch("app.services.claude_service.chat_completion", chat):
        async with AsyncSessionLocal() as db:
            out = await generate_content(BODY, db=db, current_user=await db.get(User, user_id))
    assert len(out.variants) == 3
    return chat.await_args.args[0][0]["content"]


@pytest.mark.asyncio
async def test_prompt_carries_the_real_catalog_and_no_invent_rule():
    user_id, _ = await _seed(0)
    try:
        async with AsyncSessionLocal() as db:
            db.add_all([
                Product(advertiser_id=user_id, name="Funda de silicón", price=Decimal("120.00")),
                Product(advertiser_id=user_id, name="Mica vieja", price=Decimal(50), active=False),
            ])
            await db.commit()
        prompt = await _generate(user_id)
        assert "Funda de silicón — $120" in prompt and "$120.00" not in prompt.split("No inventes")[0]
        assert "Mica vieja" not in prompt  # inactivo: no se anuncia
        assert "No inventes nada" in prompt
        assert "2x1 en fundas el sábado" in prompt
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(Product).where(Product.advertiser_id == user_id))
            await db.commit()
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_without_catalog_still_forbids_inventing_prices():
    user_id, _ = await _seed(0)
    try:
        prompt = await _generate(user_id)
        assert "CATÁLOGO" not in prompt
        assert "Si no hay precio, no\npongas precio" in prompt
    finally:
        await _cleanup(user_id)
