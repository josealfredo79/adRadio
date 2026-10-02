"""Para escribir URLs de conexión en los logs sin su contraseña."""
import re

_CREDENTIALS = re.compile(r"(?P<scheme>[a-z][a-z0-9+.-]*://)(?P<user>[^:/@]*):[^/]*@", re.IGNORECASE)


def redact_url(url: str | None) -> str:
    """redis://default:secreto@host:6379 → redis://default:***@host:6379"""
    return _CREDENTIALS.sub(r"\g<scheme>\g<user>:***@", url or "")
