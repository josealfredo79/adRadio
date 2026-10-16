"""Panel del piloto en /app/admin (admin.pilot_overview): embudo, altas por
semana y uso de cada negocio, sacado de la base en vez de PostHog
(decisión 2026-10-15). La base de pruebas puede traer usuarios de otras
pruebas, así que el embudo se compara antes/después de sembrar."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete

from app.api.v1.admin import pilot_overview
from app.database import AsyncSessionLocal, engine
from app.models.appointment import Appointment
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.order import Order
from app.models.user import User


async def _overview():
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        return await pilot_overview(db=db)


@pytest.mark.asyncio
async def test_embudo_semanas_y_uso_por_negocio():
    before = await _overview()
    now = datetime.now(timezone.utc)
    run = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        paga = User(email=f"paga-{run}@t.com", password_hash="x", business_name="Paga", email_verified=True,
                    subscription_status="active", current_plan="growth", last_seen_at=now - timedelta(hours=2))
        abrio = User(email=f"abrio-{run}@t.com", password_hash="x", business_name="Abrió pago", email_verified=True,
                     subscription_status="trial", stripe_customer_id=f"cus_{run}")
        sin_verificar = User(email=f"nada-{run}@t.com", password_hash="x", email_verified=False)
        admin = User(email=f"admin-{run}@t.com", password_hash="x", role="admin", email_verified=True,
                     subscription_status="active")
        db.add_all([paga, abrio, sin_verificar, admin])
        await db.flush()
        ana = Contact(advertiser_id=paga.id, name="Ana", phone=f"+52155{uuid.uuid4().int % 10**8:08d}")
        db.add(ana)
        await db.flush()
        db.add_all([
            Conversation(advertiser_id=paga.id, contact_id=ana.id, messages=[], last_activity=now),
            Appointment(advertiser_id=paga.id, contact_id=ana.id, customer_name="Ana", service="Corte",
                        scheduled_at=now + timedelta(days=1), status="confirmed"),
            Order(advertiser_id=paga.id, contact_id=ana.id, order_number=1, state="confirmed", items_raw="1 x"),
        ])
        await db.commit()
        ids = [paga.id, abrio.id, sin_verificar.id, admin.id]
    try:
        after = await _overview()
        delta = {k: after["embudo"][k] - before["embudo"][k]
                 for k in ("registrados", "verificaron_correo", "en_prueba", "pagando", "abrieron_pago_sin_pagar")}
        # El admin no cuenta.
        assert delta == {"registrados": 3, "verificaron_correo": 2, "en_prueba": 2, "pagando": 1,
                         "abrieron_pago_sin_pagar": 1}
        assert len(after["semanas"]) == 8
        assert after["semanas"][-1]["registros"] - before["semanas"][-1]["registros"] == 3
        rows = {n["email"]: n for n in after["negocios"]}
        assert f"admin-{run}@t.com" not in rows
        p = rows[f"paga-{run}@t.com"]
        assert (p["chats_30d"], p["citas_30d"], p["pedidos_30d"], p["contactos"]) == (1, 1, 1, 1)
        assert p["ultimo_acceso"] is not None and p["prueba_vence"] is None
        assert rows[f"abrio-{run}@t.com"]["chats_30d"] == 0
    finally:
        await engine.dispose()
        async with AsyncSessionLocal() as db:
            for model in (Order, Appointment, Conversation, Contact):
                await db.execute(delete(model).where(model.advertiser_id.in_(ids)))
            await db.execute(delete(User).where(User.id.in_(ids)))
            await db.commit()
        await engine.dispose()
