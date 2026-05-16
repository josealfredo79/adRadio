import asyncio
import sys
import os

# Agregamos el directorio actual al path para que encuentre el módulo app
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.services.twilio_service import send_whatsapp

async def main():
    if len(sys.argv) < 2:
        print("Uso: python test_whatsapp.py <numero_destino>")
        sys.exit(1)
        
    numero = sys.argv[1]
    if not numero.startswith("+"):
        print("El número debe incluir el código de país y empezar con +, por ejemplo: +521234567890")
        sys.exit(1)

    print(f"Enviando mensaje de prueba a {numero}...")
    sid = await send_whatsapp(numero, "Hola, esta es una prueba desde el entorno de IaRadio.")
    
    if sid:
        print(f"Mensaje enviado exitosamente. SID: {sid}")
    else:
        print("Hubo un error al enviar el mensaje. Revisa los logs.")

if __name__ == "__main__":
    asyncio.run(main())
