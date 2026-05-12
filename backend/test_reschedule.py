import asyncio
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.appointment import Appointment
from sqlalchemy import select, delete
from datetime import datetime, timedelta, timezone

import app.api.v1.webhooks as webhooks_module
# Mock Twilio validation
webhooks_module._validate_twilio_signature = lambda *args, **kwargs: True

async def setup_db():
    async with AsyncSessionLocal() as db:
        # Cleanup past test data
        await db.execute(delete(Appointment).where(Appointment.customer_phone == "+1234567890"))
        await db.execute(delete(User).where(User.email == "test_reschedule@example.com"))
        
        user = User(
            email="test_reschedule@example.com",
            password_hash="fakehash",
            business_name="Test Business",
            subscription_status="active",
            current_plan="pro",
            messages_remaining=100,
            whatsapp_number="+10000000000"
        )
        db.add(user)
        await db.flush()

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
        return str(user.id), str(appt.id)

async def check_appt_state(appt_id: str):
    import uuid
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Appointment).where(Appointment.id == uuid.UUID(appt_id)))
        return result.scalar_one_or_none()

async def run_tests():
    user_id, appt_id = await setup_db()

    print("--- Probando Flujo de Reagendamiento ---")
    appt = await check_appt_state(appt_id)
    print(f"Estado Inicial: status={appt.status}, awaiting_confirmation={appt.awaiting_confirmation}, awaiting_reschedule={appt.awaiting_reschedule}")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Simulamos el webhook cancelando la cita ("2")
        payload = {"From": "whatsapp:+1234567890", "To": "whatsapp:+10000000000", "Body": "2"}
        response = await ac.post("/api/v1/webhooks/twilio/incoming", data=payload)
        print("Respuesta Webhook Cancelar (2):", response.status_code, response.text)
        
        appt = await check_appt_state(appt_id)
        print(f"Estado tras Cancelar: status={appt.status}, awaiting_confirmation={appt.awaiting_confirmation}, awaiting_reschedule={appt.awaiting_reschedule}")

        # Simulamos el webhook pidiendo reagendar ("si")
        payload = {"From": "whatsapp:+1234567890", "To": "whatsapp:+10000000000", "Body": "si"}
        response = await ac.post("/api/v1/webhooks/twilio/incoming", data=payload)
        print("Respuesta Webhook Reagendar (si):", response.status_code, response.text)

        appt = await check_appt_state(appt_id)
        print(f"Estado tras Reagendar: status={appt.status}, awaiting_confirmation={appt.awaiting_confirmation}, awaiting_reschedule={appt.awaiting_reschedule}")

if __name__ == "__main__":
    asyncio.run(run_tests())
