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


class Tag(str, Enum):
    GROUP_RIDE_NO_DROP = "group_ride_no_drop"
    GROUP_RIDE_DROP = "group_ride_drop"
    SELF_SUPPORTED_RIDE = "self_supported_ride"
    ORGANIZED_RIDE = "organized_ride"
    RACE_ALLEYCAT = "race_alleycat"
    RACE_CX = "race_cx"
    RACE_GRAVEL = "race_gravel"
    RACE_MTB = "race_mtb"
    RACE_OTHER = "race_other"
    BIKE_POLO = "bike_polo"
    CLASS_SEMINAR = "class_seminar"
    GATHERING = "gathering"
    SKILLS_CLINIC = "skills_clinic"
    CAMPING = "camping"
    MAINTENANCE = "maintenance"
    SALE_SWAP_MEET = "sale_swap_meet"


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
