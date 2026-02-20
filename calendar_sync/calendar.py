"""Google Calendar API wrapper."""

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from googleapiclient.discovery import build

from .models import CalendarEvent, EventDetails

# Default calendar ID - can be overridden
DEFAULT_CALENDAR_ID = "5b0f9ebb2f4cca6705cf48ad4e4562964a7e3f90d6f2646e11c19788912c86ba@group.calendar.google.com"

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def get_credentials_path() -> Path:
    """Get the credentials file path from env var or default to cwd."""
    env_path = os.environ.get("CAL_CREDS_PATH")
    if env_path:
        return Path(env_path)
    return Path().cwd() / "cal-creds.json"


def get_calendar_service():
    """Build and return the Google Calendar service."""
    creds_path = get_credentials_path()
    if not creds_path.exists():
        raise FileNotFoundError(f"Credentials not found at {creds_path}")

    credentials = service_account.Credentials.from_service_account_file(
        str(creds_path), scopes=SCOPES
    )
    return build("calendar", "v3", credentials=credentials)


def search_events_by_date(
    start_date: str,
    end_date: str,
    calendar_id: str = DEFAULT_CALENDAR_ID,
) -> list[CalendarEvent]:
    """Search calendar for events in a date range.

    Args:
        start_date: ISO date string (e.g., "2026-01-31")
        end_date: ISO date string (e.g., "2026-02-07")
        calendar_id: Google Calendar ID

    Returns: List of events in the date range
    """
    service = get_calendar_service()

    # Convert dates to RFC3339 timestamps
    time_min = f"{start_date}T00:00:00Z"
    time_max = f"{end_date}T23:59:59Z"

    events_result = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    return [_parse_event(e) for e in events_result.get("items", [])]


def search_events_by_keyword(
    keywords: list[str],
    calendar_id: str = DEFAULT_CALENDAR_ID,
    days_ahead: int = 90,
) -> list[CalendarEvent]:
    """Search calendar for events matching any of the given keywords.

    Args:
        keywords: List of search terms (e.g., ["Unity Ride", "Unity"])
        calendar_id: Google Calendar ID
        days_ahead: How many days ahead to search

    Returns: Top 5 matching events sorted by start time (soonest first)
    """
    service = get_calendar_service()

    now = datetime.now(ZoneInfo("UTC"))
    time_min = now.isoformat()
    time_max = (now + timedelta(days=days_ahead)).isoformat()

    # Normalize keywords: strip whitespace, drop empties, deduplicate
    normalized = list(dict.fromkeys(k.strip() for k in keywords if k.strip()))

    seen_ids: set[str] = set()
    all_events: list[CalendarEvent] = []

    for keyword in normalized:
        events_result = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                q=keyword,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )

        for e in events_result.get("items", []):
            event_id = e.get("id")
            if not event_id:
                continue
            if event_id not in seen_ids:
                seen_ids.add(event_id)
                all_events.append(_parse_event(e))

    # Sort by start time; normalize naive datetimes (all-day events) to UTC
    def _sort_key(e: CalendarEvent) -> datetime:
        if e.start.tzinfo is None:
            return e.start.replace(tzinfo=ZoneInfo("UTC"))
        return e.start

    all_events.sort(key=_sort_key)
    return all_events[:5]


def create_event(
    event: EventDetails,
    calendar_id: str = DEFAULT_CALENDAR_ID,
) -> str:
    """Create a new calendar event.

    Returns: The created event's ID
    """
    service = get_calendar_service()

    # Build event body
    body = _build_event_body(event)

    result = service.events().insert(calendarId=calendar_id, body=body).execute()
    return result["id"]


def update_event(
    event_id: str,
    event: EventDetails,
    calendar_id: str = DEFAULT_CALENDAR_ID,
) -> str:
    """Update an existing calendar event.

    Returns: The updated event's ID
    """
    service = get_calendar_service()

    body = _build_event_body(event)

    result = (
        service.events()
        .update(calendarId=calendar_id, eventId=event_id, body=body)
        .execute()
    )
    return result["id"]


def delete_event(
    event_id: str,
    calendar_id: str = DEFAULT_CALENDAR_ID,
) -> None:
    """Delete a calendar event."""
    service = get_calendar_service()
    service.events().delete(calendarId=calendar_id, eventId=event_id).execute()


def _parse_event(event_data: dict) -> CalendarEvent:
    """Parse Google Calendar event data into CalendarEvent model."""
    start = event_data.get("start", {})
    end = event_data.get("end", {})

    # Handle all-day events vs timed events
    start_str = start.get("dateTime") or start.get("date")
    end_str = end.get("dateTime") or end.get("date")

    return CalendarEvent(
        id=event_data["id"],
        title=event_data.get("summary", ""),
        start=datetime.fromisoformat(start_str.replace("Z", "+00:00")),
        end=datetime.fromisoformat(end_str.replace("Z", "+00:00")) if end_str else None,
        location=event_data.get("location"),
        description=event_data.get("description"),
    )


def _build_event_body(event: EventDetails) -> dict:
    """Build Google Calendar event body from EventDetails."""
    tz = event.timezone

    # Parse date
    date = datetime.strptime(event.date, "%Y-%m-%d")

    if event.time:
        # Timed event
        hour, minute = map(int, event.time.split(":"))
        start_dt = date.replace(hour=hour, minute=minute, tzinfo=ZoneInfo(tz))

        if event.end_time:
            end_hour, end_minute = map(int, event.end_time.split(":"))
            end_dt = date.replace(hour=end_hour, minute=end_minute, tzinfo=ZoneInfo(tz))
        else:
            # Default to 2 hours later
            end_dt = start_dt + timedelta(hours=2)

        start = {"dateTime": start_dt.isoformat(), "timeZone": tz}
        end = {"dateTime": end_dt.isoformat(), "timeZone": tz}
    else:
        # All-day event
        start = {"date": event.date}
        end = {"date": event.date}

    body = {
        "summary": event.title,
        "start": start,
        "end": end,
    }

    if event.location:
        body["location"] = event.location
    if event.description:
        body["description"] = event.description

    return body
