"""Clientes de un negocio que contestan al número central de IaRadio.

El número central les manda el código de /mi y del QR de mostrador. Si el
cliente le contesta ("gracias", una duda de su cita), antes caía en el bot de
la cuenta IaRadio, que es de VENTAS: le ofrecía planes y llenaba el Inbox de
IaRadio con clientes ajenos. Ahora, si el número es cliente de algún negocio
(que no sea la propia cuenta IaRadio), se le contesta corto con el link a su
negocio. Un interesado real, que no es cliente de nadie, sigue con el bot.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.contact import Contact
from app.models.user import User
from app.services.customer_account import canonical_phone, contact_phone_canonical
from app.services.portal_service import portal_url

MAX_LISTED = 3


async def customer_redirect_reply(
    db: AsyncSession, number: str, *, central_account_id: uuid.UUID | None
) -> str | None:
    """El mensaje para mandarlo con su negocio, o None si no es cliente de
    ningún negocio (entonces le contesta el bot de ventas como siempre)."""
    phone = canonical_phone(number)
    if not phone or not settings.SECRET_KEY:
        return None
    query = (
        select(Contact.id, User.business_name)
        .join(User, User.id == Contact.advertiser_id)
        .where(contact_phone_canonical() == phone, Contact.status != "blocked")
        .order_by(Contact.last_interaction.desc().nulls_last(), Contact.created_at.desc())
    )
    if central_account_id is not None:
        query = query.where(Contact.advertiser_id != central_account_id)
    rows = (await db.execute(query)).all()
    if not rows:
        return None

    intro = "Hola 👋 Este número de IaRadio solo envía códigos y avisos, aquí nadie lee los mensajes."
    if len(rows) == 1:
        contact_id, name = rows[0]
        return f"{intro}\n\nPara hablar con {name or 'tu negocio'}, entra aquí:\n{portal_url(contact_id)}"
    if len(rows) > MAX_LISTED and settings.CUSTOMER_ACCOUNT_ENABLED:
        base = (settings.FRONTEND_URL or "https://www.iaradio.online").rstrip("/")
        return f"{intro}\n\nTodos tus negocios están aquí:\n{base}/mi"
    lines = "\n".join(f"• {name or 'Tu negocio'}: {portal_url(contact_id)}" for contact_id, name in rows[:MAX_LISTED])
    return f"{intro}\n\nPara hablar con tu negocio, entra a su chat:\n{lines}"
