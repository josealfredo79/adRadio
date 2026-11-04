"""httpx logs every request URL at INFO, query string included. Graph API calls
carry secrets there (oauth/access_token?client_secret=…, debug_token?input_token=…,
access_token=…), so they ended up in Railway's logs. Keep the line (revisar-prod
reads method, host, path and status) but drop the query string."""
import logging


class _DropQueryString(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple) and len(record.args) >= 2:
            args = list(record.args)
            args[1] = str(args[1]).split("?", 1)[0]
            record.args = tuple(args)
        return True


def redact_http_client_logs() -> None:
    logger = logging.getLogger("httpx")
    if not any(isinstance(f, _DropQueryString) for f in logger.filters):
        logger.addFilter(_DropQueryString())
