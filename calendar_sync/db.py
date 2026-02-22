"""SQLite database for tracking processed posts."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .models import Action, EventDetails


def get_db_path() -> Path:
    """Get the database file path."""
    return Path(__file__).parent.parent / "data" / "calendar_sync.db"


def init_db() -> None:
    """Initialize the database schema."""
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS processed_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_guid TEXT NOT NULL,
            processed_at TEXT NOT NULL,
            decision TEXT NOT NULL,
            calendar_event_id TEXT,
            post_content TEXT,
            reasoning TEXT,
            input_tokens INTEGER,
            output_tokens INTEGER,
            cost_usd REAL,
            post_title TEXT,
            post_author TEXT,
            post_time TEXT,
            post_link TEXT,
            event_title TEXT,
            event_date TEXT,
            event_time TEXT,
            event_location TEXT
        )
    """)

    conn.commit()
    conn.close()


def is_processed(post_guid: str) -> bool:
    """Check if a post has already been processed."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()

    cursor.execute(
        "SELECT 1 FROM processed_posts WHERE post_guid = ?",
        (post_guid,),
    )
    result = cursor.fetchone() is not None

    conn.close()
    return result


def get_processed(post_guid: str) -> list[dict]:
    """Get all processing records for a post."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM processed_posts WHERE post_guid = ? ORDER BY id",
        (post_guid,),
    )
    rows = cursor.fetchall()

    conn.close()
    return [dict(row) for row in rows]


def record_processed(
    post_guid: str,
    decision: Action,
    calendar_event_id: Optional[str] = None,
    post_content: str = "",
    reasoning: Optional[str] = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cost_usd: float = 0.0,
    post_title: Optional[str] = None,
    post_author: Optional[str] = None,
    post_time: Optional[str] = None,
    post_link: Optional[str] = None,
    event: Optional[EventDetails] = None,
) -> None:
    """Record that a post has been processed."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO processed_posts
        (post_guid, processed_at, decision, calendar_event_id, post_content, reasoning,
         input_tokens, output_tokens, cost_usd, post_title, post_author,
         post_time, post_link, event_title, event_date, event_time, event_location)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            post_guid,
            datetime.now(timezone.utc).isoformat(),
            decision.value,
            calendar_event_id,
            post_content,
            reasoning,
            input_tokens,
            output_tokens,
            cost_usd,
            post_title,
            post_author,
            post_time,
            post_link,
            event.title if event else None,
            event.date if event else None,
            event.time if event else None,
            event.location if event else None,
        ),
    )

    conn.commit()
    conn.close()


def delete_processed(post_guid: str) -> bool:
    """Delete a processing record so the post can be re-processed.

    Returns True if a record was deleted, False if not found.
    """
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM processed_posts WHERE post_guid = ?",
        (post_guid,),
    )
    deleted = cursor.rowcount > 0

    conn.commit()
    conn.close()
    return deleted


def get_history(limit: int = 20) -> list[dict]:
    """Get recent processing history."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM processed_posts
        ORDER BY processed_at DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = cursor.fetchall()

    conn.close()
    return [dict(row) for row in rows]


def get_rows_by_calendar_event_ids(event_ids: list[str]) -> dict[str, dict]:
    """Return a mapping of calendar_event_id → most-recent DB row for each id."""
    if not event_ids:
        return {}

    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    placeholders = ",".join("?" * len(event_ids))
    cursor.execute(
        f"""
        SELECT * FROM processed_posts
        WHERE calendar_event_id IN ({placeholders})
        ORDER BY id ASC
        """,
        event_ids,
    )
    rows = cursor.fetchall()
    conn.close()

    # Keep only the most-recent row per calendar_event_id (ORDER BY id DESC)
    result: dict[str, dict] = {}
    for row in rows:
        d = dict(row)
        eid = d["calendar_event_id"]
        if eid not in result:
            result[eid] = d
    return result


def get_total_cost() -> float:
    """Get total cost across all processed posts."""
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()

    cursor.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM processed_posts")
    result = cursor.fetchone()[0]

    conn.close()
    return result
