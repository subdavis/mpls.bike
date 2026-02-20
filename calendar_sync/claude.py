"""Claude SDK integration for analyzing posts and making calendar decisions."""

import base64
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from anthropic import Anthropic
from pydantic import ValidationError

from . import calendar, db
from .models import Action, ClaudeDecision, EventDetails, RssPost

# Pricing per million tokens (Claude 3.5 Sonnet)
INPUT_COST_PER_M = 3.00
OUTPUT_COST_PER_M = 15.00
TIME_ZONE = "America/Chicago"


def local_time_str(dt: datetime | str | None) -> str:
    """Convert UTC datetime or ISO string to local timezone string for logging.

    Args:
        dt: A datetime object, ISO format string, or None

    Returns:
        Formatted local time string, or "-" if dt is None
    """
    if dt is None:
        return "-"

    # Parse string to datetime if needed
    if isinstance(dt, str):
        try:
            dt_parsed: datetime = datetime.fromisoformat(dt)
        except (ValueError, TypeError):
            return str(dt)  # Return original string if parsing fails
        dt = dt_parsed

    # Convert to local timezone
    tz = ZoneInfo(TIME_ZONE)
    local_dt = dt.astimezone(tz)
    return local_dt.strftime("%Y-%m-%d %H:%M:%S %Z")


def get_logs_dir() -> Path:
    """Get the logs directory path."""
    return Path(__file__).parent.parent / "logs"


class SessionLogger:
    """Logs a Claude session to a file for debugging."""

    def __init__(self, post_guid: str):
        logs_dir = get_logs_dir()
        logs_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        # Use first 8 chars of guid for filename
        short_guid = post_guid[:8] if len(post_guid) >= 8 else post_guid
        self.log_path = logs_dir / f"{timestamp}-{short_guid}.log"
        self.turn = 0

        # Start the log
        with open(self.log_path, "w") as f:
            f.write(f"Session started: {datetime.now(timezone.utc).isoformat()}\n")
            f.write(f"Post GUID: {post_guid}\n")
            f.write("=" * 60 + "\n\n")

    def log_user_message(self, content: list[dict]) -> None:
        """Log the initial user message."""
        with open(self.log_path, "a") as f:
            f.write("=== USER MESSAGE ===\n")
            for block in content:
                if block.get("type") == "text":
                    f.write(block["text"] + "\n")
                elif block.get("type") == "image":
                    f.write(f"[IMAGE: {block['source']['media_type']}]\n")
            f.write("\n")

    def log_turn(self, response, tool_results: list[dict] | None = None) -> None:
        """Log a conversation turn."""
        self.turn += 1
        with open(self.log_path, "a") as f:
            f.write(f"=== TURN {self.turn} ===\n")
            f.write(f"Stop reason: {response.stop_reason}\n")
            f.write(
                f"Tokens: {response.usage.input_tokens} in / {response.usage.output_tokens} out\n\n"
            )

            # Log assistant response
            f.write("--- Assistant ---\n")
            for block in response.content:
                if hasattr(block, "text"):
                    f.write(block.text + "\n")
                elif block.type == "tool_use":
                    f.write(f"[TOOL CALL: {block.name}]\n")
                    f.write(json.dumps(block.input, indent=2) + "\n")
            f.write("\n")

            # Log tool results if any
            if tool_results:
                f.write("--- Tool Results ---\n")
                for result in tool_results:
                    f.write(f"[{result['tool_use_id']}]\n")
                    content = result["content"]
                    if isinstance(content, list):
                        # Content blocks (e.g. from get_images)
                        for block in content:
                            if block.get("type") == "image":
                                f.write(f"[IMAGE: {block['source']['media_type']}]\n")
                            elif block.get("type") == "text":
                                f.write(block["text"] + "\n")
                    else:
                        # Try to pretty-print JSON content
                        try:
                            parsed = json.loads(content)
                            f.write(json.dumps(parsed, indent=2) + "\n")
                        except (json.JSONDecodeError, TypeError):
                            f.write(content + "\n")
                f.write("\n")

    def log_final(self, ctx: "AnalysisContext") -> None:
        """Log final summary."""
        with open(self.log_path, "a") as f:
            f.write("=" * 60 + "\n")
            f.write("=== SESSION COMPLETE ===\n")
            f.write(f"Total tokens: {ctx.input_tokens} in / {ctx.output_tokens} out\n")
            f.write(f"Cost: ${ctx.cost_usd:.4f}\n")
            f.write(f"Decisions: {len(ctx.decisions)}\n")
            for i, (decision, cal_id) in enumerate(
                zip(ctx.decisions, ctx.calendar_event_ids)
            ):
                if len(ctx.decisions) > 1:
                    f.write(f"\n--- Decision {i + 1} ---\n")
                f.write(f"Decision: {decision.action.value}\n")
                f.write(f"Reasoning: {decision.reasoning}\n")
                if decision.event:
                    f.write(f"Event: {decision.event.title} on {decision.event.date}\n")
                if cal_id:
                    f.write(f"Calendar event ID: {cal_id}\n")

    def log_error(self, error: str) -> None:
        """Log an error."""
        with open(self.log_path, "a") as f:
            f.write(f"\n!!! ERROR !!!\n{error}\n")


