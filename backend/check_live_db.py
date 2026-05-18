import asyncio
import sys
import os
from sqlalchemy import select

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.contact import Contact
from app.models.campaign import Campaign
from app.models.message import Message

async def check_db():
    print("🔍 Diagnosticando Base de Datos de Producción...")
    async with AsyncSessionLocal() as db:
        # 1. Consultar Usuarios
        users_res = await db.execute(select(User))
        users = users_res.scalars().all()
        print(f"\n👥 Usuarios registrados: {len(users)}")
        for u in users:
            print(f"   - ID: {u.id} | Email: {u.email} | Business: {u.business_name} | WhatsApp Emisor: {u.whatsapp_number} | Créditos: {u.messages_remaining}")

        # 2. Consultar Campañas
        campaigns_res = await db.execute(select(Campaign).order_by(Campaign.created_at.desc()))
        campaigns = campaigns_res.scalars().all()
        print(f"\n📻 Campañas registradas: {len(campaigns)}")
        for c in campaigns[:10]:  # Mostrar últimas 10
            segment_val = c.segment
            ab_val = c.ab_test
            print(f"   - ID: {c.id} | Nombre: {c.name} | Status: {c.status} | AdvID: {c.advertiser_id} | Segment: {segment_val} | Audio: {ab_val.get('audio_url', 'Ninguno')}")

        # 3. Consultar Contactos
        contacts_res = await db.execute(select(Contact))
        contacts = contacts_res.scalars().all()
        print(f"\n📇 Contactos registrados: {len(contacts)}")
        for cont in contacts:
            print(f"   - ID: {cont.id} | Nombre: {cont.name} | Teléfono: {cont.phone} | Status: {cont.status} | AdvID: {cont.advertiser_id} | Tags: {cont.tags}")

        # 4. Consultar Mensajes Recientes
        messages_res = await db.execute(select(Message).order_by(Message.created_at.desc()))
        messages = messages_res.scalars().all()
        print(f"\n💬 Mensajes registrados (últimos 10): {len(messages)}")
        for m in messages[:10]:
            print(f"   - ID: {m.id} | CampID: {m.campaign_id} | ContID: {m.contact_id} | Dir: {m.direction} | Status: {m.status} | Twilio SID: {m.twilio_sid} | Creado: {m.created_at}")

if __name__ == "__main__":
    asyncio.run(check_db())
