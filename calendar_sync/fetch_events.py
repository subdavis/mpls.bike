"""Fetch and augment calendar events for static site export."""

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import json

from . import calendar, claude, db, rss


# Matches any tag-like substring — used for HTML detection only
_HTML_TAG_RE = re.compile(r"<[a-zA-Z/][^>]*>")

# Matches bare URLs not already inside an href="…" attribute
_URL_RE = re.compile(
    r'(?<!href=["\'])(?<!href=)(https?://[^\s<>"\']+)',
    re.IGNORECASE,
)

# How far ahead to expand recurring events via singleEvents=True
RECURRING_WINDOW_MONTHS = 4


def _today_midnight_local() -> datetime:
    """Return midnight of today in the local timezone, as a UTC-aware datetime.

    Uses TIME_ZONE from claude.py so the day boundary matches the user's locale
    rather than UTC.
    """
    tz = ZoneInfo(claude.TIME_ZONE)
    now_local = datetime.now(tz)
    midnight_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight_local.astimezone(timezone.utc)


def _fetch_single_events(time_min: str, time_max: str) -> list[dict]:
    """Fetch expanded (singleEvents=True) events between two RFC3339 timestamps.

    Recurring events are returned as individual instances, ordered by start time.
    Cancelled instances are excluded by the API when using singleEvents=True.
    """
    service = calendar.get_calendar_service()
    all_items: list[dict] = []
    page_token: str | None = None

    while True:
        kwargs: dict = {
            "calendarId": calendar.CALENDAR_ID,
            "timeMin": time_min,
            "timeMax": time_max,
            "singleEvents": True,
            "orderBy": "startTime",
        }
        if page_token:
            kwargs["pageToken"] = page_token

        result = service.events().list(**kwargs).execute()
        all_items.extend(result.get("items", []))

        page_token = result.get("nextPageToken")
        if not page_token:
            break

    return all_items


def _fetch_non_recurring_events(time_min: str) -> list[dict]:
    """Fetch non-recurring one-off events from time_min to infinity.

    Uses singleEvents=False so the API returns series master records, then
    filters to only events that have no recurrence rule (i.e. true one-offs).
    Cancelled records are also dropped.
    """
    service = calendar.get_calendar_service()
    all_items: list[dict] = []
    page_token: str | None = None

    while True:
        kwargs: dict = {
            "calendarId": calendar.CALENDAR_ID,
            "timeMin": time_min,
            "singleEvents": False,
            "orderBy": "updated",
        }
        if page_token:
            kwargs["pageToken"] = page_token

        result = service.events().list(**kwargs).execute()
        all_items.extend(result.get("items", []))

        page_token = result.get("nextPageToken")
        if not page_token:
            break

    return [
        e
        for e in all_items
        if not e.get("recurrence") and e.get("status") != "cancelled"
    ]


def _group_recurring_events(single_events: list[dict]) -> list[dict]:
    """Reduce expanded recurring instances to one representative per series.

    Groups instances by their recurringEventId. For each group, the
    immediately upcoming instance (the first in startTime order, since the
    API returns them ordered) is kept as the representative event, and
    recurrence_future_count is set to the total number of instances in the
    group (including the representative itself).

    One-off events (no recurringEventId) pass through unchanged with
    recurrence_future_count left unset.
    """
    # Separate recurring instances from one-offs
    groups: dict[str, list[dict]] = {}
    one_offs: list[dict] = []

    for event in single_events:
        series_id = event.get("recurringEventId")
        if series_id:
            groups.setdefault(series_id, []).append(event)
        else:
            one_offs.append(event)

    result: list[dict] = list(one_offs)

    for series_id, instances in groups.items():
        # instances are already in startTime order from the API
        representative = instances[0]
        count = len(instances)
        representative["recurrence_future_count"] = count
        representative["recurrence_label"] = (
            f"And {count - 1} more" if count > 1 else "No more after this"
        )
        result.append(representative)

    return result


