import asyncio
import sys
import os
from sqlalchemy import select

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.database import AsyncSessionLocal
from app.models.user import User

async def read_logs():
    print("📡 Consultando base de datos de producción para telemetría de logs...")
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User))
        user = result.scalars().first()
        if user and user.bot_personality:
            print("\n================== LOGS DE CELERY EN PRODUCCIÓN ==================")
            print(user.bot_personality)
            print("==================================================================\n")
        else:
            print("⚠️ No se encontró telemetría de logs todavía. Es posible que el contenedor aún no haya ejecutado su healthcheck.")

if __name__ == "__main__":
    asyncio.run(read_logs())
