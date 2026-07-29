# Levantar AdRadio (IaRadio) en local

Guía para correr la plataforma completa en una máquina de desarrollo,
sin depender de Railway. Escrita después de migrar de Twilio a Meta
Cloud API — el flujo de webhook ahora necesita una URL pública.

## Por qué venv y no Docker Compose

`docker-compose.yml` sigue siendo válido (`db`, `redis`, `backend`,
`worker`, `beat`, `frontend`, `cloudflared`), pero las imágenes locales
de `backend`/`worker`/`beat` pueden quedar desactualizadas si no se
reconstruyen tras cambios en `requirements.txt` — la capa de `pip
install` a veces se queda pegada al cache viejo incluso con `docker
compose build`. Si eso pasa, la vía rápida es correr todo con el venv
del proyecto directo en el host:

```bash
cd backend
source venv/bin/activate
pip install -r requirements.txt   # solo si el venv está desactualizado
```

Si en vez de esto prefieres Docker, la salida definitiva es forzar
`docker compose build --no-cache backend worker beat`.

## 1. Redis local

Celery (broker + backend de resultados) y el pub/sub de SSE necesitan
Redis. `REDIS_URL` en `backend/.env` apunta al Redis interno de
Railway (`redis.railway.internal`), que **no es alcanzable fuera de
Railway** — hay que sobreescribirlo con un Redis local:

```bash
redis-server --daemonize yes --port 6379
redis-cli ping   # debe responder PONG
```

## 2. Backend (FastAPI)

`DATABASE_URL` en `.env` ya apunta a la base real de Neon (la misma
que usa producción) — no hace falta levantar Postgres local, las
migraciones ya están aplicadas ahí.

```bash
cd backend
source venv/bin/activate
REDIS_URL="redis://localhost:6379/0" \
ALLOWED_HOSTS="www.iaradio.online,iaradio.online,adradio.railway.app,<tu-tunnel>.trycloudflare.com" \
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

`ALLOWED_HOSTS` importa: `AllowedHostsMiddleware` en `app/main.py`
rechaza con 400 cualquier `Host` header que no esté en la lista
(`localhost` tiene bypass propio, pero el hostname del túnel de
Cloudflare no). Actualízalo cada vez que el túnel cambie de URL.

## 3. Celery worker + beat

```bash
REDIS_URL="redis://localhost:6379/0" \
celery -A app.workers.celery_app worker --loglevel=info -Q whatsapp,campaigns,processing -c 4

REDIS_URL="redis://localhost:6379/0" \
celery -A app.workers.celery_app beat --loglevel=info -s /tmp/celerybeat-schedule
```

El flag `-s` evita el archivo `celerybeat-schedule` del repo, que
puede quedar con permisos de root si antes corrió dentro de un
contenedor Docker con bind mount.

## 4. Frontend (Vite)

El proxy de dev de `vite.config.ts` apunta a `http://backend:8000`
(hostname de Docker Compose) — fuera de Docker no resuelve. Crea
`frontend/.env` (ya está en `.gitignore`):

```
VITE_API_URL=http://localhost:8000
VITE_SITE_URL=http://localhost:5173
```

```bash
cd frontend
npm run dev -- --host
```

## 5. Túnel público para el webhook de Meta

Meta necesita poder pegarle a `POST /api/v1/webhooks/meta` desde
internet. Para pruebas rápidas, un túnel efímero de Cloudflare (no
requiere cuenta ni credenciales):

```bash
cloudflared tunnel --url http://localhost:8000
```

Imprime una URL tipo `https://<palabras-random>.trycloudflare.com`.
Configúrala en el dashboard de Meta:

- **Callback URL:** `https://<tu-tunnel>.trycloudflare.com/api/v1/webhooks/meta`
- **Verify token:** valor de `META_WEBHOOK_VERIFY_TOKEN` en `backend/.env`

Recuerda agregar ese mismo hostname a `ALLOWED_HOSTS` (paso 2) o el
handshake de Meta va a chocar con un 400 antes de llegar al webhook.

Existe también `cloudflared/config.yml` apuntando a un túnel nombrado
`adradio-prod` — requiere un `credentials.json` que no vive en el
repo (se monta aparte). Para desarrollo diario, el túnel efímero de
arriba es más simple.

## 6. Usuarios de prueba

La base de Neon ya tiene cuentas de prueba (ver `SELECT email, role
FROM users`). Si no conoces la contraseña de alguna, se puede resetear
directo con el helper de hashing del proyecto:

```python
from app.core.security import hash_password
# user.password_hash = hash_password("<nueva-contraseña>")
```

Esto escribe sobre la base real de Neon — no es una operación
reversible, hazlo solo con cuentas de prueba conocidas.

## Checklist rápido

- [ ] `redis-cli ping` → `PONG`
- [ ] `curl localhost:8000/health` → `{"status":"ok"}`
- [ ] `curl localhost:5173` → 200
- [ ] `curl https://<tunnel>/health` → 200 (si da 400 "Host no
      permitido", falta agregar el hostname a `ALLOWED_HOSTS`)
- [ ] Webhook de Meta configurado con la URL del túnel + verify token