SYSTEM_PROMPT = f"""You are analyzing RSS posts to determine if they announce events that should be added to a calendar.

These posts come from Instagram accounts of cycling groups and community organizations. They may contain:
- Event announcements with dates, times, and locations
- Updates to previously announced events (time changes, location changes)
- Cancellation notices
- General posts that are NOT events (quotes, reflections, photos)

IMPORTANT: Event information may be embedded in images (event posters/flyers). You will NOT receive images upfront. You must request them with the get_images tool.

You have access to these tools:
1. get_images - Fetch the post's images (call this if the post could plausibly be an event)
2. search_events_by_date - Check if events exist on specific dates
3. search_events_by_keyword - Search for events by name/keyword. Provide an array of keywords; events matching ANY keyword are returned (top 5 by upcoming date)
4. submit_decision - Submit your final decision (REQUIRED)

Workflow:
1. Analyze the post text to determine if it could plausibly be an event
2. If it's clearly NOT an event (quotes, reflections, general photos with no event info), submit_decision with action "ignore" immediately
3. If it COULD be an event, call get_images to check for event posters/flyers with dates, times, and locations
4. If it looks like an event, use search tools to check if it already exists
5. Call submit_decision with your decision

IMPORTANT: You MUST call get_images before submitting any decision other than "ignore". Event details are often only in images.

For submit_decision, you must provide:
- is_event: boolean
- confidence: number 0.0-1.0
- action: "create", "update", "cancel", "ignore", or "flag_for_review"
- reasoning: explanation of your decision
- event: object with title, date (YYYY-MM-DD), time (HH:MM or null), etc. Required if is_event=true
  - day_of_week: optional field inside the event object. If you know the day of week for the event date (e.g. the post says "this Saturday"), include it (e.g. "Saturday"). The tool will validate your date calculation and return a helpful error with the correct date if it is wrong.
- related_event_id: calendar event ID if updating/canceling an existing event

For search_events_by_date, the optional day_of_week parameter works the same way: if you know the day of week for start_date, provide it and the tool will catch any date calculation mistake before you search.

If the action is "flag_for_review", you should provide a detailed explanation of why you're flagging it for review.
This should be used if you feel something with the workflow is broken (API error, information you've been told to expect is missing, etc.)

Edge cases:

- If several events seem related or are happening concurrently, it's OK to create multiple events, especially if they start at different times.
    - For example, One post may announce a ride, and another may announce a pre-ride meetup.  If these are organized by different people, at different locations/times, create separate events for each.
    - When in doubt,
      - creaete separate events rather than merging them!
      - merge the events into one by combining the details and expanding the time slot.
- If you get a validation error from submit_decision, fix the issue and try again.
- If it's spoken about as past tense, your decision should be to ignore it.
- If you are obviously missing a date, your decision should be to ignore it.
- If you have the date but are missing a start time, create the event with a null time.
- In rare cases, a single post may announce multiple events.
  - If these are clearly distinct events with all the necessary details, create separate events by calling submit_decision multiple times.
  - DO NOT create more than 5 events from a single post.  If you think more than 5 events are needed, flag_for_review instead.

How to write a good description:
If you can find these details in the post, they're always worth including.

<Begin description guidance>
    Distance: [if the post specified a distance, include it here]
    
    Time: [sometimes the meet time will be a bit before the roll out. If stated, include it here]
    
    Start and Finish: [if the post specifies a location for the start of the event, include it here]
    
    Pace: [if the post specifies a pace, include it here. It might be a number, or style like "easy" or "no-drop" or "party pace"]
    
    Link: [REQUIRED! Always have at least one link! Choose the most relevant link from the post]
    
    Leaders: [if the post specifically names leaders, include them here]

    [Other details as relevant]
</End description guidance>
<Begin Sampole descriptions>
    <Sample description 1>
    Group ride (no-drop) Bonesaw Cycling Collective Winter Tuesday rides.
    
    When: Last Tuesday of each month. Meet at 6:45 PM. Meet at 6:45 pm, roll at 7 pm. 

    Start and Finish: Martin Olav Sabo Bridge

    Distance: typically 10-15 miles. Pace: typically 10-12 mph. 

    Our winter ride series starts the last week of November and goes through March! Make sure to dress in layers and bring lights!

    Link: https://bonesawcycling.bike/events
    </Sample description 1>
    <Sample description 2>
    Group ride (no-drop) Behind Bars Ice Skating Ride. Instagram 

    When: Saturday Jan 3, 2026 2:00 PM. Roll at 2:15pm.

    Start: Behind Bars Bicycle Shop Finish: Lake of the Isles ice skating rink

    Distance: ~5 miles. Pace: typically ~12 mph. 

    Ice skating at Lake of the Isles. If you do not have your own ice skates that is okay! There are some available to borrow from the Lake of the Isles warming hut.

    Link: https://www.instagram.com/p/DT_ZXQLCWeh/
    </Sample description 2>
</End Sample descriptions>

For the sake of reasoning about relative dates (i.e. "this saturday"), the current date and time is {local_time_str(datetime.now(timezone.utc))}. The timezone is {TIME_ZONE}. 
It is OK to create events for dates in the past if the post was published in the past (the post speaks of the event in present or future tense).

You MUST call submit_decision before exiting."""

