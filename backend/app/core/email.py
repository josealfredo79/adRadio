import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import settings


async def send_email(to: str, subject: str, html_body: str) -> bool:
    """Send email via SMTP. Returns True on success."""
    if not settings.SMTP_HOST:
        # Dev mode: log to console
        print(f"[EMAIL] To: {to} | Subject: {subject}\n{html_body}")
        return True

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
        print(f"[EMAIL ERROR] {e}")
        return False


async def send_verification_email(to: str, code: str) -> bool:
    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:0 auto">
      <h2 style="color:#6366f1">AdRadio — Verifica tu email</h2>
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
    return await send_email(to, "Verifica tu cuenta de AdRadio", html)


async def send_password_reset_email(to: str, token: str) -> bool:
    reset_url = f"https://app.adradio.app/reset-password?token={token}"
    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:0 auto">
      <h2 style="color:#6366f1">AdRadio — Recuperar contraseña</h2>
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
    return await send_email(to, "Recupera tu contraseña de AdRadio", html)
