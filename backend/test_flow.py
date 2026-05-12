import asyncio
from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.appointment import Appointment
from sqlalchemy import select

async def test_reschedule():
    async with AsyncSessionLocal() as db:
        # 1. Create a dummy user and appointment
        user = User(
            email="test_reschedule@example.com",
            business_name="Test Business",
            subscription_status="active",
            current_plan="pro",
            messages_remaining=100
        )
        db.add(user)
        await db.flush()

        from datetime import datetime, timedelta, timezone
        appt = Appointment(
            advertiser_id=user.id,
            customer_name="Juan Perez",
            customer_phone="+1234567890",
            service="Corte de Pelo",
            scheduled_at=datetime.now(timezone.utc) + timedelta(days=1),
            status="pending",
            awaiting_confirmation=True
        )
        db.add(appt)
        await db.commit()

        # 2. Simulate user sending "2" (Cancel)
        print(f"[{appt.id}] Initial state: status={appt.status}, awaiting_confirmation={appt.awaiting_confirmation}, awaiting_reschedule={appt.awaiting_reschedule}")
        
        # We'd have to mock the webhook. Instead of full HTTP request, let's just see if we can call the handler directly.
        # It's easier to just use TestClient from fastapi.testclient.
        
        print("Done setup.")

asyncio.run(test_reschedule())