TOOLS = [
    {
        "name": "get_images",
        "description": "Fetch the images attached to this post. Call this if the post could plausibly be an event. Images often contain event posters with dates, times, and locations. You MUST call this before any non-ignore decision.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "search_events_by_date",
        "description": "Search the calendar for events in a date range.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format",
                },
                "end_date": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD format",
                },
                "day_of_week": {
                    "type": "string",
                    "description": "Optional: the expected day of week for start_date (e.g. 'Monday', 'Saturday'). If you know the day of week, provide it here and the tool will validate your date calculation, returning an error with a correction if it is wrong.",
                },
            },
            "required": ["start_date", "end_date"],
        },
    },
    {
        "name": "search_events_by_keyword",
        "description": "Search the calendar for events matching any of the given keywords. Returns the 5 nearest upcoming events that match at least one keyword.",
        "input_schema": {
            "type": "object",
            "properties": {
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "description": 'List of search terms to match against (e.g., ["Unity Ride", "Unity", "Sunday ride"]). An event matching ANY keyword will be returned.',
                },
            },
            "required": ["keywords"],
        },
    },
    {
        "name": "submit_decision",
        "description": "Submit a decision about this post. You MUST call this tool at least once. If the post announces multiple events, call it multiple times with done=false, then done=true on the last call.",
        "input_schema": {
            "type": "object",
            "properties": {
                "is_event": {
                    "type": "boolean",
                    "description": "Whether this post announces an event",
                },
                "confidence": {
                    "type": "number",
                    "description": "Confidence level 0.0-1.0",
                },
                "action": {
                    "type": "string",
                    "enum": ["create", "update", "cancel", "ignore", "flag_for_review"],
                    "description": "What action to take",
                },
                "reasoning": {
                    "type": "string",
                    "description": "Explanation of your decision",
                },
                "event": {
                    "type": ["object", "null"],
                    "description": "Event details. Required if is_event=true. Must have: title (string), date (YYYY-MM-DD string), time (HH:MM string or null), end_time (HH:MM string or null), timezone (string, default America/Chicago), location (string or null), description (string or null)",
                    "properties": {
                        "title": {"type": "string"},
                        "date": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$"},
                        "day_of_week": {
                            "type": "string",
                            "description": "Optional: the expected day of week for this event's date (e.g. 'Monday', 'Saturday'). If you know the day of week, provide it here and the tool will validate your date calculation, returning an error with a correction if it is wrong.",
                        },
                        "time": {"type": ["string", "null"]},
                        "end_time": {"type": ["string", "null"]},
                        "timezone": {"type": "string"},
                        "location": {"type": ["string", "null"]},
                        "description": {"type": ["string", "null"]},
                    },
                    "required": ["title", "date"],
                },
                "related_event_id": {
                    "type": ["string", "null"],
                    "description": "Calendar event ID if updating or canceling an existing event",
                },
                "done": {
                    "type": "boolean",
                    "description": "Set to true if this is your last decision for this post. Set to false if you plan to submit more decisions (e.g., multiple events from one post).",
                },
            },
            "required": ["is_event", "confidence", "action", "reasoning", "done"],
        },
    },
]


