import asyncio
from app.database import AsyncSessionLocal
from app.models.user import User
import traceback
import sys

async def setup_db():
    try:
        async with AsyncSessionLocal() as db:
            user = User(
                email="test_reschedule4@example.com",
                password_hash="fakehash",
                business_name="Test Business",
                subscription_status="active",
                current_plan="pro",
                messages_remaining=100,
                whatsapp_number="whatsapp:+10000000004"
            )
            db.add(user)
            await db.flush()
            print("Success")
    except Exception as e:
        print("REAL ERROR:", e.orig if hasattr(e, 'orig') else e)
        traceback.print_exc()

asyncio.run(setup_db())
