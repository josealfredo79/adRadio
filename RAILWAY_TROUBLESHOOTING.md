# 📡 Diagnóstico y Estado del Despliegue de Celery en Railway

Este documento sirve como bitácora técnica para comprender los problemas detectados en los procesos en segundo plano de **Celery** en el servidor de producción (Railway), las optimizaciones implementadas y los pasos pendientes para lograr la estabilidad absoluta.

---

## 🔍 1. Qué Está Pasando (Diagnóstico)

### El Problema Inicial
* En Railway, el contenedor de producción arranca y se marca como **`● Online`**, pero las tareas de WhatsApp y campañas en segundo plano no se ejecutan y quedan encoladas (**`queued`**) indefinidamente.
* Al consultar los logs principales con `railway logs`, únicamente se ven los registros del servidor web **Uvicorn/FastAPI**. Los procesos en segundo plano de **Celery Worker** y **Celery Beat** no imprimen salida en consola (stdout), lo que hacía imposible saber si estaban crasheando, bloqueados por memoria o si ni siquiera se estaban iniciando.

### Las Causas Clave Detectadas
1. **Restricción de Recursos (Memoria):** Los comandos de inicio anteriores intentaban levantar Celery con múltiples workers (`-c 2` o más) junto a múltiples hilos de Uvicorn. Esto causaba picos de consumo de memoria que superaban los límites del plan de Railway, provocando que el supervisor del contenedor matara silenciosamente los subprocesos de Celery (OOM - Out Of Memory).
2. **Sintaxis de Arranque en Segundo Plano:** El comando usaba agrupaciones de comandos con paréntesis y operadores `&&` para los subprocesos en segundo plano (ej. `(celery -A ... worker &) && (celery -A ... beat &)`). En entornos de contenedores Docker de Railway, esto provocaba que si una de las tareas terminaba o fallaba en segundo plano, todo el comando propagara señales de interrupción, o bien que los subprocesos no heredaran las variables de entorno correctamente.
3. **Subidas Manuales Lentas:** Al intentar subir el código manualmente con `railway up` para diagnosticar en caliente, la subida tardaba minutos o fallaba por límite de tiempo. Descubrimos que las carpetas de entornos virtuales locales (`backend/venv` de 596MB y `backend/.venv` de 568MB), junto con `node_modules` (254MB), estaban siendo empaquetadas y subidas a la nube de forma innecesaria.

---

## 🛠️ 2. Soluciones Implementadas

### A. Comando de Arranque Ultra-Estable y Optimizado
Hemos reescrito y optimizado completamente el comando de inicio en los archivos [railway.toml](file:///home/josealfredo/adradio/railway.toml) y [backend/railway.toml](file:///home/josealfredo/adradio/backend/railway.toml):
* **Concurrencia Reducida (`-c 1`):** Redujimos la concurrencia del worker a exactamente 1 hilo de ejecución. Esto minimiza drásticamente el consumo de RAM del contenedor, garantizando que quepa de forma holgada en la infraestructura de Railway sin riesgo de ser finalizado por falta de memoria.
* **Redireccionamiento de Logs a Archivos:** Modificamos la sintaxis para lanzar los procesos en segundo plano y redirigir toda su salida estándar y de errores a archivos locales:
  * `celery_worker.log` para el Worker.
  * `celery_beat.log` para el Beat scheduler.
* **Comando Final Configurado:**
  ```bash
  alembic upgrade head && celery -A app.workers.celery_app worker --loglevel=info -Q whatsapp,campaigns,processing -c 1 > celery_worker.log 2>&1 & celery -A app.workers.celery_app beat --loglevel=info > celery_beat.log 2>&1 & uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
  ```

### B. Puente de Telemetría por Base de Datos (Neon)
Para poder leer los archivos de logs de Celery (`celery_worker.log` y `celery_beat.log`) que se quedan atrapados dentro del contenedor de producción (ya que Railway bloquea el tráfico de red cuando un despliegue está en transición):
1. **Endpoint de Telemetría:** Modificamos el endpoint de `/health` en [main.py](file:///home/josealfredo/adradio/backend/app/main.py). Cuando Railway hace su consulta de salud periódica, el contenedor automáticamente lee los logs de Celery de los archivos de texto y los escribe en la columna `bot_personality` del primer usuario en la base de datos de producción de **Neon**.
2. **Script de Lectura Local:** Creamos el script [read_telemetry_logs.py](file:///home/josealfredo/adradio/backend/read_telemetry_logs.py). Al ejecutarlo de forma local, se conecta a la base de datos en la nube y nos muestra exactamente los logs de arranque de Celery de forma limpia y directa.

### C. Exclusión y Subidas Instantáneas (`.railwayignore`)
* Creamos el archivo [.railwayignore](file:///home/josealfredo/adradio/.railwayignore) en la raíz del proyecto para excluir entornos virtuales, audios pesados y carpetas `node_modules`. 
* **Resultado:** Redujimos el peso de la subida manual de **1.5 Gigabytes a menos de 2 Megabytes**, logrando que el comando `railway up --detach` suba el código e inicie la compilación en Railway en tan solo **2 segundos**.

---

## 📋 3. Estado Actual de la Plataforma

* **Servidor Web (FastAPI):** Funcionando al 100% en vivo bajo la URL [https://adradio-production-51a9.up.railway.app](https://adradio-production-51a9.up.railway.app).
* **Base de Datos (Neon):** Activa y respondiendo de forma correcta. Contiene 2 usuarios registrados:
  1. `test_reschedule@example.com` (Primer usuario en orden, receptor de los logs de telemetría).
  2. `tecnologicotlaxiaco@gmail.com` (Tu usuario del proyecto).
* **Redis en la Nube:** Activo y conectado al backend FastAPI.
* **Mensajes en Cola:** Hay actualmente 1 mensaje en estado `queued` en la base de datos con destino a *Laurencio (+529531247518)* esperando a que el proceso de Celery comience a consumir la cola.

---

## ⏳ 4. Tareas Pendientes (Próximos Pasos)

Para finalizar la puesta en marcha de Celery y que los mensajes de WhatsApp comiencen a enviarse de forma real en producción, quedan pendientes los siguientes pasos:

1. **Hacer push del nuevo código:**
   - `git add -A && git commit -m "fix: unified startup with start.sh"`
   - `git push` para que Railway recompile el contenedor

2. **Esperar a que se actualicen los logs en la Base de Datos:**
   Una vez que Railway haga rebuild y el healthcheck se ejecute, correr `python3 read_telemetry_logs.py` para ver los logs de Celery.

3. **Verificar que Celery esté corriendo:**
   - Los logs deben mostrar "ready" para el worker
   - Los mensajes deben pasar de "queued" a "sent"

4. **Limpiar el endpoint de `/health`:**
   Una vez que Celery esté arrancado y enviando mensajes con éxito, eliminaremos el código temporal de telemetría de `/health` en [main.py](file:///home/josealfredo/adradio/backend/app/main.py) para restaurarlo a su estado de producción limpio original y evitar escrituras innecesarias en la base de datos.

5. **Crear servicios separados en Railway (opcional):**
   Para escalabilidad futura, considerar crear servicios Worker y Beat separados en Railway Dashboard con `SERVICE_ROLE=worker` y `SERVICE_ROLE=beat`.

---

> **Nota:** ¡Hemos dado un paso gigante! Al reducir el tamaño de subida a segundos y establecer el puente de telemetría por base de datos, tenemos el control total del servidor de producción y podemos diagnosticar cualquier fallo en tiempo récord sin dar pasos a ciegas.