class AnalysisContext:
    """Context for a single post analysis, tracking tokens and state."""

    def __init__(self, post: RssPost, dry_run: bool = False):
        self.post = post
        self.dry_run = dry_run
        self.input_tokens = 0
        self.output_tokens = 0
        self.decisions: list[ClaudeDecision] = []
        self.calendar_event_ids: list[str | None] = []
        self.logger = SessionLogger(post.guid)

    @property
    def decision(self) -> ClaudeDecision | None:
        """Last decision (for backwards compat)."""
        return self.decisions[-1] if self.decisions else None

    @property
    def calendar_event_id(self) -> str | None:
        """Last calendar event ID (for backwards compat)."""
        return self.calendar_event_ids[-1] if self.calendar_event_ids else None

    @property
    def submitted(self) -> bool:
        """Whether at least one decision has been submitted."""
        return len(self.decisions) > 0

    @property
    def cost_usd(self) -> float:
        return (
            self.input_tokens * INPUT_COST_PER_M / 1_000_000
            + self.output_tokens * OUTPUT_COST_PER_M / 1_000_000
        )


def _detect_media_type(data: bytes) -> str | None:
    """Detect image media type from magic bytes."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return None


def fetch_image_as_base64(url: str) -> tuple[str, str] | None:
    """Fetch an image and return as base64 with media type."""
    try:
        response = httpx.get(url, timeout=30, follow_redirects=True)
        response.raise_for_status()

        media_type = _detect_media_type(response.content)
        if not media_type:
            print(f"Skipping unrecognized image format from {url}")
            return None

        b64 = base64.standard_b64encode(response.content).decode("utf-8")
        return media_type, b64
    except Exception as e:
        print(f"Failed to fetch image {url}: {e}")
        return None


def build_message_content(post: RssPost) -> list[dict]:
    """Build the message content with text only (images loaded on demand via get_images tool)."""
    image_count = min(len(post.image_urls), 5)
    image_note = (
        f"\n\nThis post has {image_count} image(s) available. Call get_images to view them."
        if image_count > 0
        else "\n\nThis post has no images."
    )

    text = f"""Analyze this RSS post:

Title: {post.title}
Author: {post.author or "Unknown"}
Link: {post.link}
Published: {local_time_str(post.published) if post.published else "Unknown"}

Content:
{post.content}{image_note}

