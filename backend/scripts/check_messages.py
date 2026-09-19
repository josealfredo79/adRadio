import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.message import Message


async def main():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Message))
        messages = result.scalars().all()
        print(f"📝 Total de mensajes registrados en DB: {len(messages)}")
        for m in messages:
            print(f"   - ID: {m.id} | Estado: {m.status} | Twilio SID: {m.twilio_sid} | Fecha: {m.created_at}")

if __name__ == "__main__":
    asyncio.run(main())
