"""Pydantic models for calendar sync decisions."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class Action(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    CANCEL = "cancel"
    IGNORE = "ignore"
    FLAG = "flag_for_review"


class EventDetails(BaseModel):
    """Extracted event information."""

    title: str
    date: str  # ISO date string
    time: Optional[str] = None  # HH:MM format
    end_time: Optional[str] = None
    timezone: str = "America/Chicago"
    location: Optional[str] = None
    description: Optional[str] = None


class ClaudeDecision(BaseModel):
    """Claude's decision about an RSS post."""

    is_event: bool
    confidence: float
    event: Optional[EventDetails] = None
    action: Action
    related_event_id: Optional[str] = None
    reasoning: str


class RssPost(BaseModel):
    """An RSS post to process."""

    guid: str
    title: str
    link: str
    content: str
    author: Optional[str] = None
    published: Optional[datetime] = None
    image_urls: list[str] = []


class CalendarEvent(BaseModel):
    """A Google Calendar event."""

    id: str
    title: str
    start: datetime
    end: Optional[datetime] = None
    location: Optional[str] = None
    description: Optional[str] = None
