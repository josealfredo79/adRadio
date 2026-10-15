"""El worker corre tareas en hilos (`--pool threads -c 4`, railway.json) y cada
una arma su propio ciclo con asyncio.run (run_async). Con un grupo de
conexiones compartido, dos tareas al mismo tiempo tronaban con "Lock ... is
bound to a different event loop" (19 veces en 2 días en prod, 13/14-oct:
recordatorios de citas, campañas y ofertas que caen en el mismo segundo)."""
import asyncio
import threading

from sqlalchemy import text

from app.database import CeleryAsyncSessionLocal
from app.workers.task_helpers.common import run_async


def test_tareas_simultaneas_en_hilos_no_comparten_conexiones():
    errors: list[BaseException] = []
    start = threading.Barrier(6)

    def task():
        async def _run():
            for _ in range(5):
                async with CeleryAsyncSessionLocal() as db:
                    await db.execute(text("SELECT pg_sleep(0.02)"))
                await asyncio.sleep(0)

        try:
            start.wait()
            run_async(_run())
        except BaseException as e:
            errors.append(e)

    threads = [threading.Thread(target=task, daemon=True) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    # Con el motor compartido no tronaba siempre: a veces se quedaba trabado para siempre.
    assert not any(t.is_alive() for t in threads), "tareas trabadas esperando conexión"
    assert not errors, errors[:2]
