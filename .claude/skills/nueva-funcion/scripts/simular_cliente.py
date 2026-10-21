#!/usr/bin/env python3
"""Clientes simulados contra el chat web REAL (POST /widget/chat, el mismo que
usa el navegador): agente con herramientas, catálogo, citas, pedidos y la base
de conocimiento, con los modelos de IA de verdad. A diferencia del Laboratorio
(que solo prueba answer_with_rag), aquí el cliente está verificado con su link
del portal, así que también entra el agente del cliente (customer_agent.py).

Todo corre en una base Postgres NUEVA en Docker (adradio-sim-pg, puerto 55433)
y Redis local (56379, base 5). Nunca toca producción: del backend/.env solo se
leen las llaves de IA y de Voyage. No manda WhatsApp (el chat web no lo hace).

Uso (desde la raíz del repo):
  backend/.venv/bin/python .claude/skills/nueva-funcion/scripts/simular_cliente.py escenarios.json [--sin-juez]

escenarios.json:
{
  "negocio": {                       # opcional; si falta, una estética de ejemplo
    "business_name": "Estética Lupita", "business_category": "estética", "city": "Tlaxiaco",
    "delivers_home": true,             # opcional: true / false / null (sin definir = solo recoger)
    "business_hours": {"mon": ["09:00", "19:00"], ...},
    "appointment_services": [{"name": "Corte", "minutes": 30}],
    "productos": [{"name": "Shampoo", "price": 120}],
    "conocimiento": "Texto libre de la base de conocimiento..."
  },
  "escenarios": [
    {"nombre": "agenda corte", "mensajes": ["hola", "quiero un corte mañana a las 11", "Sí, confírmalo"],
     "forbid": ["Messenger"], "espera": {"citas": 1}},
    {"nombre": "regatea", "persona": "Eres un cliente que regatea todo...", "turnos": 4}
  ]
}
"mensajes" = guion fijo; "persona" = un modelo hace de cliente (hasta "turnos").
"espera" revisa la base al final: {"citas": n, "pedidos": n}.
"""
import asyncio
import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[4] / "backend"
PG_PORT = 55433
PG_NAME = "adradio-sim-pg"
DB_URL = f"postgresql+asyncpg://postgres:pg@localhost:{PG_PORT}/adradio?ssl=disable"

DEFAULT_BUSINESS = {
    "business_name": "Estética Lupita",
    "business_category": "estética",
    "city": "Tlaxiaco",
    "business_hours": {d: ["09:00", "19:00"] for d in ("mon", "tue", "wed", "thu", "fri", "sat")} | {"sun": None},
    "appointment_services": [{"name": "Corte de cabello", "minutes": 30}, {"name": "Tinte", "minutes": 90}],
    "productos": [{"name": "Shampoo de keratina", "price": 180}, {"name": "Tratamiento capilar", "price": 350}],
    "conocimiento": (
        "Estamos en Calle Hidalgo 12, centro de Tlaxiaco. Corte de dama $120, corte de caballero $80, "
        "tinte desde $450. Aceptamos efectivo y transferencia. No hacemos servicio a domicilio. "
        "Estacionamiento en la calle."
    ),
}


def setup_env() -> None:
    # Lo que ya venga en el entorno gana: los *_MODEL del .env local suelen
    # estar viejos (los de producción: `railway variables -s adRadio --kv | grep _MODEL=`).
    for line in (BACKEND / ".env").read_text().splitlines():
        key, _, value = line.strip().partition("=")
        if re.fullmatch(r"[A-Z_]*(API_KEY|API_TOKEN|ACCOUNT_ID|_BASE_URL|_MODEL)", key):
            os.environ.setdefault(key, value.strip().strip('"'))
    if os.environ.get("USAR_OPENROUTER") != "1":
        # La llave local es la de producción y su cuota gratis (~50/día) es de los clientes reales.
        os.environ.pop("OPENROUTER_API_KEY", None)
    os.environ["APP_ENV_FILE"] = ""  # que app/config.py no lea el .env (producción)
    os.environ["DATABASE_URL"] = DB_URL
    os.environ["REDIS_URL"] = "redis://localhost:56379/5"
    os.environ.setdefault("SECRET_KEY", "simular-cliente")
    sys.path.insert(0, str(BACKEND))


