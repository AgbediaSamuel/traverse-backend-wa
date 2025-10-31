from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, HttpUrl


class Activity(BaseModel):
    time: str = Field(
        ...,
        description="Local time label, e.g., '09:00 AM'",
    )
    title: str
    location: str | None = None
    description: str | None = None
    image: HttpUrl | None = None

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
    cover_image: HttpUrl | None = None
    days: list[Day] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    # Optional group trip metadata
    trip_type: str | None = Field(
        default=None, pattern="^(solo|group)$", description="Type of trip"
    )
    group: GroupInfo | None = None


# =============================================================================
# User Authentication Schemas
# =============================================================================


class UserBase(BaseModel):
    """Base user model with common fields."""

    email: EmailStr
    username: str
    full_name: str | None = None


class UserCreate(UserBase):
    """Schema for user registration."""

    password: str = Field(
        ..., min_length=8, description="Password must be at least 8 characters"
    )


class UserLogin(BaseModel):
    """Schema for user login."""

    email: EmailStr
    password: str


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
    created_at: datetime
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class UserInDB(User):
    """User model as stored in database (includes hashed password)."""

    hashed_password: str


# =============================================================================
# Authentication Response Schemas
# =============================================================================


class Token(BaseModel):
    """JWT token response."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class TokenData(BaseModel):
    """Token payload data."""

    email: str | None = None
    scopes: list[str] = Field(default_factory=list)


class RefreshToken(BaseModel):
    """Refresh token request."""

    refresh_token: str


class PasswordReset(BaseModel):
    """Password reset request."""

    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Password reset confirmation."""

    token: str
    new_password: str = Field(..., min_length=8)


# =============================================================================
# Chat Session Schemas
# =============================================================================


class ChatSessionBase(BaseModel):
    """Base chat session model."""

    clerk_user_id: str
    trip_type: str | None = Field(
        None, pattern="^(solo|group)$", description="Type of trip: solo or group"
    )


class ChatSessionCreate(ChatSessionBase):
    """Schema for creating a chat session."""

    pass


class ChatSessionResponse(BaseModel):
    """Chat session returned by API."""

    id: str
    clerk_user_id: str
    trip_type: str | None = Field(None, pattern="^(solo|group)$")
    status: str = Field(default="active", pattern="^(active|finalized)$")
    itinerary_id: str | None = None
    created_at: datetime
    updated_at: datetime
    messages: list[dict] = Field(default_factory=list)

    class Config:
        from_attributes = True


class FinalizeSessionResponse(BaseModel):
    """Response from finalizing a session."""

    message: str
    itinerary_id: str
    new_session_id: str
    itinerary_url: str


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
