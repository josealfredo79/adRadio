import asyncio
import sys
import redis.asyncio as aioredis
from redis.exceptions import ConnectionError, TimeoutError

async def main():
    print("\n" + "="*50)
    print("🛠️  PRUEBA DE CONEXIÓN A REDIS PÚBLICO (AISLADA) 🛠️")
    print("="*50)
    
    # Pedir la URL al usuario
    redis_url = input("\n👉 Por favor, pega aquí la REDIS_PUBLIC_URL de Railway: ").strip()
    
    if not redis_url:
        print("❌ No ingresaste ninguna URL. Saliendo...")
        sys.exit(1)
        
    print(f"\nIntentando conectar a: {redis_url[:15]}... (oculto por seguridad)")
    
    try:
        # Intentamos conectar igual que lo hace el backend
        pool = await aioredis.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=10,
            socket_timeout=10,
        )
        
        # Ping de prueba
        respuesta = await pool.ping()
        
        if respuesta:
            print("\n✅ ¡ÉXITO TOTAL! Conexión establecida perfectamente.")
            print("Si esto funcionó aquí, la URL es correcta y debe funcionar en el servidor.")
        else:
            print("\n⚠️ Conectó, pero no respondió al Ping.")
            
        await pool.aclose()
        
    except Exception as e:
        print("\n❌ FALLO LA CONEXIÓN.")
        print(f"Motivo técnico: {type(e).__name__} -> {e}")
        print("\n💡 Si ves un error de SSL, avísame. Si es Timeout, la URL podría estar mal.")

if __name__ == "__main__":
    asyncio.run(main())
