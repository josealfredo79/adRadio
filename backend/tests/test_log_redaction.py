"""Secrets in Graph API query strings must never reach the logs."""
import logging

import httpx

from app.core.log_redaction import redact_http_client_logs


def test_httpx_request_log_drops_the_query_string(caplog):
    redact_http_client_logs()
    url = httpx.URL("https://graph.facebook.com/v21.0/oauth/access_token?client_id=1&client_secret=SHHH&code=abc")
    with caplog.at_level(logging.INFO, logger="httpx"):
        logging.getLogger("httpx").info('HTTP Request: %s %s "%s %d %s"', "GET", url, "HTTP/1.1", 200, "OK")
    text = caplog.text
    assert "SHHH" not in text and "code=abc" not in text
    assert 'HTTP Request: GET https://graph.facebook.com/v21.0/oauth/access_token "HTTP/1.1 200 OK"' in text