Remember: You MUST call submit_decision with your final decision."""
    return [{"type": "text", "text": text}]


def execute_get_images(ctx: AnalysisContext) -> list[dict]:
    """Fetch post images and return as content blocks for a tool result."""
    content_blocks: list[dict] = []
    fetched = 0

    for url in ctx.post.image_urls[:5]:
        image_data = fetch_image_as_base64(url)
        if image_data:
            media_type, b64 = image_data
            content_blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": b64,
                    },
                }
            )
            fetched += 1

    if not content_blocks:
        content_blocks.append({"type": "text", "text": "No images could be loaded."})
    else:
        content_blocks.insert(
            0, {"type": "text", "text": f"Loaded {fetched} image(s)."}
        )

    return content_blocks


_DAY_NAMES = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]


def validate_day_of_week(date_str: str, day_of_week: str) -> str | None:
    """Check that date_str falls on the given day of week.

    Returns None if valid, or an error message with nearby suggestions if not.
    """
    from datetime import date, timedelta

    normalized = day_of_week.strip().capitalize()
    # Accept abbreviations like "Mon", "Tue", etc.
    if normalized not in _DAY_NAMES:
        for day in _DAY_NAMES:
            if day.lower().startswith(normalized.lower()):
                normalized = day
                break
        else:
            return f"Unknown day of week: '{day_of_week}'. Use a name like 'Monday', 'Tuesday', etc."

    try:
        d = date.fromisoformat(date_str)
    except ValueError:
        return f"Invalid date format: '{date_str}'. Expected YYYY-MM-DD."

    actual_day = _DAY_NAMES[d.weekday()]
    if actual_day == normalized:
        return None  # Valid

    # Build "did you mean" suggestions: nearest past and next matching dates
    expected_idx = _DAY_NAMES.index(normalized)
    actual_idx = d.weekday()
    days_forward = (expected_idx - actual_idx) % 7
    days_backward = (actual_idx - expected_idx) % 7

    def fmt(dt: "date") -> str:
        return f"{dt.strftime('%b')} {dt.day}, {dt.year}"

    prev_date = d - timedelta(days=days_backward)
    next_date = d + timedelta(days=days_forward)
    actual_date_str = fmt(d)

    return (
        f"{actual_date_str} is a {actual_day}, not a {normalized}. "
        f"Did you mean {fmt(prev_date)} ({normalized}) or {fmt(next_date)} ({normalized})?"
    )


def execute_tool(name: str, input_data: dict, ctx: AnalysisContext) -> Any:
    """Execute a tool and return the result."""
    if name == "get_images":
        return execute_get_images(ctx)

    elif name == "search_events_by_date":
        if day_of_week := input_data.get("day_of_week"):
            error = validate_day_of_week(input_data["start_date"], day_of_week)
            if error:
                return {"error": error}
        events = calendar.search_events_by_date(
            start_date=input_data["start_date"],
            end_date=input_data["end_date"],
        )
        return [
            {
                "id": e.id,
                "title": e.title,
                "start": e.start.isoformat(),
                "location": e.location,
                "description": e.description,
            }
            for e in events
        ]

    elif name == "search_events_by_keyword":
        events = calendar.search_events_by_keyword(keywords=input_data["keywords"])
        return [
            {
                "id": e.id,
                "title": e.title,
                "start": e.start.isoformat(),
                "location": e.location,
                "description": e.description,
            }
            for e in events
        ]

    elif name == "submit_decision":
        return handle_submit_decision(input_data, ctx)

    else:
        return {"error": f"Unknown tool: {name}"}


def handle_submit_decision(input_data: dict, ctx: AnalysisContext) -> dict:
    """Validate and process the submit_decision tool call."""
    try:
        # Validate event details if present
        event = None
        if input_data.get("event"):
            event_data = dict(input_data["event"])
            # Validate day_of_week before creating the event
            if day_of_week := event_data.pop("day_of_week", None):
                dow_error = validate_day_of_week(event_data["date"], day_of_week)
                if dow_error:
                    return {"error": dow_error}
            event = EventDetails(**event_data)

        # Validate the full decision
        decision = ClaudeDecision(
            is_event=input_data["is_event"],
            confidence=input_data["confidence"],
            action=Action(input_data["action"]),
            reasoning=input_data["reasoning"],
            event=event,
            related_event_id=input_data.get("related_event_id"),
        )

        # Validation passed - now execute the action
        calendar_event_id = None

        if not ctx.dry_run:
            if decision.action == Action.CREATE and decision.event:
                calendar_event_id = calendar.create_event(decision.event)
            elif (
                decision.action == Action.UPDATE
                and decision.event
                and decision.related_event_id
            ):
                calendar_event_id = calendar.update_event(
                    decision.related_event_id, decision.event
                )
            elif decision.action == Action.CANCEL and decision.related_event_id:
                calendar.delete_event(decision.related_event_id)
                calendar_event_id = decision.related_event_id

        # Record to database
        db.record_processed(
            post_guid=ctx.post.guid,
            decision=decision.action,
            calendar_event_id=calendar_event_id,
            reasoning=decision.reasoning,
            input_tokens=ctx.input_tokens,
            output_tokens=ctx.output_tokens,
            cost_usd=ctx.cost_usd,
            post_title=ctx.post.title,
            post_author=ctx.post.author,
            post_time=ctx.post.published.isoformat() if ctx.post.published else None,
            post_link=ctx.post.link,
            event=decision.event,
        )

        ctx.decisions.append(decision)
        ctx.calendar_event_ids.append(calendar_event_id)

        done = input_data.get("done", True)
        return {
            "success": True,
            "action": decision.action.value,
            "calendar_event_id": calendar_event_id,
            "done": done,
        }

    except ValidationError as e:
        # Return validation error so Claude can fix it
        errors = e.errors()
        error_msgs = [f"{err['loc']}: {err['msg']}" for err in errors]
        return {"error": "Validation failed", "details": error_msgs}

    except Exception as e:
        return {"error": str(e)}


def analyze_post(post: RssPost, dry_run: bool = False) -> AnalysisContext:
    """Analyze a post using Claude. Returns the context with results."""
    client = Anthropic()
    ctx = AnalysisContext(post, dry_run)

    user_content = build_message_content(post)
    ctx.logger.log_user_message(user_content)

    messages = [{"role": "user", "content": user_content}]

    # Agentic loop
    max_turns = 10
    for _ in range(max_turns):
        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,  # ty: ignore[invalid-argument-type]
            messages=messages,  # ty: ignore[invalid-argument-type]
        )

        # Track tokens
        ctx.input_tokens += response.usage.input_tokens
        ctx.output_tokens += response.usage.output_tokens

        if response.stop_reason == "tool_use":
            tool_results = []
            assistant_content = []
            done = False

            for block in response.content:
                assistant_content.append(block)
                if block.type == "tool_use":
                    result = execute_tool(block.name, block.input, ctx)
                    # get_images returns content blocks (with images); others return JSON-serializable data
                    if block.name == "get_images":
                        content = result
                    else:
                        content = json.dumps(result)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": content,
                        }
                    )

                    if (
                        block.name == "submit_decision"
                        and isinstance(result, dict)
                        and result.get("done")
                    ):
                        done = True

            ctx.logger.log_turn(response, tool_results)

            if done and ctx.submitted:
                ctx.logger.log_final(ctx)
                return ctx

            messages.append({"role": "assistant", "content": assistant_content})
            messages.append({"role": "user", "content": tool_results})

        elif response.stop_reason == "end_turn":
            ctx.logger.log_turn(response)
            if ctx.submitted:
                ctx.logger.log_final(ctx)
                return ctx
            # Claude stopped without ever calling submit_decision
            error_msg = (
                f"Claude exited without calling submit_decision. "
                f"Tokens used: {ctx.input_tokens} in / {ctx.output_tokens} out (${ctx.cost_usd:.4f})"
            )
            ctx.logger.log_error(error_msg)
            raise RuntimeError(error_msg)

        else:
            error_msg = f"Unexpected stop reason: {response.stop_reason}"
            ctx.logger.log_error(error_msg)
            raise RuntimeError(error_msg)

    # Max turns exceeded
    error_msg = (
        f"Max turns ({max_turns}) exceeded without submit_decision. "
        f"Tokens used: {ctx.input_tokens} in / {ctx.output_tokens} out (${ctx.cost_usd:.4f})"
    )
    ctx.logger.log_error(error_msg)
    raise RuntimeError(error_msg)
