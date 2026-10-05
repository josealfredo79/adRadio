"""Cómo le paga el cliente su pedido al negocio: su propio link de cobro
(Mercado Pago, Stripe, Clip…) y/o sus datos de transferencia
(users.payment_link / users.payment_transfer). IaRadio no cobra ni toca el
dinero; solo manda los datos al confirmar el pedido. El dueño marca el
pedido como pagado cuando le llega."""
import unicodedata

from app.models.user import User


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def payment_lines(advertiser: User, method: str | None) -> str:
    """Las líneas para el final de la confirmación, según cómo dijo que va a
    pagar. Vacío si paga en efectivo o el negocio no dio esos datos."""
    m = _plain(method or "")
    link = (advertiser.payment_link or "").strip()
    transfer = (advertiser.payment_transfer or "").strip()
    if any(w in m for w in ("tarjeta", "link", "liga", "mercado", "credito", "debito", "en linea")) and link:
        return f"\n\n💳 Paga aquí: {link}"
    if "transfer" in m or "spei" in m or "deposit" in m:
        if transfer:
            return f"\n\n🏦 Datos para transferir: {transfer}"
        if link:
            return f"\n\n💳 Paga aquí: {link}"
    return ""


def payment_methods_line(advertiser: User) -> str:
    """Para el prompt del agente: qué formas de pago tiene de verdad."""
    ways = ["efectivo"]
    if advertiser.payment_link:
        ways.append("tarjeta (con su link de pago)")
    if advertiser.payment_transfer:
        ways.append("transferencia")
    return ", ".join(ways)
