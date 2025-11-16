import re
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


class Activity(BaseModel):
    time: str = Field(
        ...,
        description="Local time label, e.g., '09:00 AM'",
    )
    title: str
    location: str | None = None
    description: str | None = None
    image: str | None = Field(None, description="Image URL (absolute or relative)")

    # Google Places API enrichment fields (optional)
    place_id: str | None = Field(None, description="Google Place ID")
    address: str | None = Field(None, description="Full address")
    rating: float | None = Field(None, description="Google rating (1-5)")
    price_level: int | None = Field(None, description="Price level (1-4)")
    google_maps_url: str | None = Field(None, description="Google Maps link")
    # Distance to next activity (None for last activity of the day)
    distance_to_next: float | None = Field(
        None, description="Distance to next activity in kilometers"
    )


class Day(BaseModel):
    date: str = Field(
        ...,
        description="Display date, e.g., 'Friday, March 15'",
    )
    activities: list[Activity] = Field(default_factory=list)


class GroupParticipant(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr | None = None
    email_sent: bool = False
    email_sent_at: datetime | None = None


class GroupInfo(BaseModel):
    invite_id: str | None = None
    participants: list[GroupParticipant] = Field(default_factory=list)
    collect_preferences: bool | None = False


class ItineraryDocument(BaseModel):
    trip_name: str = Field(..., description="User-provided name for the trip")
    traveler_name: str
    destination: str
    dates: str
    duration: str
    cover_image: str | None = Field(None, description="Cover image URL (absolute or relative)")
    days: list[Day] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    # Optional group trip metadata
    trip_type: str | None = Field(
        default=None, pattern="^(solo|group)$", description="Type of trip"
    )
    group: GroupInfo | None = None
    # Extracted city name for browser title (extracted from destination)
    city: str | None = Field(
        default=None,
        description=(
            "City name extracted from destination " "(e.g., 'Paris' from 'Paris, France')"
        ),
    )


# =============================================================================
# User Authentication Schemas
# =============================================================================


class UserBase(BaseModel):
    """Base user model with common fields."""

    email: EmailStr
    username: str
    full_name: str | None = None


class UserUpdate(BaseModel):
    """Schema for updating user information."""

    username: str | None = None
    full_name: str | None = None
    email: EmailStr | None = None
    onboarding_completed: bool | None = None
    onboarding_skipped: bool | None = None


class OnboardingUpdate(BaseModel):
    """Schema for updating onboarding status."""

    onboarding_completed: bool | None = None
    onboarding_skipped: bool | None = None


class UserPreferences(BaseModel):
    """Schema for user travel preferences."""

    # Travel style sliders (0-100 values)
    budget_style: int = Field(
        50,
        ge=0,
        le=100,
        description="Budget vs Luxury preference (0=Budget, 100=Luxury)",
    )
    pace_style: int = Field(
        50,
        ge=0,
        le=100,
        description="Relaxation vs Adventure preference (0=Relaxation, 100=Adventure)",
    )
    schedule_style: int = Field(
        50,
        ge=0,
        le=100,
        description="Early Bird vs Night Owl preference (0=Early Bird, 100=Night Owl)",
    )

    # Selected interests
    selected_interests: list[str] = Field(
        default_factory=list, description="List of selected interest sub-items"
    )

    # Other interests (free text)
    other_interests: str | None = Field(
        None,
        max_length=500,
        description="Additional interests not covered in categories",
    )

    # Metadata
    created_at: datetime | None = None
    updated_at: datetime | None = None


class UserPreferencesCreate(BaseModel):
    """Schema for creating user preferences."""

    budget_style: int = Field(50, ge=0, le=100)
    pace_style: int = Field(50, ge=0, le=100)
    schedule_style: int = Field(50, ge=0, le=100)
    selected_interests: list[str] = Field(default_factory=list)
    other_interests: str | None = Field(None, max_length=500)


class ClerkUserSync(BaseModel):
    """Schema for syncing user data from Clerk"""

    clerk_user_id: str
    email: EmailStr
    email_verified: bool = False
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    full_name: str | None = None
    image_url: str | None = None


class User(UserBase):
    """Complete user model returned by API."""

    id: str
    clerk_user_id: str | None = None  # Clerk integration
    email_verified: bool = False
    first_name: str | None = None
    last_name: str | None = None
    image_url: str | None = None
    is_active: bool = True
    scopes: list[str] = Field(default_factory=lambda: ["user"])  # For role-based access
    onboarding_completed: bool = False
    onboarding_skipped: bool = False
    first_itinerary_email_sent: bool = False  # Track if first itinerary email was sent
    created_at: datetime
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


# =============================================================================
# Calendar & Trip Invite Schemas
# =============================================================================


class InviteParticipantBase(BaseModel):
    """Base participant model."""

    email: EmailStr
    first_name: str
    last_name: str
    collect_preferences: bool = Field(
        default=False,
        description="Whether to collect travel preferences from this participant",
    )


class InviteParticipantCreate(InviteParticipantBase):
    """Schema for adding a participant to an invite."""

    pass


class InviteParticipantUpdate(BaseModel):
    """Schema for updating a participant."""

    email: EmailStr | None = None
    first_name: str | None = None
    last_name: str | None = None


class InviteParticipantResponse(InviteParticipantBase):
    """Participant returned by API."""

    is_organizer: bool = Field(
        default=False, description="Whether this participant is the trip organizer"
    )
    status: str = Field(
        default="pending",
        pattern="^(pending|invited|responded|declined|preferences_completed)$",
    )
    available_dates: list[str] | None = Field(default_factory=list, description="ISO date strings")
    has_completed_preferences: bool = Field(
        default=False, description="Whether participant has completed their preferences"
    )
    submitted_at: datetime | None = None

    class Config:
        from_attributes = True


class TripInviteBase(BaseModel):
    """Base trip invite model."""

    trip_name: str = Field(..., max_length=200)
    destination: str | None = None
    date_range_start: str | None = Field(None, description="ISO date string")
    date_range_end: str | None = Field(None, description="ISO date string")

    # Calculated dates (from date analysis algorithm)
    calculated_start_date: str | None = Field(
        None, description="Auto-calculated start date based on participant availability"
    )
    calculated_end_date: str | None = Field(
        None, description="Auto-calculated end date based on participant availability"
    )

    # Finalized dates (set by organizer)
    finalized_start_date: str | None = Field(None, description="Finalized start date for the trip")
    finalized_end_date: str | None = Field(None, description="Finalized end date for the trip")
    dates_finalized_by: str | None = Field(
        None, pattern="^(common|organizer)$", description="How dates were finalized"
    )

    # Date analysis results
    no_common_dates: bool = Field(
        default=False, description="True if no common dates found with >50% overlap"
    )
    common_dates_percentage: int | None = Field(
        None, description="Percentage of participants available for calculated dates"
    )

    collect_preferences: bool = Field(
        default=False, description="Whether to collect preferences from participants"
    )
    trip_type: str = Field(default="group", pattern="^(solo|group)$", description="Type of trip")
    cover_image: str | None = Field(None, description="Proxied cover image URL for the destination")
    itinerary_id: str | None = Field(
        None, description="ID of the itinerary created from this invite"
    )


class TripInviteCreate(TripInviteBase):
    """Schema for creating a trip invite."""

    pass


class TripInviteResponse(TripInviteBase):
    """Trip invite returned by API."""

    id: str
    organizer_clerk_id: str
    organizer_email: str
    organizer_name: str | None = None
    status: str = Field(default="draft", pattern="^(draft|sent|finalized)$")
    collect_preferences: bool = Field(default=False)
    trip_type: str = Field(default="group")
    participants: list[InviteParticipantResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CalendarResponseSubmit(BaseModel):
    """Schema for participant submitting their availability."""

    available_dates: list[str] = Field(
        ..., description="List of ISO date strings participant is available"
    )


class SendInvitesRequest(BaseModel):
    """Request to send invites to all participants."""

    message: str | None = Field(
        None, max_length=500, description="Optional message to include in invite email"
    )


class FinalizeDatesRequest(BaseModel):
    """Request to finalize dates for an invite."""

    use_common: bool = Field(
        ...,
        description="True to use calculated common dates, False to use organizer's dates",
    )


class ResendInvitesRequest(BaseModel):
    """Request to resend invites to selected participants."""

    participant_emails: list[EmailStr] = Field(
        ..., description="List of participant emails to resend invites to"
    )


# =============================================================================
# Additional Request Schemas for Dict Endpoints
# =============================================================================


class ParticipantName(BaseModel):
    """Schema for participant name only (no email required)."""

    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)


class RejectInviteRequest(BaseModel):
    """Request to reject/decline an invite."""

    email: EmailStr | None = Field(
        None, description="Participant email (optional, defaults to authenticated user)"
    )


class UpdateParticipantPreferencesRequest(BaseModel):
    """Request to update participant preferences collection setting."""

    collect_preferences: bool = Field(
        ..., description="Whether to collect preferences from this participant"
    )


class UpdateParticipantsRequest(BaseModel):
    """Request to update itinerary participants list."""

    participants: list[ParticipantName] = Field(
        ..., max_length=20, description="List of participants"
    )


class ShareItineraryRequest(BaseModel):
    """Request to share an itinerary with participants."""

    participants: list[EmailStr] = Field(
        ..., max_length=20, description="List of participant emails"
    )
    message: str | None = Field(None, max_length=500, description="Optional message to include")


# =============================================================================
# Itinerary Generation Schemas
# =============================================================================


class ItineraryGenerateRequest(BaseModel):
    """Schema for itinerary generation request."""

    trip_name: str = Field(..., min_length=1, max_length=50)
    traveler_name: str = Field(..., min_length=1, max_length=100)
    destination: str = Field(..., min_length=1, max_length=200)
    destination_place_id: str | None = Field(
        None,
        description="Google Place ID from autocomplete (more reliable than geocoding)",
    )
    dates: str = Field(
        ...,
        description="Date range in format 'YYYY-MM-DD - YYYY-MM-DD'",
    )
    duration: str | None = Field(None, max_length=50)
    clerk_user_id: str | None = Field(None, max_length=100)
    trip_type: str = Field(default="solo", pattern="^(solo|group)$")
    invite_id: str | None = Field(None, max_length=100)
    participants: list[ParticipantName] = Field(default_factory=list, max_length=20)
    notes: str | None = Field(None, max_length=1000)
    vibe_notes: str | None = Field(None, max_length=500)

    @field_validator("dates")
    @classmethod
    def validate_dates(cls, v: str) -> str:
        """Validate date format and range."""
        from datetime import datetime

        if not v or not isinstance(v, str):
            raise ValueError("dates is required and must be a string")

        # Check format: "YYYY-MM-DD - YYYY-MM-DD"
        parts = v.split(" - ")
        if len(parts) != 2:
            raise ValueError("Invalid date format. Expected 'YYYY-MM-DD - YYYY-MM-DD'")

        start_s, end_s = parts[0].strip(), parts[1].strip()

        # Validate date format
        try:
            start = datetime.fromisoformat(start_s)
            end = datetime.fromisoformat(end_s)
        except ValueError as e:
            raise ValueError(f"Invalid date format: {e}") from e

        # Validate date range
        if end < start:
            raise ValueError("End date must be after start date")

        days_diff = (end - start).days + 1
        if days_diff > 7:
            raise ValueError("Trip duration cannot exceed 7 days")
        if days_diff < 1:
            raise ValueError("Trip duration must be at least 1 day")

        return v

    @field_validator("trip_name", "traveler_name", "destination")
    @classmethod
    def validate_string_fields(cls, v: str) -> str:
        """Sanitize string fields by stripping whitespace."""
        if not isinstance(v, str):
            raise ValueError("Field must be a string")
        return v.strip()

    @field_validator("vibe_notes", "notes")
    @classmethod
    def validate_optional_text_fields(cls, v: str | None) -> str | None:
        """Sanitize optional text fields."""
        if v is None:
            return None
        if not isinstance(v, str):
            raise ValueError("Field must be a string or None")
        return v.strip()


# =============================================================================
# Path Parameter Validation Schemas
# =============================================================================


class ClerkUserId(BaseModel):
    """Validated Clerk user ID from path parameters."""

    clerk_user_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        pattern="^[a-zA-Z0-9_-]+$",
        description="Clerk user ID (alphanumeric, underscores, hyphens only)",
    )

    @classmethod
    def validate(cls, value: str) -> str:
        """Validate and sanitize Clerk user ID."""
        if not value or not isinstance(value, str):
            raise ValueError("clerk_user_id must be a non-empty string")
        value = value.strip()
        if len(value) > 100:
            raise ValueError("clerk_user_id exceeds maximum length")
        if not re.match(r"^[a-zA-Z0-9_-]+$", value):
            raise ValueError(
                "clerk_user_id contains invalid characters. "
                "Only alphanumeric, underscores, and hyphens allowed"
            )
        return value


