import sys
import os

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.workers.celery_app import celery_app

def check_workers():
    print("📡 Inspeccionando el servidor Redis de producción para buscar Workers de Celery activos...")
    try:
        inspect = celery_app.control.inspect()
        active = inspect.active()
        
        if active is None:
            print("❌ ¡Alerta crítica! No se detectó NINGÚN Celery Worker activo en producción.")
            print("   -> Esto significa que el proceso de Celery en tu servidor de Railway no está corriendo.")
        elif not active:
            print("⚠️ Hay conexión con Celery pero la lista de workers activos está vacía.")
        else:
            print(f"✅ ¡Workers de Celery activos detectados en producción!: {list(active.keys())}")
            for worker, tasks in active.items():
                print(f"   - Worker: {worker} | Tareas ejecutándose actualmente: {len(tasks)}")
                
        # También inspeccionamos las colas programadas (scheduled/reserved)
        scheduled = inspect.scheduled()
        print(f"\n⏰ Tareas programadas en cola (esperando countdown): {scheduled}")
        
        # También inspeccionamos las tareas registradas
        registered = inspect.registered()
        if registered:
            print(f"📋 El worker tiene registradas {len(list(registered.values())[0])} tareas en el broker.")
            
    except Exception as e:
        print(f"❌ Error al intentar conectar e inspeccionar Celery: {e}")

if __name__ == "__main__":
    check_workers()
