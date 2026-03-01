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
    GROUP_RIDE_NO_DROP = "nodrop"
    GROUP_RIDE_DROP = "drop"
    SELF_SUPPORTED_RIDE = "selfsupported"
    ORGANIZED_RIDE = "organized"
    RACE_ALLEYCAT = "alleycat"
    RACE_CX = "cx"
    RACE_GRAVEL = "gravel"
    RACE_MTB = "mtb"
    RACE_OTHER = "race"
    BIKE_POLO = "polo"
    CLASS_SEMINAR = "class"
    GATHERING = "gathering"
    SKILLS_CLINIC = "clinic"
    CAMPING = "camping"
    MAINTENANCE = "maintenance"
    SALE_SWAP_MEET = "swap"


TAG_TITLES = {
    Tag.GROUP_RIDE_NO_DROP: "Group Ride (No Drop)",
    Tag.GROUP_RIDE_DROP: "Group Ride (Drop)",
    Tag.SELF_SUPPORTED_RIDE: "Self-Supported Ride",
    Tag.ORGANIZED_RIDE: "Organized Ride",
    Tag.RACE_ALLEYCAT: "Alleycat Race",
    Tag.RACE_CX: "Cyclocross Race",
    Tag.RACE_GRAVEL: "Gravel Race",
    Tag.RACE_MTB: "Mountain Bike Race",
    Tag.RACE_OTHER: "Other Race",
    Tag.BIKE_POLO: "Bike Polo",
    Tag.CLASS_SEMINAR: "Class or Seminar",
    Tag.GATHERING: "Social Gathering",
    Tag.SKILLS_CLINIC: "Skills Clinic",
    Tag.CAMPING: "Camping",
    Tag.MAINTENANCE: "Maintenance/Repair",
    Tag.SALE_SWAP_MEET: "Sale or Swap Meet",
}


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
    extra: dict = {}


class CalendarEvent(BaseModel):
    """A Google Calendar event."""

    id: str
    title: str
    start: datetime
    end: Optional[datetime] = None
    location: Optional[str] = None
    description: Optional[str] = None