def _base_event_id(event_id: str) -> str | None:
    """Return the base series ID for a split-series continuation event, or None.

    When an organiser edits a recurring event from a given occurrence onward
    ("this and following"), Google creates a new series whose ID is:
        <original_id>_R<RFC-timestamp>   e.g. abc123_R20250612T230000

    This function strips the _R… suffix so we can fall back to the original
    series' DB row when the continuation has no row of its own.
    """
    idx = event_id.find("_R")
    if idx == -1:
        return None
    # Sanity-check: the suffix should look like _R<digits>T<digits>
    suffix = event_id[idx + 2 :]  # everything after "_R"
    if "T" in suffix and suffix.replace("T", "").isdigit():
        return event_id[:idx]
    return None


def _transform_description(description: str) -> str:
    """Normalise a plain-text calendar description to simple HTML.

    If the description already contains HTML tags it is returned as-is.
    Otherwise:
    - Newlines are converted to <br> tags.
    - Bare URLs are wrapped in <a href="…"> tags.
    """
    if not description:
        return description
    if _HTML_TAG_RE.search(description):
        return description.replace("\n", "<br>")
    # Linkify first so newline conversion doesn't split URLs
    linked = _URL_RE.sub(
        lambda m: f'<a href="{m.group(1)}">{m.group(1)}</a>', description
    )
    return linked.replace("\n", "<br>")


def _attach_metadata(events: list[dict]) -> None:
    """Join each event with its DB row in-place, attaching extra_metadata and image_urls."""
    event_ids = [e["id"] for e in events if "id" in e]
    base_ids = [bid for eid in event_ids if (bid := _base_event_id(eid)) is not None]
    db_rows = db.get_rows_by_calendar_event_ids(event_ids + base_ids)

    for event in events:
        event_id: str | None = event.get("id")
        row = None
        if event_id is not None:
            row = db_rows.get(event_id)
            if row is None:
                base_id = _base_event_id(event_id)
                if base_id is not None:
                    row = db_rows.get(base_id)
        if row and row.get("post_extra"):
            try:
                row["post_extra"] = json.loads(row["post_extra"])
                event["source_id"] = row["post_extra"].get("rssglue_source_feed_id")
            except (json.JSONDecodeError, TypeError):
                pass
        event["extra_metadata"] = row
        event["image_urls"] = (
            rss.extract_image_urls(row["post_content"] or "")
            if row and row.get("post_content")
            else []
        )
        if description := event.get("description"):
            event["description"] = _transform_description(description)


def build_events_json() -> list[dict]:
    """Fetch, merge, and enrich calendar events for static site export.

    Strategy:
    - singleEvents=True for the next 4 months: captures all recurring
      instances; grouped by series so only the next occurrence is kept,
      with recurrence_future_count reflecting how many fall in the window.
    - singleEvents=False from today onward: one-off events beyond the 4-month
      window are captured here; recurring series masters are discarded.

    The two datasets are merged (deduped by event id), then enriched with
    DB metadata.
    """
    today_midnight = _today_midnight_local()
    time_min = today_midnight.strftime("%Y-%m-%dT%H:%M:%SZ")
    # Approximate 4 months as 4 * 31 days
    window_end = today_midnight + timedelta(days=4 * 31)
    time_max = window_end.strftime("%Y-%m-%dT%H:%M:%SZ")

    # --- Dataset 1: expanded recurring events for the next 4 months ---
    single_events = _fetch_single_events(time_min=time_min, time_max=time_max)
    grouped = _group_recurring_events(single_events)

    # Track which event IDs are already represented so we don't duplicate
    seen_ids: set[str] = set()
    # For recurring instances, key by recurringEventId to avoid adding the
    # same series twice if it also appears in the non-recurring fetch
    seen_series_ids: set[str] = set()
    for event in grouped:
        seen_ids.add(event["id"])
        series_id = event.get("recurringEventId")
        if series_id:
            seen_series_ids.add(series_id)

    # --- Dataset 2: one-off events beyond the 4-month window ---
    non_recurring = _fetch_non_recurring_events(time_min=time_min)
    beyond = [e for e in non_recurring if e.get("id") not in seen_ids]

    # --- Merge ---
    merged = grouped + beyond

    # --- Attach DB metadata ---
    _attach_metadata(merged)

    return merged
