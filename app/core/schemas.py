from typing import List, Optional

from pydantic import BaseModel, Field, HttpUrl


class Activity(BaseModel):
    time: str = Field(
        ...,
        description="Local time label, e.g., '09:00 AM'",
    )
    title: str
    location: Optional[str] = None
    description: Optional[str] = None
    image: Optional[HttpUrl] = None


class Day(BaseModel):
    date: str = Field(
        ...,
        description="Display date, e.g., 'Friday, March 15'",
    )
    activities: List[Activity] = Field(default_factory=list)


class ItineraryDocument(BaseModel):
    traveler_name: str
    destination: str
    dates: str
    duration: str
    cover_image: Optional[HttpUrl] = None
    days: List[Day] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)
