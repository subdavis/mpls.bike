"""HTML report generation for calendar-sync."""

import base64
import html as html_lib
from collections import defaultdict
from datetime import datetime, timezone

from . import claude
from .calendar import CALENDAR_ID
from .rss import extract_image_urls


def _gcal_url(event_id: str) -> str:
    """Build a Google Calendar web URL for an event."""
    eid = base64.b64encode(f"{event_id} {CALENDAR_ID}".encode()).decode()
    return f"https://www.google.com/calendar/event?eid={eid}"


DECISION_COLORS = {
    "create": "#22c55e",
    "update": "#3b82f6",
    "cancel": "#ef4444",
    "ignore": "#9ca3af",
    "flag_for_review": "#eab308",
}


def _day_label(post_time: str | None) -> str:
    """Return a day header like 'Tuesday Feb 4' from an ISO timestamp in local time."""
    if not post_time or post_time == "-":
        return "Unknown Date"
    try:
        # Parse and convert to local time
        dt = datetime.fromisoformat(post_time)
        from zoneinfo import ZoneInfo

        local_dt = dt.astimezone(ZoneInfo(claude.TIME_ZONE))
        return local_dt.strftime("%A %b ") + str(local_dt.day)
    except (ValueError, TypeError):
        return "Unknown Date"


def _thumb_html(post_content: str) -> str:
    """Return an <img> thumbnail or a gray placeholder div."""
    image_urls = extract_image_urls(post_content)
    if image_urls:
        return f'<img class="thumb" src="{html_lib.escape(image_urls[0], quote=True)}" alt="">'
    return '<div class="thumb thumb-placeholder"></div>'


def _event_detail_html(e: dict) -> str:
    """Return an event-details <p> if the entry has event info, else empty string."""
    if not e.get("event_title"):
        return ""
    ev_title = html_lib.escape(e["event_title"])
    ev_date = html_lib.escape(e.get("event_date") or "")
    ev_time = html_lib.escape(e.get("event_time") or "")
    ev_loc = html_lib.escape(e.get("event_location") or "")
    when = f"{ev_date} at {ev_time}" if ev_time else ev_date
    event_id = e.get("calendar_event_id")
    if event_id:
        title_html = f'<a href="{_gcal_url(event_id)}" target="_blank"><strong>{ev_title}</strong></a>'
    else:
        title_html = f"<strong>{ev_title}</strong>"
    parts = [title_html]
    if when:
        parts.append(when)
    if ev_loc:
        parts.append(ev_loc)
    return f'<p class="event-details">📅 {" &middot; ".join(parts)}</p>'


def _render_card(e: dict) -> str:
    """Render a single entry as an HTML card."""
    color = DECISION_COLORS.get(e["decision"], "#9ca3af")
    title = html_lib.escape(e.get("post_title") or "-")
    link = e.get("post_link") or ""
    author = html_lib.escape(e.get("post_author") or "-")
    guid = html_lib.escape(e["post_guid"])
    reasoning = html_lib.escape(e.get("reasoning") or "-")
    raw_event_id = e.get("calendar_event_id") or ""
    event_id = html_lib.escape(raw_event_id or "-")
    cost = f"${e['cost_usd']:.4f}" if e.get("cost_usd") else "-"
    tokens_in = f"{e.get('input_tokens') or 0:,}"
    tokens_out = f"{e.get('output_tokens') or 0:,}"
    processed = claude.local_time_str(e["processed_at"])
    post_time = claude.local_time_str(e.get("post_time"))

    title_html = (
        f'<a href="{html_lib.escape(link, quote=True)}">{title}</a>' if link else title
    )

    return f"""
    <div class="card">
      {_thumb_html(e.get("post_content") or "")}
      <div class="card-content">
        <div class="card-header">
          <h2>{title_html}</h2>
          <span class="badge" style="background:{color}">{html_lib.escape(e["decision"])}</span>
        </div>
        <div class="card-body">
          {_event_detail_html(e)}
          <p class="reasoning">{reasoning}</p>
        </div>
        <div class="card-footer">
          <span><strong>Author:</strong> {author}</span>
          <span><strong>GUID:</strong> <code>{guid}</code></span>
          <span><strong>Event:</strong> {f'<a href="{_gcal_url(raw_event_id)}" target="_blank"><code>{event_id}</code></a>' if raw_event_id else f"<code>{event_id}</code>"}</span>
          <span><strong>Post time:</strong> {html_lib.escape(post_time)}</span>
          <span><strong>Processed:</strong> {html_lib.escape(processed)}</span>
          <span><strong>Tokens:</strong> {tokens_in} in / {tokens_out} out</span>
          <span><strong>Cost:</strong> {cost}</span>
        </div>
      </div>
    </div>"""


