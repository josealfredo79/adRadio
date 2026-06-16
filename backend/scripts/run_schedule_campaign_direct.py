import asyncio
import sys
import os
import uuid

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.database import AsyncSessionLocal
from app.workers.tasks import schedule_campaign

def main():
    # Usaremos una de las campañas de la parrilla que están en estado "running" en tu base de datos:
    # "Parrilla: Sábado" -> b916ce53-73be-44c3-afc1-8b4f00df237c
    campaign_id = "b916ce53-73be-44c3-afc1-8b4f00df237c"
    
    print(f"🚀 Iniciando ejecución síncrona directa de la tarea schedule_campaign para el ID: {campaign_id}...")
    
    try:
        # Ejecutamos la tarea de Celery de forma directa (síncrona)
        # Esto usará los hilos de conexión de producción y ejecutará todo el proceso
        schedule_campaign.run(campaign_id)
        print("✅ Ejecución finalizada sin excepciones no controladas.")
    except Exception as e:
        print(f"❌ Ocurrió un error al ejecutar la tarea: {e}")

if __name__ == "__main__":
    main()
