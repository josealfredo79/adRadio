import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import settings

logger = logging.getLogger(__name__)


async def send_email(to: str, subject: str, html_body: str, _retries: int = 3) -> bool:
    """Send email via SMTP. Non-blocking — runs smtplib in a thread executor."""
    if not settings.SMTP_HOST:
        logger.debug("[EMAIL DEV] To: %s | Subject: %s", to, subject)
        return True

    def _send() -> bool:
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

    for attempt in range(_retries):
        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, _send)
        except Exception as e:
            logger.error("[EMAIL ERROR] Attempt %d/%d: %s", attempt + 1, _retries, e)
            if attempt < _retries - 1:
                await asyncio.sleep(2 ** attempt)
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
    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
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


async def send_new_appointment_email(
    to: str,
    business_name: str,
    service: str,
    customer_name: str,
    customer_phone: str,
    fecha: str,
    hora: str,
) -> bool:
    """Notify the business owner about a new self-service-booked appointment."""
    html = f"""
    <div style="font-family:sans-serif;max-width:520px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;border:1px solid #e2e8f0">
      <div style="background:linear-gradient(135deg,#6366f1,#a855f7);padding:24px 28px">
        <h1 style="margin:0;color:#fff;font-size:22px;font-weight:800">
          📅 Nueva cita agendada
        </h1>
        <p style="margin:4px 0 0;color:rgba(255,255,255,0.8);font-size:14px">{business_name}</p>
      </div>

      <div style="padding:24px 28px">
        <div style="background:#f8fafc;border-radius:8px;padding:16px;margin-bottom:16px">
          <p style="margin:0 0 4px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#94a3b8">Servicio</p>
          <p style="margin:0;font-size:18px;font-weight:700;color:#1e293b">{service}</p>
        </div>

        <table style="width:100%;border-collapse:collapse;font-size:14px">
          <tr>
            <td style="padding:8px 0;color:#64748b;width:40%">👤 Cliente</td>
            <td style="padding:8px 0;font-weight:600;color:#1e293b">{customer_name}</td>
          </tr>
          <tr>
            <td style="padding:8px 0;color:#64748b">📱 Teléfono</td>
            <td style="padding:8px 0;font-weight:600;color:#1e293b">{customer_phone}</td>
          </tr>
          <tr>
            <td style="padding:8px 0;color:#64748b">🕐 Fecha</td>
            <td style="padding:8px 0;font-weight:600;color:#1e293b">{fecha} a las {hora}</td>
          </tr>
        </table>
      </div>

      <div style="background:#f8fafc;padding:16px 28px;border-top:1px solid #e2e8f0">
        <p style="margin:0;font-size:12px;color:#94a3b8;text-align:center">
          Puedes ver todas tus citas en tu panel de IaRadio.
        </p>
      </div>
    </div>
    """
    subject = f"📅 Nueva cita — {business_name}"
    return await send_email(to, subject, html)


async def send_campaign_sent_email(
    to: str,
    business_name: str,
    campaign_name: str,
    sent_count: int,
) -> bool:
    """Notify the advertiser that their campaign has started sending."""
    html = f"""
    <div style="font-family:sans-serif;max-width:520px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;border:1px solid #e2e8f0">
      <div style="background:linear-gradient(135deg,#6366f1,#a855f7);padding:24px 28px">
        <h1 style="margin:0;color:#fff;font-size:22px;font-weight:800">
          📢 Campaña enviada
        </h1>
        <p style="margin:4px 0 0;color:rgba(255,255,255,0.8);font-size:14px">{business_name}</p>
      </div>
      <div style="padding:24px 28px">
        <div style="background:#f8fafc;border-radius:8px;padding:16px;margin-bottom:16px">
          <p style="margin:0 0 4px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#94a3b8">Campaña</p>
          <p style="margin:0;font-size:18px;font-weight:700;color:#1e293b">{campaign_name}</p>
        </div>
        <div style="background:#f0fdf4;border-radius:8px;padding:16px;text-align:center">
          <p style="margin:0;font-size:32px;font-weight:800;color:#16a34a">{sent_count}</p>
          <p style="margin:0;font-size:13px;color:#64748b">mensajes enviados</p>
        </div>
      </div>
      <div style="background:#f8fafc;padding:16px 28px;border-top:1px solid #e2e8f0">
        <p style="margin:0;font-size:12px;color:#94a3b8;text-align:center">
          Puedes ver el progreso en tu panel de IaRadio.
        </p>
      </div>
    </div>
    """
    subject = f"📢 Campaña enviada — {campaign_name}"
    return await send_email(to, subject, html)


