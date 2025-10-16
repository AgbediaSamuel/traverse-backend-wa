from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field, HttpUrl


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


# =============================================================================
# User Authentication Schemas
# =============================================================================


class UserBase(BaseModel):
    """Base user model with common fields."""

    email: EmailStr
    username: str
    full_name: Optional[str] = None


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

    username: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    onboarding_completed: Optional[bool] = None
    onboarding_skipped: Optional[bool] = None


class OnboardingUpdate(BaseModel):
    """Schema for updating onboarding status."""

    onboarding_completed: Optional[bool] = None
    onboarding_skipped: Optional[bool] = None


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
    selected_interests: List[str] = Field(
        default_factory=list, description="List of selected interest sub-items"
    )

    # Other interests (free text)
    other_interests: Optional[str] = Field(
        None,
        max_length=500,
        description="Additional interests not covered in categories",
    )

    # Metadata
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class UserPreferencesCreate(BaseModel):
    """Schema for creating user preferences."""

    budget_style: int = Field(50, ge=0, le=100)
    pace_style: int = Field(50, ge=0, le=100)
    schedule_style: int = Field(50, ge=0, le=100)
    selected_interests: List[str] = Field(default_factory=list)
    other_interests: Optional[str] = Field(None, max_length=500)


class ClerkUserSync(BaseModel):
    """Schema for syncing user data from Clerk"""

    clerk_user_id: str
    email: EmailStr
    email_verified: bool = False
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    image_url: Optional[str] = None


class User(UserBase):
    """Complete user model returned by API."""

    id: str
    clerk_user_id: Optional[str] = None  # Clerk integration
    email_verified: bool = False
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    image_url: Optional[str] = None
    is_active: bool = True
    scopes: List[str] = Field(default_factory=lambda: ["user"])  # For role-based access
    onboarding_completed: bool = False
    onboarding_skipped: bool = False
    created_at: datetime
    updated_at: Optional[datetime] = None

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

    email: Optional[str] = None
    scopes: List[str] = Field(default_factory=list)


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


class ChatSessionCreate(ChatSessionBase):
    """Schema for creating a chat session."""

    pass


class ChatSessionResponse(BaseModel):
    """Chat session returned by API."""

    id: str
    clerk_user_id: str
    status: str = Field(default="active", pattern="^(active|finalized)$")
    itinerary_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    messages: List[dict] = Field(default_factory=list)

    class Config:
        from_attributes = True


class FinalizeSessionResponse(BaseModel):
    """Response from finalizing a session."""

    message: str
    itinerary_id: str
    new_session_id: str
    itinerary_url: str
