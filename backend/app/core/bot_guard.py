"""Trampas para bots en formularios públicos.

Honeypot: los formularios llevan un campo "website" escondido (fuera de la
pantalla, sin tabulador, sin autocompletar). Una persona nunca lo ve; un bot
que llena todo lo que encuentra, sí lo llena. Si viene lleno se contesta como
si todo hubiera salido bien, pero no se hace nada (así el bot no aprende).
"""
import logging

from fastapi import Request

logger = logging.getLogger(__name__)

HONEYPOT_FIELD = "website"


def is_honeypot_hit(body: dict, request: Request | None = None, where: str = "") -> bool:
    if str(body.get(HONEYPOT_FIELD) or "").strip():
        ip = request.client.host if request and request.client else "?"
        logger.warning("[BOT] honeypot lleno en %s desde %s", where, ip)
        return True
    return False