def run(*cmd: str, **kw) -> None:
    subprocess.run(cmd, check=True, capture_output=True, **kw)


def fresh_database() -> None:
    subprocess.run(["docker", "rm", "-f", PG_NAME], capture_output=True)
    run("docker", "run", "-d", "--name", PG_NAME, "-e", "POSTGRES_PASSWORD=pg", "-e", "POSTGRES_DB=adradio",
        "-p", f"{PG_PORT}:5432", "pgvector/pgvector:pg16")
    names = subprocess.run(["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True).stdout.split()
    if "adradio-test-redis" not in names:
        subprocess.run(["docker", "rm", "-f", "adradio-test-redis"], capture_output=True)
        run("docker", "run", "-d", "--name", "adradio-test-redis", "-p", "56379:6379", "redis:7-alpine")
    while subprocess.run(["docker", "exec", PG_NAME, "pg_isready", "-U", "postgres"], capture_output=True).returncode:
        pass
    # pg_isready contesta antes de que la base acepte conexiones de fuera.
    for _ in range(30):
        if subprocess.run([str(BACKEND / ".venv/bin/alembic"), "upgrade", "head"], cwd=BACKEND,
                          capture_output=True, env=os.environ).returncode == 0:
            return
        subprocess.run(["sleep", "1"])
    raise SystemExit("No se pudo migrar la base de simulación")


async def seed(spec: dict):
    from app.database import AsyncSessionLocal
    from app.models.knowledge_base import KnowledgeBase
    from app.models.product import Product
    from app.models.user import User
    from app.services.embedding_service import chunk_text, get_embedding

    biz = DEFAULT_BUSINESS | spec
    async with AsyncSessionLocal() as db:
        user = User(email=f"sim-{uuid.uuid4().hex[:8]}@test.com", password_hash="x",
                    business_name=biz["business_name"], business_category=biz["business_category"],
                    city=biz["city"], business_hours=biz["business_hours"],
                    appointment_services=biz["appointment_services"], subscription_status="active",
                    customer_agent_enabled=True, delivers_home=biz.get("delivers_home"))
        db.add(user)
        await db.flush()
        for p in biz["productos"]:
            db.add(Product(advertiser_id=user.id, name=p["name"], price=p.get("price"),
                           description=p.get("description")))
        for chunk in chunk_text(biz["conocimiento"]):
            db.add(KnowledgeBase(advertiser_id=user.id, filename="simulacion.txt", file_type="txt",
                                 raw_text=biz["conocimiento"], chunk_text=chunk,
                                 embedding=await get_embedding(chunk), processing_status="ready"))
        await db.commit()
        return user, biz


async def new_contact(user) -> tuple[str, str]:
    from app.database import AsyncSessionLocal
    from app.models.contact import Contact
    from app.services.portal_service import make_portal_token

    async with AsyncSessionLocal() as db:
        contact = Contact(advertiser_id=user.id, name="Cliente simulado",
                          phone=f"+5215{uuid.uuid4().int % 10**9:09d}")
        db.add(contact)
        await db.commit()
        return str(contact.id), make_portal_token(contact.id)


async def db_effects(user_id, contact_id: str) -> dict:
    from sqlalchemy import func, select

    from app.database import AsyncSessionLocal
    from app.models.appointment import Appointment
    from app.models.order import Order

    async with AsyncSessionLocal() as db:
        cid = uuid.UUID(contact_id)
        citas = await db.scalar(select(func.count()).select_from(Appointment).where(
            Appointment.advertiser_id == user_id, Appointment.contact_id == cid))
        pedidos = await db.scalar(select(func.count()).select_from(Order).where(
            Order.advertiser_id == user_id, Order.contact_id == cid))
        return {"citas": citas, "pedidos": pedidos}


async def run_scenario(client, user, biz: dict, sc: dict, judge: bool) -> bool:
    from app.services.lab.personas import Persona
    from app.services.lab.simulator import _END_MARKER, generate_persona_message

    contact_id, token = await new_contact(user)
    session = str(uuid.uuid4())
    transcript: list[dict] = []
    persona = Persona(key="sim", label=sc["nombre"], goal=sc.get("objetivo", sc["nombre"]),
                      system_prompt=sc.get("persona", "Eres un cliente de WhatsApp. Español mexicano casual."))
    script = list(sc.get("mensajes", []))
    turns = len(script) if script else sc.get("turnos", 4)

    print(f"\n=== {sc['nombre']} ===")
    for _ in range(turns):
        if script:
            msg = script.pop(0)
        else:
            msg = (await generate_persona_message(persona, biz, transcript)).strip()
            if not msg or msg == _END_MARKER:
                break
        resp = await client.post(f"/api/v1/widget/chat/{user.id}",
                                 json={"message": msg[:500], "session_id": session, "portal_token": token})
        data = resp.json() if resp.status_code == 200 else {"reply": f"[HTTP {resp.status_code}] {resp.text[:200]}"}
        reply = data.get("reply") or ("[pasó al dueño]" if data.get("handoff") else "")
        transcript += [{"role": "user", "content": msg}, {"role": "assistant", "content": reply}]
        print(f"  Cliente: {msg}\n  Bot:     {reply}" + ("\n           [botones Sí / No]" if data.get("confirm") else ""))

    problems = []
    bot_text = " ".join(m["content"] for m in transcript if m["role"] == "assistant").lower()
    problems += [f"aparece «{w}»" for w in sc.get("forbid", []) if w.lower() in bot_text]
    problems += [f"falta «{w}»" for w in sc.get("expect", []) if w.lower() not in bot_text]
    problems += [f"error HTTP: {m['content'][:80]}" for m in transcript if m["content"].startswith("[HTTP")]
    effects = await db_effects(user.id, contact_id)
    for key, want in (sc.get("espera") or {}).items():
        if effects.get(key) != want:
            problems.append(f"{key}: esperaba {want}, hay {effects.get(key)}")
    print(f"  Base al final: {effects}")

    if judge and transcript:
        from app.database import AsyncSessionLocal
        from app.services.lab.judge import evaluate_transcript

        async with AsyncSessionLocal() as db:
            verdict = await evaluate_transcript(persona, transcript, user, db)
        print(f"  Juez: {verdict.get('score')}/100 — {verdict.get('summary')}")
        for f in verdict.get("findings", []):
            print(f"    [{f.get('severity')}] {f.get('type')}: {f.get('evidence')} → {f.get('suggestion')}")
            if f.get("severity") == "alta":
                problems.append(f"juez: {f.get('type')} grave")

    print("  " + ("MAL: " + "; ".join(problems) if problems else "OK"))
    return not problems


async def main(path: str, judge: bool) -> int:
    spec = json.loads(Path(path).read_text())
    setup_env()
    fresh_database()

    import httpx

    from app.core.rate_limiter import limiter
    from app.main import app

    limiter.enabled = False  # 15/min por IP: todo sale de "127.0.0.1"
    user, biz = await seed(spec.get("negocio", {}))
    ok = 0
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://sim",
                                 timeout=120) as client:
        for sc in spec["escenarios"]:
            ok += await run_scenario(client, user, biz, sc, judge)
    total = len(spec["escenarios"])
    print(f"\n{ok}/{total} escenarios bien")
    return 0 if ok == total else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sys.exit(asyncio.run(main(sys.argv[1], judge="--sin-juez" not in sys.argv)))