async def send_campaign_completed_email(
    to: str,
    business_name: str,
    campaign_name: str,
    stats_dict: dict,
) -> bool:
    """Notify the advertiser that their campaign has completed with stats."""
    sent = stats_dict.get("sent", 0)
    delivered = stats_dict.get("delivered", 0)
    replied = stats_dict.get("replied", 0)
    html = f"""
    <div style="font-family:sans-serif;max-width:520px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;border:1px solid #e2e8f0">
      <div style="background:linear-gradient(135deg,#6366f1,#a855f7);padding:24px 28px">
        <h1 style="margin:0;color:#fff;font-size:22px;font-weight:800">
          ✅ Campaña finalizada
        </h1>
        <p style="margin:4px 0 0;color:rgba(255,255,255,0.8);font-size:14px">{business_name}</p>
      </div>
      <div style="padding:24px 28px">
        <div style="background:#f8fafc;border-radius:8px;padding:16px;margin-bottom:16px">
          <p style="margin:0 0 4px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#94a3b8">Campaña</p>
          <p style="margin:0;font-size:18px;font-weight:700;color:#1e293b">{campaign_name}</p>
        </div>
        <table style="width:100%;border-collapse:collapse;font-size:14px">
          <tr>
            <td style="padding:8px 0;color:#64748b">📤 Enviados</td>
            <td style="padding:8px 0;font-weight:700;color:#1e293b;text-align:right">{sent}</td>
          </tr>
          <tr>
            <td style="padding:8px 0;color:#64748b">✅ Entregados</td>
            <td style="padding:8px 0;font-weight:700;color:#16a34a;text-align:right">{delivered}</td>
          </tr>
          <tr>
            <td style="padding:8px 0;color:#64748b">💬 Respondidos</td>
            <td style="padding:8px 0;font-weight:700;color:#f59e0b;text-align:right">{replied}</td>
          </tr>
        </table>
      </div>
      <div style="background:#f8fafc;padding:16px 28px;border-top:1px solid #e2e8f0">
        <p style="margin:0;font-size:12px;color:#94a3b8;text-align:center">
          Revisa las métricas detalladas en tu panel de IaRadio.
        </p>
      </div>
    </div>
    """
    subject = f"✅ Campaña finalizada — {campaign_name}"
    return await send_email(to, subject, html)


async def send_trial_expiring_email(to: str, business_name: str, days_left: int) -> bool:
    """Notify the user that their trial is about to expire."""
    plan_url = f"{settings.FRONTEND_URL}/app/plans"
    html = f"""
    <div style="font-family:sans-serif;max-width:520px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;border:1px solid #e2e8f0">
      <div style="background:linear-gradient(135deg,#f59e0b,#d97706);padding:24px 28px">
        <h1 style="margin:0;color:#fff;font-size:22px;font-weight:800">
          ⏰ Tu prueba gratuita termina en {days_left} día{'s' if days_left != 1 else ''}
        </h1>
        <p style="margin:4px 0 0;color:rgba(255,255,255,0.85);font-size:14px">{business_name}</p>
      </div>
      <div style="padding:24px 28px">
        <p style="font-size:15px;color:#1e293b;line-height:1.5">
          Todo tu contenido, campañas y configuraciones se conservarán si eliges un plan.
        </p>
        <div style="background:#fffbeb;border-radius:8px;padding:16px;margin:16px 0;border:1px solid #fde68a">
          <p style="margin:0;font-size:13px;color:#92400e;line-height:1.5">
            <strong>⚠️ Si no eliges un plan, tu cuenta quedará suspendida.</strong><br />
            Tus campañas dejarán de enviarse y tu bot dejará de responder.
          </p>
        </div>
        <a href="{plan_url}"
           style="display:block;text-align:center;padding:14px 24px;background:#6366f1;
                  color:white;border-radius:10px;text-decoration:none;margin:20px 0;
                  font-size:16px;font-weight:700">
          Elegir mi plan →
        </a>
        <p style="font-size:13px;color:#64748b;text-align:center">
          Cancelas cuando quieras — sin penalizaciones.
        </p>
      </div>
      <div style="background:#f8fafc;padding:16px 28px;border-top:1px solid #e2e8f0">
        <p style="margin:0;font-size:12px;color:#94a3b8;text-align:center">
          ¿Preguntas? Responde a este correo o escríbenos a iaradio@iaradio.online
        </p>
      </div>
    </div>
    """
    subject = f"⏰ Tu prueba gratuita de IaRadio termina en {days_left} día{'s' if days_left != 1 else ''}"
    return await send_email(to, subject, html)


async def send_campaign_failed_email(
    to: str,
    business_name: str,
    campaign_name: str,
    error: str,
) -> bool:
    """Notify the advertiser that their campaign has failed."""
    html = f"""
    <div style="font-family:sans-serif;max-width:520px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;border:1px solid #e2e8f0">
      <div style="background:linear-gradient(135deg,#ef4444,#dc2626);padding:24px 28px">
        <h1 style="margin:0;color:#fff;font-size:22px;font-weight:800">
          ❌ Campaña fallida
        </h1>
        <p style="margin:4px 0 0;color:rgba(255,255,255,0.8);font-size:14px">{business_name}</p>
      </div>
      <div style="padding:24px 28px">
        <div style="background:#f8fafc;border-radius:8px;padding:16px;margin-bottom:16px">
          <p style="margin:0 0 4px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#94a3b8">Campaña</p>
          <p style="margin:0;font-size:18px;font-weight:700;color:#1e293b">{campaign_name}</p>
        </div>
        <div style="background:#fef2f2;border-radius:8px;padding:16px;border:1px solid #fecaca">
          <p style="margin:0 0 4px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#dc2626">Error</p>
          <p style="margin:0;font-size:14px;color:#991b1b">{error}</p>
        </div>
      </div>
      <div style="background:#f8fafc;padding:16px 28px;border-top:1px solid #e2e8f0">
        <p style="margin:0;font-size:12px;color:#94a3b8;text-align:center">
          Puedes intentarlo de nuevo desde tu panel de IaRadio.
        </p>
      </div>
    </div>
    """
    subject = f"❌ Campaña fallida — {campaign_name}"
    return await send_email(to, subject, html)

