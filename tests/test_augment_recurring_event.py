"""Tests for fetch_events recurring-event grouping logic."""

import os

import pytest

os.environ.setdefault("CALENDAR_ID", "test-calendar-id")

from calendar_sync.fetch_events import (  # noqa: E402
    _base_event_id,
    _group_recurring_events,
    _transform_description,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _instance(
    series_id: str,
    occurrence_date: str,
    *,
    summary: str = "Test Ride",
    status: str = "confirmed",
) -> dict:
    """Build a minimal singleEvents=True instance dict."""
    return {
        "id": f"{series_id}_{occurrence_date}",
        "summary": summary,
        "status": status,
        "recurringEventId": series_id,
        "start": {
            "dateTime": f"{occurrence_date}T10:00:00-06:00",
            "timeZone": "America/Chicago",
        },
        "end": {
            "dateTime": f"{occurrence_date}T12:00:00-06:00",
            "timeZone": "America/Chicago",
        },
    }


def _one_off(event_id: str, date: str, *, summary: str = "One-off Event") -> dict:
    """Build a minimal one-off (non-recurring) event dict."""
    return {
        "id": event_id,
        "summary": summary,
        "status": "confirmed",
        "start": {"dateTime": f"{date}T10:00:00-06:00", "timeZone": "America/Chicago"},
        "end": {"dateTime": f"{date}T12:00:00-06:00", "timeZone": "America/Chicago"},
    }


# ---------------------------------------------------------------------------
# _group_recurring_events
# ---------------------------------------------------------------------------


def test_single_series_reduced_to_one_event() -> None:
    instances = [
        _instance("series-a", "2026-03-01"),
        _instance("series-a", "2026-04-05"),
        _instance("series-a", "2026-05-03"),
    ]
    result = _group_recurring_events(instances)
    series_events = [e for e in result if e.get("recurringEventId") == "series-a"]
    assert len(series_events) == 1


def test_representative_is_first_instance() -> None:
    """The earliest (first in startTime order) instance should be the representative."""
    instances = [
        _instance("series-a", "2026-03-01"),
        _instance("series-a", "2026-04-05"),
        _instance("series-a", "2026-05-03"),
    ]
    result = _group_recurring_events(instances)
    rep = next(e for e in result if e.get("recurringEventId") == "series-a")
    assert rep["start"]["dateTime"].startswith("2026-03-01")


def test_recurrence_future_count_equals_group_size() -> None:
    instances = [
        _instance("series-a", "2026-03-01"),
        _instance("series-a", "2026-04-05"),
        _instance("series-a", "2026-05-03"),
    ]
    result = _group_recurring_events(instances)
    rep = next(e for e in result if e.get("recurringEventId") == "series-a")
    assert rep["recurrence_future_count"] == 3


def test_recurrence_label_and_n_more() -> None:
    instances = [
        _instance("series-a", "2026-03-01"),
        _instance("series-a", "2026-04-05"),
        _instance("series-a", "2026-05-03"),
    ]
    result = _group_recurring_events(instances)
    rep = next(e for e in result if e.get("recurringEventId") == "series-a")
    assert rep["recurrence_label"] == "And 2 more"


def test_recurrence_label_single_instance() -> None:
    """A series with only one occurrence in the window gets 'No more after this'."""
    instances = [_instance("series-a", "2026-03-01")]
    result = _group_recurring_events(instances)
    rep = next(e for e in result if e.get("recurringEventId") == "series-a")
    assert rep["recurrence_future_count"] == 1
    assert rep["recurrence_label"] == "No more after this"


def test_one_off_events_pass_through_unchanged() -> None:
    events = [_one_off("evt-1", "2026-03-15"), _one_off("evt-2", "2026-04-20")]
    result = _group_recurring_events(events)
    assert len(result) == 2
    ids = {e["id"] for e in result}
    assert ids == {"evt-1", "evt-2"}


def test_one_off_events_have_no_recurrence_fields() -> None:
    events = [_one_off("evt-1", "2026-03-15")]
    result = _group_recurring_events(events)
    assert "recurrence_future_count" not in result[0]
    assert "recurrence_label" not in result[0]


def test_multiple_series_grouped_independently() -> None:
    instances = [
        _instance("series-a", "2026-03-01"),
        _instance("series-b", "2026-03-07"),
        _instance("series-a", "2026-04-05"),
        _instance("series-b", "2026-04-11"),
        _instance("series-b", "2026-05-09"),
    ]
    result = _group_recurring_events(instances)

    a_events = [e for e in result if e.get("recurringEventId") == "series-a"]
    b_events = [e for e in result if e.get("recurringEventId") == "series-b"]

    assert len(a_events) == 1
    assert a_events[0]["recurrence_future_count"] == 2

    assert len(b_events) == 1
    assert b_events[0]["recurrence_future_count"] == 3


def test_mixed_one_offs_and_recurring() -> None:
    events = [
        _one_off("evt-1", "2026-03-10"),
        _instance("series-a", "2026-03-01"),
        _instance("series-a", "2026-04-05"),
        _one_off("evt-2", "2026-05-01"),
    ]
    result = _group_recurring_events(events)
    # 2 one-offs + 1 representative for series-a
    assert len(result) == 3


def test_empty_input() -> None:
    assert _group_recurring_events([]) == []


# ---------------------------------------------------------------------------
# _base_event_id
# ---------------------------------------------------------------------------


def test_base_event_id_strips_r_suffix() -> None:
    assert _base_event_id("abc123_R20250612T230000") == "abc123"


def test_base_event_id_no_suffix_returns_none() -> None:
    assert _base_event_id("abc123") is None


def test_base_event_id_invalid_suffix_returns_none() -> None:
    # Has _R but not in the expected timestamp format
    assert _base_event_id("abc123_Rfoobar") is None


def test_base_event_id_preserves_complex_base() -> None:
    assert (
        _base_event_id("2gllle8uet9h6uckcgmvb4iics_R20250612T230000")
        == "2gllle8uet9h6uckcgmvb4iics"
    )


# ---------------------------------------------------------------------------
# _transform_description
# ---------------------------------------------------------------------------


def test_plain_text_newlines_become_br() -> None:
    assert _transform_description("line one\nline two") == "line one<br>line two"


def test_plain_text_multiple_newlines() -> None:
    result = _transform_description("a\n\nb")
    assert result == "a<br><br>b"


def test_plain_text_url_linkified() -> None:
    result = _transform_description("Visit https://example.com for info")
    assert '<a href="https://example.com">https://example.com</a>' in result


def test_plain_text_url_and_newline_together() -> None:
    result = _transform_description("Info:\nhttps://example.com\nSee you there")
    assert '<a href="https://example.com">https://example.com</a>' in result
    assert "<br>" in result


def test_html_description_returned_unchanged() -> None:
    html = '<p>Group ride. <a href="https://example.com">Details</a></p>'
    assert _transform_description(html) == html


def test_html_with_br_returned_unchanged() -> None:
    html = "Line one<br>Line two"
    assert _transform_description(html) == html


def test_html_with_bold_returned_unchanged() -> None:
    html = "Meet at <b>6pm</b> sharp."
    assert _transform_description(html) == html


def test_empty_string_returned_unchanged() -> None:
    assert _transform_description("") == ""


def test_plain_text_no_url_no_newline_unchanged() -> None:
    text = "Just a plain sentence with no special content."
    assert _transform_description(text) == text


def test_url_not_double_linked_when_already_in_href() -> None:
    """URLs that are already inside an href attribute must not be wrapped again."""
    html = '<a href="https://example.com">https://example.com</a>'
    assert _transform_description(html) == html
