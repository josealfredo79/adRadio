"""
Google Calendar service — OAuth2 flow + event CRUD.

Flujo:
  1. Usuario presiona "Conectar Google Calendar" → redirect a Google OAuth
  2. Google regresa con code → intercambiamos por refresh_token
  3. Se guarda refresh_token en user.google_refresh_token
  4. Al crear/actualizar/cancelar cita → sync con Google Calendar
"""
import logging
from datetime import datetime, timedelta

from app.config import settings

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


def _get_flow(redirect_uri: str):
    """Create Google OAuth2 flow for Calendar access."""
    from google_auth_oauthlib.flow import Flow  # type: ignore

    client_config = {
        "web": {
            "client_id": settings.GOOGLE_CALENDAR_CLIENT_ID,
            "client_secret": settings.GOOGLE_CALENDAR_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }
    flow = Flow.from_client_config(client_config, scopes=SCOPES)
    flow.redirect_uri = redirect_uri
    return flow


def get_auth_url(redirect_uri: str, state: str) -> str:
    """Generate the Google OAuth consent URL."""
    flow = _get_flow(redirect_uri)
    url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=state,
        include_granted_scopes="true",
    )
    return url


def exchange_code(code: str, redirect_uri: str) -> str:
    """Exchange authorization code for refresh_token."""
    flow = _get_flow(redirect_uri)
    flow.fetch_token(code=code)
    credentials = flow.credentials
    if not credentials.refresh_token:
        raise ValueError("No refresh token received — user may need to re-authorize")
    return credentials.refresh_token


def _get_calendar_service(refresh_token: str):
    """Build an authorized Google Calendar API client."""
    from google.auth.transport.requests import Request  # type: ignore
    from google.oauth2.credentials import Credentials  # type: ignore
    from googleapiclient.discovery import build  # type: ignore

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=settings.GOOGLE_CALENDAR_CLIENT_ID,
        client_secret=settings.GOOGLE_CALENDAR_CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
    )
    creds.refresh(Request())

    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def create_event(
    refresh_token: str,
    summary: str,
    description: str,
    start_dt: datetime,
    duration_min: int = 30,
    customer_phone: str | None = None,
) -> str:
    """Create a Google Calendar event. Returns the event ID."""
    try:
        service = _get_calendar_service(refresh_token)
        end_dt = start_dt + timedelta(minutes=duration_min)

        event_body = {
            "summary": summary,
            "description": description,
            "start": {"dateTime": start_dt.isoformat(), "timeZone": "America/Mexico_City"},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": "America/Mexico_City"},
            "reminders": {"useDefault": False, "overrides": [
                {"method": "popup", "minutes": 60},
                {"method": "popup", "minutes": 1440},
            ]},
        }

        event = service.events().insert(calendarId="primary", body=event_body).execute()
        logger.info("[GCAL] Event created: %s", event.get("id"))
        return event["id"]
    except Exception as e:
        logger.error("[GCAL] Error creating event: %s", e)
        raise


def update_event(
    refresh_token: str,
    event_id: str,
    summary: str | None = None,
    start_dt: datetime | None = None,
    duration_min: int | None = None,
) -> None:
    """Update an existing Google Calendar event."""
    try:
        service = _get_calendar_service(refresh_token)
        event = service.events().get(calendarId="primary", eventId=event_id).execute()

        if summary:
            event["summary"] = summary
        if start_dt:
            event["start"] = {"dateTime": start_dt.isoformat(), "timeZone": "America/Mexico_City"}
            end_dt = start_dt + timedelta(minutes=duration_min or 30)
            event["end"] = {"dateTime": end_dt.isoformat(), "timeZone": "America/Mexico_City"}

        service.events().update(calendarId="primary", eventId=event_id, body=event).execute()
        logger.info("[GCAL] Event updated: %s", event_id)
    except Exception as e:
        logger.error("[GCAL] Error updating event: %s", e)


def delete_event(refresh_token: str, event_id: str) -> None:
    """Delete a Google Calendar event."""
    try:
        service = _get_calendar_service(refresh_token)
        service.events().delete(calendarId="primary", eventId=event_id).execute()
        logger.info("[GCAL] Event deleted: %s", event_id)
    except Exception as e:
        logger.error("[GCAL] Error deleting event: %s", e)
