"""
Script para probar si las plantillas con botones están aprobadas.
Uso: python test_templates_aprobacion.py <numero_destino>
Ejemplo: python test_templates_aprobacion.py +521234567890
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.services.twilio_service import send_whatsapp_buttons
from app.config import settings


async def test_template(nombre: str, sid: str, to: str):
    print(f"Probando plantilla: {nombre}")
    print(f"  SID: {sid}")
    if not sid:
        print(f"  ⏭️  No configurada, se salta")
        return

    sid_result, err = await send_whatsapp_buttons(
        to=to,
        body="Prueba de template",
        template_sid=sid,
        variables={"1": "Cliente", "2": "Servicio"},
    )
    if sid_result:
        print(f"  ✅ ÉXITO — SID: {sid_result}")
    else:
        print(f"  ❌ FALLO — Error: {err}")
    print()


async def main():
    if len(sys.argv) < 2:
        print("Uso: python test_templates_aprobacion.py <numero_destino>")
        print("Ejemplo: python test_templates_aprobacion.py +521234567890")
        sys.exit(1)

    to = sys.argv[1]
    if not to.startswith("+"):
        print("El número debe empezar con + (ej: +521234567890)")
        sys.exit(1)

    print("=== Verificando plantillas Twilio ===\n")

    templates = [
        ("notificacion_audio_v2 (UTILITY)", settings.TWILIO_UTILITY_TEMPLATE_SID),
        ("notificacion_informativa (MARKETING)", settings.TWILIO_INVITACION_TEMPLATE_SID),
        ("order_confirm_buttons", settings.TWILIO_ORDER_CONFIRM_BUTTONS_SID),
        ("appointment_confirm_buttons", settings.TWILIO_APPOINTMENT_CONFIRM_BUTTONS_SID),
    ]

    for nombre, sid in templates:
        await test_template(nombre, sid, to)


if __name__ == "__main__":
    asyncio.run(main())
