import asyncio
from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.appointment import Appointment
from sqlalchemy import select, delete
from datetime import datetime, timedelta, timezone

async def setup_db():
    try:
        async with AsyncSessionLocal() as db:
            user = User(
                email="test_reschedule3@example.com",
                business_name="Test Business",
                subscription_status="active",
                current_plan="pro",
                messages_remaining=100,
                whatsapp_number="whatsapp:+10000000003"
            )
            db.add(user)
            await db.flush()
            print("Successfully inserted user.")
            
            appt = Appointment(
                advertiser_id=user.id,
                customer_name="Juan Perez",
                customer_phone="+1234567890",
                service="Corte de Pelo",
                scheduled_at=datetime.now(timezone.utc) + timedelta(days=1),
                status="pending",
                awaiting_confirmation=True,
                awaiting_reschedule=False
            )
            db.add(appt)
            await db.commit()
            print("Successfully inserted appt.")
            
    except Exception as e:
        print("DATABASE ERROR:")
        print(str(e))

asyncio.run(setup_db())
