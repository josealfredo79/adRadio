import asyncio
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.user import User

async def main():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User.email, User.whatsapp_number, User.whatsapp_number_source))
        users = result.all()
        for u in users:
            print(u)

if __name__ == "__main__":
    asyncio.run(main())