class ItineraryId(BaseModel):
    """Validated itinerary ID from path parameters."""

    itinerary_id: str = Field(
        ...,
        min_length=1,
        max_length=50,
        pattern="^[a-zA-Z0-9_-]+$",
        description="Itinerary ID (alphanumeric, underscores, hyphens only)",
    )

    @classmethod
    def validate(cls, value: str) -> str:
        """Validate and sanitize itinerary ID."""
        if not value or not isinstance(value, str):
            raise ValueError("itinerary_id must be a non-empty string")
        value = value.strip()
        if len(value) > 50:
            raise ValueError("itinerary_id exceeds maximum length")
        if not re.match(r"^[a-zA-Z0-9_-]+$", value):
            raise ValueError(
                "itinerary_id contains invalid characters. "
                "Only alphanumeric, underscores, and hyphens allowed"
            )
        return value


class InviteId(BaseModel):
    """Validated invite ID from path parameters."""

    invite_id: str = Field(
        ...,
        min_length=1,
        max_length=50,
        pattern="^[a-zA-Z0-9_-]+$",
        description="Invite ID (alphanumeric, underscores, hyphens only)",
    )

    @classmethod
    def validate(cls, value: str) -> str:
        """Validate and sanitize invite ID."""
        if not value or not isinstance(value, str):
            raise ValueError("invite_id must be a non-empty string")
        value = value.strip()
        if len(value) > 50:
            raise ValueError("invite_id exceeds maximum length")
        if not re.match(r"^[a-zA-Z0-9_-]+$", value):
            raise ValueError(
                "invite_id contains invalid characters. "
                "Only alphanumeric, underscores, and hyphens allowed"
            )
        return value
