"""Clientes de un negocio que contestan al número central de IaRadio: se les
manda a su negocio en vez de al bot de ventas (real-DB)."""
import uuid

import pytest
from sqlalchemy import delete

from app.config import settings
from app.database import AsyncSessionLocal, engine
from app.models.contact import Contact
from app.models.user import User
from app.services.central_number_redirect import customer_redirect_reply
from app.services.portal_service import portal_url


@pytest.fixture
async def seeded(monkeypatch):
    """IaRadio (la cuenta del número central) y cuatro negocios. Ana es
    clienta de Barbería (guardada a 10 dígitos) y además contacto de IaRadio;
    Beto es cliente de los cuatro negocios; Caro solo es prospecto de
    IaRadio; Dani está bloqueada en Barbería."""
    monkeypatch.setattr(settings, "SECRET_KEY", settings.SECRET_KEY or "test-secret")
    await engine.dispose()
    tail = f"{uuid.uuid4().int % 10**7:07d}"
    ana, beto, caro, dani = (f"+52155{n}{tail}" for n in "1234")
    async with AsyncSessionLocal() as db:
        central = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="IaRadio")
        barber = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Barbería Don Pepe")
        tacos = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Tacos El Primo")
        nails = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Uñas Lupita")
        nails2 = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Spa Sol")
        users = [central, barber, tacos, nails, nails2]
        db.add_all(users)
        await db.flush()
        ana_barber = Contact(advertiser_id=barber.id, name="Ana", phone=ana[4:])  # 10 dígitos, como de CSV
        db.add_all([
            ana_barber,
            Contact(advertiser_id=central.id, name="Ana", phone=ana),
            Contact(advertiser_id=barber.id, name="Beto", phone=beto),
            Contact(advertiser_id=tacos.id, name="Beto", phone=beto),
            Contact(advertiser_id=nails.id, name="Beto", phone=beto),
            Contact(advertiser_id=nails2.id, name="Beto", phone=beto),
            Contact(advertiser_id=central.id, name="Caro", phone=caro),
            Contact(advertiser_id=barber.id, name="Dani", phone=dani, status="blocked"),
        ])
        await db.commit()
        ids = [u.id for u in users]
        ana_contact = ana_barber.id
    yield {"central": central.id, "ana": ana, "ana_contact": ana_contact,
           "beto": beto, "caro": caro, "dani": dani}
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        for uid in ids:
            await db.execute(delete(Contact).where(Contact.advertiser_id == uid))
            await db.execute(delete(User).where(User.id == uid))
        await db.commit()
    await engine.dispose()


async def test_customer_of_one_business_gets_its_chat_link(seeded):
    async with AsyncSessionLocal() as db:
        # WhatsApp lo manda con 521; en Barbería está guardada a 10 dígitos.
        reply = await customer_redirect_reply(db, seeded["ana"], central_account_id=seeded["central"])
    assert "Barbería Don Pepe" in reply
    assert portal_url(seeded["ana_contact"]) in reply
    assert "IaRadio" not in reply.split("\n\n", 1)[1]  # no le ofrece planes


async def test_prospect_who_is_nobodys_customer_keeps_the_sales_bot(seeded):
    async with AsyncSessionLocal() as db:
        assert await customer_redirect_reply(db, seeded["caro"], central_account_id=seeded["central"]) is None
        assert await customer_redirect_reply(db, "+5215500000000", central_account_id=seeded["central"]) is None


async def test_blocked_contact_does_not_count(seeded):
    async with AsyncSessionLocal() as db:
        assert await customer_redirect_reply(db, seeded["dani"], central_account_id=seeded["central"]) is None


async def test_many_businesses_lists_three_while_mi_is_off(seeded, monkeypatch):
    monkeypatch.setattr(settings, "CUSTOMER_ACCOUNT_ENABLED", False)
    async with AsyncSessionLocal() as db:
        reply = await customer_redirect_reply(db, seeded["beto"], central_account_id=seeded["central"])
    assert reply.count("/c/") == 3 and "/mi" not in reply


async def test_many_businesses_go_to_mi_when_it_is_on(seeded, monkeypatch):
    monkeypatch.setattr(settings, "CUSTOMER_ACCOUNT_ENABLED", True)
    async with AsyncSessionLocal() as db:
        reply = await customer_redirect_reply(db, seeded["beto"], central_account_id=seeded["central"])
    assert reply.rstrip().endswith("/mi") and "/c/" not in reply
