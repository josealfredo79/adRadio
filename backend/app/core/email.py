import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import settings

logger = logging.getLogger(__name__)


async def send_email(to: str, subject: str, html_body: str) -> bool:
    """Send email via SMTP. Non-blocking — runs smtplib in a thread executor."""
    if not settings.SMTP_HOST:
        logger.debug("[EMAIL DEV] To: %s | Subject: %s", to, subject)
        return True

    def _send() -> bool:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = settings.FROM_EMAIL
            msg["To"] = to
            msg.attach(MIMEText(html_body, "html"))

            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
                server.starttls()
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.sendmail(settings.FROM_EMAIL, to, msg.as_string())
            return True
        except Exception as e:
            logger.error("[EMAIL ERROR] %s", e)
            return False

    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _send)
    except Exception as e:
        logger.error("[EMAIL EXECUTOR ERROR] %s", e)
        return False


async def send_verification_email(to: str, code: str) -> bool:
    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:0 auto">
      <h2 style="color:#6366f1">IaRadio — Verifica tu email</h2>
      <p>Tu código de verificación es:</p>
      <div style="font-size:36px;font-weight:bold;letter-spacing:8px;
                  text-align:center;padding:20px;background:#f1f5f9;
                  border-radius:8px;color:#1e293b">
        {code}
      </div>
      <p style="color:#64748b;font-size:13px">
        Este código expira en 10 minutos. No lo compartas con nadie.
      </p>
    </div>
    """
    return await send_email(to, "Verifica tu cuenta de IaRadio", html)


async def send_password_reset_email(to: str, token: str) -> bool:
    reset_url = f"https://app.iaradio.app/reset-password?token={token}"
    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:0 auto">
      <h2 style="color:#6366f1">IaRadio — Recuperar contraseña</h2>
      <p>Haz clic en el botón para restablecer tu contraseña:</p>
      <a href="{reset_url}"
         style="display:inline-block;padding:12px 24px;background:#6366f1;
                color:white;border-radius:8px;text-decoration:none;margin:16px 0">
        Restablecer contraseña
      </a>
      <p style="color:#64748b;font-size:13px">
        Este enlace expira en 1 hora. Si no solicitaste esto, ignora este email.
      </p>
    </div>
    """
    return await send_email(to, "Recupera tu contraseña de IaRadio", html)


async def send_new_order_email(
    to: str,
    order_number: int,
    business_name: str,
    items_raw: str,
    customer_name: str,
    customer_phone: str,
    delivery_address: str,
    payment_method: str,
) -> bool:
    """Notify the business owner about a new confirmed order."""
    html = f"""
    <div style="font-family:sans-serif;max-width:520px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;border:1px solid #e2e8f0">
      <!-- Header -->
      <div style="background:linear-gradient(135deg,#6366f1,#a855f7);padding:24px 28px">
        <h1 style="margin:0;color:#fff;font-size:22px;font-weight:800">
          📦 Nuevo pedido #{order_number:04d}
        </h1>
        <p style="margin:4px 0 0;color:rgba(255,255,255,0.8);font-size:14px">{business_name}</p>
      </div>

      <!-- Body -->
      <div style="padding:24px 28px">
        <!-- Items -->
        <div style="background:#f8fafc;border-radius:8px;padding:16px;margin-bottom:16px">
          <p style="margin:0 0 4px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#94a3b8">Pedido</p>
          <p style="margin:0;font-size:18px;font-weight:700;color:#1e293b">{items_raw}</p>
        </div>

        <!-- Details grid -->
        <table style="width:100%;border-collapse:collapse;font-size:14px">
          <tr>
            <td style="padding:8px 0;color:#64748b;width:40%">👤 Cliente</td>
            <td style="padding:8px 0;font-weight:600;color:#1e293b">{customer_name}</td>
          </tr>
          <tr>
            <td style="padding:8px 0;color:#64748b">📱 WhatsApp</td>
            <td style="padding:8px 0;font-weight:600;color:#1e293b">{customer_phone}</td>
          </tr>
          <tr>
            <td style="padding:8px 0;color:#64748b">📍 Dirección</td>
            <td style="padding:8px 0;font-weight:600;color:#1e293b">{delivery_address}</td>
          </tr>
          <tr>
            <td style="padding:8px 0;color:#64748b">💳 Pago</td>
            <td style="padding:8px 0;font-weight:600;color:#1e293b">{payment_method}</td>
          </tr>
        </table>
      </div>

      <!-- Footer -->
      <div style="background:#f8fafc;padding:16px 28px;border-top:1px solid #e2e8f0">
        <p style="margin:0;font-size:12px;color:#94a3b8;text-align:center">
          Puedes ver todos tus pedidos en tu panel de IaRadio.
        </p>
      </div>
    </div>
    """
    subject = f"🛒 Nuevo pedido #{order_number:04d} — {business_name}"
    return await send_email(to, subject, html)