def generate_report(entries: list[dict], total_cost: float) -> str:
    """Generate a static HTML report from processing history entries."""
    # Group entries by day
    grouped: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        label = _day_label(e.get("post_time"))
        grouped[label].append(e)

    cards = ""
    for day_label, day_entries in grouped.items():
        cards += f'\n    <h2 class="day-header">{html_lib.escape(day_label)}</h2>'
        for e in day_entries:
            cards += _render_card(e)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Calendar Sync Report</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f8fafc; color: #1e293b; padding: 2rem; max-width: 860px; margin: 0 auto; }}
  h1 {{ font-size: 1.5rem; margin-bottom: .25rem; }}
  .subtitle {{ color: #64748b; margin-bottom: 1.5rem; font-size: .9rem; }}
  .card {{ background: white; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,.1); margin-bottom: .75rem; overflow: hidden; display: flex; }}
  .thumb {{ width: 180px; flex-shrink: 0; object-fit: contain; }}
  .thumb-placeholder {{ background: #e2e8f0; }}
  .card-content {{ flex: 1; min-width: 0; }}
  .card-header {{ padding: .75rem 1rem .5rem; display: flex; justify-content: space-between; align-items: start; gap: .5rem; }}
  .card-header h2 {{ font-size: .95rem; font-weight: 600; }}
  .card-header h2 a {{ color: #1e293b; text-decoration: none; }}
  .card-header h2 a:hover {{ text-decoration: underline; }}
  .badge {{ display: inline-block; color: white; font-size: .7rem; font-weight: 600; padding: 2px 8px; border-radius: 4px; white-space: nowrap; flex-shrink: 0; }}
  .card-body {{ padding: 0 1rem .5rem; }}
  .event-details {{ font-size: .8rem; color: #475569; margin-bottom: .35rem; }}
  .event-details a {{ color: #2563eb; text-decoration: none; }}
  .event-details a:hover {{ text-decoration: underline; }}
  .reasoning {{ font-size: .85rem; color: #334155; white-space: pre-wrap; }}
  .card-footer {{ padding: .5rem 1rem; background: #f8fafc; font-size: .75rem; color: #64748b; display: flex; flex-wrap: wrap; gap: .25rem 1.25rem; border-top: 1px solid #e2e8f0; }}
  .card-footer code {{ background: #e2e8f0; padding: 1px 4px; border-radius: 3px; font-size: .7rem; }}
  .day-header {{ font-size: 1.1rem; font-weight: 600; margin: 1.5rem 0 .5rem; }}
  .day-header:first-child {{ margin-top: 0; }}
  .summary {{ margin-top: 1rem; font-size: .85rem; color: #64748b; }}
</style>
</head>
<body>
  <h1>Calendar Sync Report</h1>
  <p class="subtitle">Last {len(entries)} processed posts &middot; Total cost: ${total_cost:.4f}</p>
  {cards}
  <p class="summary">Generated {claude.local_time_str(datetime.now(timezone.utc))}</p>
</body>
</html>"""
