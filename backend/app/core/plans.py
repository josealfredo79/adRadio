"""Planes de IaRadio — fuente única de verdad (precios, cuotas y límites).

Rediseño 2026-10-01 (ver docs/PLANES.md): 3 planes públicos + Empresa. Las
claves internas (starter/growth/pro/enterprise) no cambian — las usan la BD
(users.current_plan), Stripe (metadata) y el gating por plan — solo cambian
nombre, precio y lo que incluye. micro y business se retiran de la venta,
pero se quedan aquí para quien ya los tuviera.

Qué cuenta cada cuota:
- `messages`: envíos que inicia el negocio por WhatsApp (campañas, parrilla,
  automatizaciones, plantillas de reapertura). Las notificaciones web y el
  portal del cliente NO cuentan: son ilimitados en todos los planes.
- `conversations`: conversaciones del bot con IA al mes (WhatsApp y web);
  una conversación = un cliente atendido en una ventana de 24 h. Es nuestro
  costo variable principal. Al pasarse, el bot NO se apaga: sigue
  contestando con un modelo más barato (ver plan_usage.py).

Los cargos de Meta por WhatsApp NO están incluidos: Meta los cobra directo
en la cuenta de WhatsApp de cada negocio.
"""

# price_usd es lo que se cobra en Stripe (moneda USD); price_mxn es el precio
# de lista que se muestra. -1 = sin límite.
PLANS: dict[str, dict] = {
    "starter": {
        "name": "Arranque", "price_mxn": 449, "price_usd": 26,
        "messages": 150, "conversations": 300, "radio": 0, "team": 1,
        "days": 30, "sellable": True,
    },
    "growth": {
        "name": "Negocio", "price_mxn": 899, "price_usd": 52,
        "messages": 500, "conversations": 1000, "radio": 4, "team": 2,
        "days": 30, "sellable": True,
    },
    "pro": {
        "name": "Crecimiento", "price_mxn": 1799, "price_usd": 104,
        "messages": 1500, "conversations": 3000, "radio": 15, "team": 5,
        "days": 30, "sellable": True,
    },
    "enterprise": {
        "name": "Empresa", "price_mxn": 4999, "price_usd": 289,
        "messages": 5000, "conversations": -1, "radio": -1, "team": -1,
        "days": 30, "sellable": True,
    },
    # Retirados de la venta (2026-10-01) — solo por compatibilidad.
    "micro": {
        "name": "Micro", "price_mxn": 299, "price_usd": 18,
        "messages": 100, "conversations": 300, "radio": 0, "team": 1,
        "days": 30, "sellable": False,
    },
    "business": {
        "name": "Business", "price_mxn": 6799, "price_usd": 399,
        "messages": 3000, "conversations": 3000, "radio": 15, "team": 5,
        "days": 30, "sellable": False,
    },
}

# Prueba gratis: 15 días (decisión 2026-10-01: 30 días era mucho costo de IA
# sin ingreso), con los límites de Arranque más 3 cuñas para probar la radio.
TRIAL_DAYS = 15
TRIAL_LIMITS = {"conversations": 300, "radio": 3, "team": 1}

# Programa Fundadores: ~30% menos, precio bloqueado 12 meses, cupo real en BD
# (migración 0048). Solo en los dos planes de entrada.
FOUNDER_PRICES: dict[str, dict] = {
    "starter": {"price_mxn": 319, "price_usd": 18},
    "growth": {"price_mxn": 629, "price_usd": 36},
}

# Paquetes extra (pago único). Las conversaciones extra no vencen: se usan
# cuando se acaba lo del plan. Los envíos se suman al saldo actual.
ADDONS: dict[str, dict] = {
    "conversations_500": {"name": "+500 conversaciones del bot", "price_mxn": 149, "price_usd": 9, "conversations": 500},
    "messages_500": {"name": "+500 envíos de campaña", "price_mxn": 99, "price_usd": 6, "messages": 500},
}

PLAN_MESSAGES: dict[str, int] = {key: p["messages"] for key, p in PLANS.items()}


def plan_limit(plan: str | None, field: str) -> int:
    """Límite de `field` (conversations/radio/team) del plan; -1 = sin límite."""
    if not plan or plan == "trial":
        return TRIAL_LIMITS.get(field, 0)
    return PLANS.get(plan, {}).get(field, TRIAL_LIMITS.get(field, 0))


def plan_name(plan: str | None) -> str:
    if not plan or plan == "trial":
        return "Prueba gratis"
    return PLANS.get(plan, {}).get("name", plan)
