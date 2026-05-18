import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.database import AsyncSessionLocal
from app.models.message import Message
from sqlalchemy import select

async def main():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Message))
        messages = result.scalars().all()
        print(f"📝 Total de mensajes registrados en DB: {len(messages)}")
        for m in messages:
            print(f"   - ID: {m.id} | Estado: {m.status} | Twilio SID: {m.twilio_sid} | Fecha: {m.created_at}")

if __name__ == "__main__":
    asyncio.run(main())
