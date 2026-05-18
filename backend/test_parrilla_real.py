import asyncio
import sys
import os
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.contact import Contact
from app.models.message import Message
from sqlalchemy import select, delete

async def main():
    print("🚀 Iniciando prueba real de Parrilla + Twilio...")
    
    # Destinatario real de pruebas
    destinatario = "+529531953182"
    # Audio de prueba (.ogg)
    audio_url = "https://6481e4df37691c3164688cc3324898bc.r2.cloudflarestorage.com/adradio-audio/test_audio.ogg"
    script = "🎙️ Hola, esta es una prueba real del flujo de la parrilla de IaRadio. El motor de envío ahora está 100% operativo."
    
    async with AsyncSessionLocal() as db:
        # Limpieza previa por seguridad
        await db.execute(delete(Message).where(Message.content.like("[PARRILLA:%")))
        await db.execute(delete(Contact).where(Contact.phone == destinatario))
        await db.execute(delete(User).where(User.email == "test_parrilla@example.com"))
        await db.commit()
        
        # 1. Crear usuario de prueba con plan Pro y el remitente correcto
        user = User(
            email="test_parrilla@example.com",
            password_hash="fakehash",
            business_name="La Parrilla Test",
            subscription_status="active",
            current_plan="pro",
            messages_remaining=100,
            whatsapp_number="+5215599631448" # Remitente aprobado en Twilio
        )
        db.add(user)
        await db.flush()
        
        # 2. Crear contacto de prueba
        contact = Contact(
            advertiser_id=user.id,
            name="Cliente de Prueba",
            phone=destinatario,
            status="active"
        )
        db.add(contact)
        await db.commit()
        
        user_id = str(user.id)
        contact_id = contact.id
        print(f"✅ Creado usuario de prueba ID: {user_id}")
        print(f"✅ Creado contacto de prueba para teléfono: {destinatario}")
        
    print("\n📻 Simulando tarea Celery: send_parrilla_day...")
    async with AsyncSessionLocal() as db:
        # Crear mensaje encolado
        msg = Message(
            advertiser_id=uuid.UUID(user_id),
            contact_id=contact_id,
            direction="outbound",
            content=f"[PARRILLA:Lunes:classic] {audio_url}",
            status="queued",
            scheduled_for=datetime.now(timezone.utc),
        )
        db.add(msg)
        await db.commit()
        await db.refresh(msg)
        msg_id = str(msg.id)
        print(f"   -> Mensaje de parrilla encolado creado en DB (ID: {msg_id})")

    print("\n💬 Ejecutando tarea Celery: send_whatsapp_voice_note...")
    from app.services.twilio_service import send_whatsapp_media
    
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Message).where(Message.id == uuid.UUID(msg_id)))
        message_obj = result.scalar_one_or_none()
        
        from_number = "+5215599631448"
        print(f"   -> Llamando a Twilio con nota de voz: de={from_number} a={destinatario}")
        sid = await send_whatsapp_media(destinatario, audio_url, body=script, from_number=from_number)
        
        if sid:
            message_obj.status = "sent"
            message_obj.twilio_sid = sid
            message_obj.sent_at = datetime.now(timezone.utc)
            await db.commit()
            print(f"   ✅ ¡Mensaje enviado exitosamente a Twilio! SID: {sid}")
            print(f"   ✅ Estado del mensaje actualizado en la base de datos a: 'sent'")
        else:
            message_obj.status = "failed"
            await db.commit()
            print("   ❌ Falló el envío del mensaje en Twilio. Revisa los logs.")
            
    # Limpieza final
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Message).where(Message.id == uuid.UUID(msg_id)))
        await db.execute(delete(Contact).where(Contact.id == contact_id))
        await db.execute(delete(User).where(User.id == uuid.UUID(user_id)))
        await db.commit()
        print("\n🧹 Limpieza de base de datos completada.")

if __name__ == "__main__":
    asyncio.run(main())
