from __future__ import annotations

import os
import time
import uuid
from datetime import datetime

from dotenv import load_dotenv
from pymongo import MongoClient

from app.core.auth import get_password_hash, verify_password
from app.core.schemas import (
    ClerkUserSync,
    ItineraryDocument,
    User,
    UserCreate,
    UserInDB,
    UserPreferences,
    UserPreferencesCreate,
)
from dotenv import load_dotenv
from pymongo import MongoClient

# Load environment variables
load_dotenv()


class MongoDBRepo:
    def __init__(self):
        # Load environment variables
        load_dotenv()

        # MongoDB connection
        mongodb_uri = os.getenv("MONGODB_URI")
        database_name = os.getenv("DATABASE_NAME", "traverse_db")

        if not mongodb_uri:
            raise ValueError("MONGODB_URI environment variable is required")

        # Initialize MongoDB client with alternative connection settings
        self.client = MongoClient(mongodb_uri)

        self.db = self.client[database_name]

        # Collections
        self.itineraries_collection = self.db.itineraries
        self.users_collection = self.db.users
        self.sessions_collection = self.db.sessions
        self.preferences_collection = self.db.user_preferences
        self.trip_invites_collection = self.db.trip_invites

        # Test connection and create indexes only if connection works
        try:
            # Test the connection
            self.client.admin.command("ping")
            print("MongoDB connection successful")

            # Create indexes for better performance (only if connection works)
            try:
                self.users_collection.create_index("email", unique=True)
                self.sessions_collection.create_index("id", unique=True)
                print("Database indexes created")
            except Exception as index_error:
                print(f"Index creation failed (might already exist): {index_error}")

        except Exception as e:
            print(f"MongoDB connection failed: {e}")
            print("Will continue without database connection (for development)")

    # Sessions
    def create_session(self, session: dict) -> None:
        session_doc = {**session, "created_at": time.time()}
        self.sessions_collection.insert_one(session_doc)

    def get_session(self, session_id: str) -> dict | None:
        session_doc = self.sessions_collection.find_one({"id": session_id})
        if session_doc:
            session_doc.pop("_id", None)  # Remove MongoDB ObjectId
        return session_doc

    def update_session(self, session_id: str, data: dict) -> None:
        self.sessions_collection.update_one({"id": session_id}, {"$set": data})

    def get_active_session(self, clerk_user_id: str, trip_type: str | None = None) -> dict | None:
        """Get the active session for a user, or create one if none exists."""
        session_doc = self.sessions_collection.find_one(
            {"clerk_user_id": clerk_user_id, "status": "active"}
        )

        if session_doc:
            session_doc.pop("_id", None)
            return session_doc

        # No active session exists, create one
        session_id = f"sess_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        new_session = {
            "id": session_id,
            "clerk_user_id": clerk_user_id,
            "trip_type": trip_type,
            "status": "active",
            "itinerary_id": None,
            "messages": [],
            "conversation_state": {},
            "created_at": now,
            "updated_at": now,
        }

        self.sessions_collection.insert_one(new_session)
        new_session.pop("_id", None)
        return new_session

    def finalize_session(self, session_id: str, itinerary_id: str) -> str:
        """
        Finalize a session by marking it as finalized and creating a new active session.

        Returns the new active session ID.
        """
        # Get the current session
        session = self.get_session(session_id)
        if not session:
            raise ValueError("Session not found")

        clerk_user_id = session.get("clerk_user_id")
        if not clerk_user_id:
            raise ValueError("Session has no clerk_user_id")

        now = datetime.utcnow()

        # Mark current session as finalized
        self.sessions_collection.update_one(
            {"id": session_id},
            {
                "$set": {
                    "status": "finalized",
                    "itinerary_id": itinerary_id,
                    "updated_at": now,
                }
            },
        )

        # Create new active session
        new_session_id = f"sess_{uuid.uuid4().hex[:12]}"
        new_session = {
            "id": new_session_id,
            "clerk_user_id": clerk_user_id,
            "status": "active",
            "itinerary_id": None,
            "messages": [],
            "conversation_state": {},
            "created_at": now,
            "updated_at": now,
        }

        self.sessions_collection.insert_one(new_session)
        return new_session_id

    # Itineraries
    def save_itinerary(
        self,
        doc: ItineraryDocument,
        session_id: str | None = None,
        clerk_user_id: str | None = None,
    ) -> str:
        itn_id = f"itn_{uuid.uuid4().hex[:12]}"
        itinerary_doc = {
            "id": itn_id,
            "document": doc.model_dump(mode="json"),
            "session_id": session_id,
            "clerk_user_id": clerk_user_id,
            "created_at": time.time(),
        }
        self.itineraries_collection.insert_one(itinerary_doc)
        return itn_id

    def get_itinerary(self, itinerary_id: str) -> dict | None:
        itinerary_doc = self.itineraries_collection.find_one({"id": itinerary_id})
        if itinerary_doc:
            itinerary_doc.pop("_id", None)  # Remove MongoDB ObjectId
        return itinerary_doc

    def delete_itinerary(self, itinerary_id: str) -> bool:
        """Delete an itinerary from MongoDB."""
        result = self.itineraries_collection.delete_one({"id": itinerary_id})
        return result.deleted_count > 0

    def get_user_itineraries(self, clerk_user_id: str) -> list[dict]:
        """Get all itineraries for a user by finding their finalized sessions or direct clerk_user_id."""
        # Get user email for group trip participant matching
        user_doc = self.users_collection.find_one({"clerk_user_id": clerk_user_id})
        user_email = user_doc.get("email") if user_doc and user_doc.get("email") else None

        # First, find itineraries directly linked to user (new flow)
        direct_itineraries = list(
            self.itineraries_collection.find({"clerk_user_id": clerk_user_id}).sort(
                "created_at", -1
            )
        )

        # Then find itineraries from finalized sessions (old flow)
        sessions = self.sessions_collection.find(
            {"clerk_user_id": clerk_user_id, "status": "finalized"},
            {"itinerary_id": 1, "created_at": 1},
        ).sort("created_at", -1)

        itineraries = []
        seen_ids = set()

        # Add direct itineraries first
        for itn in direct_itineraries:
            itn.pop("_id", None)
            itineraries.append(itn)
            seen_ids.add(itn["id"])

        # Add session-based itineraries (avoid duplicates)
        for session in sessions:
            if session.get("itinerary_id") and session["itinerary_id"] not in seen_ids:
                itinerary = self.get_itinerary(session["itinerary_id"])
                if itinerary:
                    itineraries.append(itinerary)
                    seen_ids.add(session["itinerary_id"])

        # Also include group trips where user is a participant (by email)
        if user_email:
            # Find all group itineraries where user's email matches a participant
            # Use $elemMatch to explicitly match array elements
            group_itineraries = list(
                self.itineraries_collection.find(
                    {
                        "document.trip_type": "group",
                        "document.group": {"$exists": True, "$ne": None},
                        "document.group.participants": {"$elemMatch": {"email": user_email}},
                    }
                ).sort("created_at", -1)
            )

            # Add group itineraries where user is a participant (avoid duplicates)
            for itn in group_itineraries:
                itn.pop("_id", None)
                if itn["id"] not in seen_ids:
                    # Double-check that user's email is in participants
                    participants = itn.get("document", {}).get("group", {}).get("participants", [])
                    if any(p.get("email") == user_email for p in participants):
                        itineraries.append(itn)
                        seen_ids.add(itn["id"])

        return itineraries

    # Users
    async def create_user(self, user_data: UserCreate) -> User:
        """Create a new user in MongoDB."""
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        hashed_password = get_password_hash(user_data.password)
        now = datetime.utcnow()

        user_doc = {
            "id": user_id,
            "email": user_data.email,
            "username": user_data.username,
            "full_name": user_data.full_name,
            "hashed_password": hashed_password,
            "is_active": True,
            "scopes": ["user"],
            "created_at": now,
            "updated_at": now,
        }

        try:
            self.users_collection.insert_one(user_doc)
        except Exception as e:
            if "duplicate key" in str(e).lower():
                raise ValueError("User with this email already exists")
            raise e

        # Return User model (without hashed_password)
        return User(**{k: v for k, v in user_doc.items() if k != "hashed_password"})

    async def get_user_by_email(self, email: str) -> User | None:
        """Get user by email from MongoDB."""
        user_doc = self.users_collection.find_one({"email": email})
        if user_doc:
            user_doc.pop("_id", None)  # Remove MongoDB ObjectId
            # Return User model (without hashed_password)
            return User(**{k: v for k, v in user_doc.items() if k != "hashed_password"})
        return None

    def get_user_by_email_sync(self, email: str) -> User | None:
        """Synchronous version for optional auth dependency."""
        user_doc = self.users_collection.find_one({"email": email})
        if user_doc:
            user_doc.pop("_id", None)  # Remove MongoDB ObjectId
            return User(**{k: v for k, v in user_doc.items() if k != "hashed_password"})
        return None

    async def get_user_in_db(self, email: str) -> UserInDB | None:
        """Get complete user including hashed password (for authentication)."""
        user_doc = self.users_collection.find_one({"email": email})
        if user_doc:
            user_doc.pop("_id", None)  # Remove MongoDB ObjectId
            return UserInDB(**user_doc)
        return None

    async def authenticate_user(self, email: str, password: str) -> User | None:
        """Authenticate user with email and password."""
        user_in_db = await self.get_user_in_db(email)
        if not user_in_db:
            return None

        if not verify_password(password, user_in_db.hashed_password):
            return None

        # Return User model (without hashed_password)
        return User(
            **{
                k: v
                for k, v in user_in_db.model_dump().items()
                if k != "hashed_password"
            }
        )

    # Clerk Integration Methods
    async def sync_clerk_user(self, clerk_data: ClerkUserSync) -> User:
        """Sync or create user from Clerk data."""
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        # Check if user already exists by clerk_user_id or email
        existing_user = self.users_collection.find_one(
            {
                "$or": [
                    {"clerk_user_id": clerk_data.clerk_user_id},
                    {"email": clerk_data.email},
                ]
            }
        )

        if existing_user:
            # Update existing user with latest Clerk data
            update_data = {
                "clerk_user_id": clerk_data.clerk_user_id,
                "email_verified": clerk_data.email_verified,
                "first_name": clerk_data.first_name,
                "last_name": clerk_data.last_name,
                "full_name": clerk_data.full_name,
                "image_url": clerk_data.image_url,
                "updated_at": now,
            }

            # Update username only if it's provided and not already set
            if clerk_data.username and not existing_user.get("username"):
                update_data["username"] = clerk_data.username

            # Ensure onboarding fields exist for existing users (migration)
            if "onboarding_completed" not in existing_user:
                update_data["onboarding_completed"] = False
            if "onboarding_skipped" not in existing_user:
                update_data["onboarding_skipped"] = False

            self.users_collection.update_one(
                {"_id": existing_user["_id"]}, {"$set": update_data}
            )

            # Return updated user
            updated_user = self.users_collection.find_one({"_id": existing_user["_id"]})
            updated_user.pop("_id", None)
            updated_user.pop("hashed_password", None)  # Remove if present
            return User(**updated_user)

        else:
            # Create new user from Clerk data
            user_doc = {
                "id": user_id,
                "clerk_user_id": clerk_data.clerk_user_id,
                "email": clerk_data.email,
                "email_verified": clerk_data.email_verified,
                "username": clerk_data.username
                or f"user_{user_id[-8:]}",  # Generate username if not provided
                "first_name": clerk_data.first_name,
                "last_name": clerk_data.last_name,
                "full_name": clerk_data.full_name,
                "image_url": clerk_data.image_url,
                "is_active": True,
                "scopes": ["user"],
                "onboarding_completed": False,  # New users haven't completed onboarding
                "onboarding_skipped": False,  # New users haven't skipped onboarding
                "created_at": now,
                "updated_at": now,
            }

            result = self.users_collection.insert_one(user_doc)
            if result.inserted_id:
                user_doc.pop("_id", None)  # Remove MongoDB ObjectId
                return User(**user_doc)
            else:
                raise Exception("Failed to create user from Clerk data")

    async def get_user_by_clerk_id(self, clerk_user_id: str) -> User | None:
        """Get user by Clerk user ID."""
        user_doc = self.users_collection.find_one({"clerk_user_id": clerk_user_id})
        if user_doc:
            user_doc.pop("_id", None)  # Remove MongoDB ObjectId
            user_doc.pop("hashed_password", None)  # Remove if present

            # Ensure onboarding fields exist (migration for existing users)
            if "onboarding_completed" not in user_doc:
                user_doc["onboarding_completed"] = False
            if "onboarding_skipped" not in user_doc:
                user_doc["onboarding_skipped"] = False

            print(user_doc)
            return User(**user_doc)
        return None

    async def update_user_onboarding(
        self,
        clerk_user_id: str,
        onboarding_completed: bool = None,
        onboarding_skipped: bool = None,
    ) -> User | None:
        """Update user onboarding status."""
        update_data = {"updated_at": datetime.utcnow()}

        if onboarding_completed is not None:
            update_data["onboarding_completed"] = onboarding_completed

        if onboarding_skipped is not None:
            update_data["onboarding_skipped"] = onboarding_skipped

        result = self.users_collection.update_one(
            {"clerk_user_id": clerk_user_id}, {"$set": update_data}
        )

        if result.modified_count > 0:
            return await self.get_user_by_clerk_id(clerk_user_id)
        return None

    async def save_user_preferences(
        self, clerk_user_id: str, preferences_data: UserPreferencesCreate
    ) -> UserPreferences:
        """Save or update user travel preferences."""
        now = datetime.utcnow()

        # Create preferences document
        preferences_doc = {
            "clerk_user_id": clerk_user_id,
            "budget_style": preferences_data.budget_style,
            "pace_style": preferences_data.pace_style,
            "schedule_style": preferences_data.schedule_style,
            "selected_interests": preferences_data.selected_interests,
            "other_interests": preferences_data.other_interests,
            "created_at": now,
            "updated_at": now,
        }

        # Upsert (update if exists, insert if not)
        self.preferences_collection.update_one(
            {"clerk_user_id": clerk_user_id}, {"$set": preferences_doc}, upsert=True
        )

        # Return the saved preferences
        saved_doc = self.preferences_collection.find_one(
            {"clerk_user_id": clerk_user_id}
        )
        if saved_doc:
            saved_doc.pop("_id", None)  # Remove MongoDB ObjectId
            return UserPreferences(**saved_doc)
        else:
            raise Exception("Failed to save user preferences")

    async def get_user_preferences(
        self, clerk_user_id: str
    ) -> Optional[UserPreferences]:
        """Get user travel preferences by Clerk user ID."""
        preferences_doc = self.preferences_collection.find_one(
            {"clerk_user_id": clerk_user_id}
        )
        if preferences_doc:
            preferences_doc.pop("_id", None)  # Remove MongoDB ObjectId
            return UserPreferences(**preferences_doc)
        return None

    def get_user_preferences_dict(self, clerk_user_id: str) -> dict | None:
        """Get user travel preferences as dict (sync version for itinerary generation)."""
        preferences_doc = self.preferences_collection.find_one({"clerk_user_id": clerk_user_id})
        if preferences_doc:
            preferences_doc.pop("_id", None)  # Remove MongoDB ObjectId
            return preferences_doc
        return None

    # =========================================================================
    # Trip Invites Methods
    # =========================================================================

    def create_trip_invite(
        self,
        organizer_clerk_id: str,
        organizer_email: str,
        organizer_name: str | None,
        trip_name: str,
        destination: str | None = None,
        date_range_start: str | None = None,
        date_range_end: str | None = None,
        collect_preferences: bool = False,
        trip_type: str = "group",
    ) -> dict:
        """Create a new trip invite."""
        invite_id = str(uuid.uuid4())
        now = datetime.utcnow()

        # Add organizer as first participant
        organizer_first_name = organizer_name.split()[0] if organizer_name else "Organizer"
        organizer_last_name = (
            " ".join(organizer_name.split()[1:])
            if organizer_name and len(organizer_name.split()) > 1
            else ""
        )

        organizer_participant = {
            "email": organizer_email,
            "first_name": organizer_first_name,
            "last_name": organizer_last_name,
            "is_organizer": True,
            "status": "pending",
            "available_dates": [],
            "has_completed_preferences": False,
            "submitted_at": None,
        }

        invite_doc = {
            "id": invite_id,
            "organizer_clerk_id": organizer_clerk_id,
            "organizer_email": organizer_email,
            "organizer_name": organizer_name,
            "trip_name": trip_name,
            "destination": destination,
            "date_range_start": date_range_start,
            "date_range_end": date_range_end,
            "collect_preferences": collect_preferences,
            "trip_type": trip_type,
            "status": "draft",
            "participants": [organizer_participant],  # Organizer as first participant
            "created_at": now,
            "updated_at": now,
        }

        self.trip_invites_collection.insert_one(invite_doc)
        invite_doc.pop("_id", None)
        return invite_doc

    def get_trip_invite(self, invite_id: str) -> dict | None:
        """Get a trip invite by ID."""
        invite_doc = self.trip_invites_collection.find_one({"id": invite_id})
        if invite_doc:
            invite_doc.pop("_id", None)
            return invite_doc
        return None

    def get_user_trip_invites(self, clerk_user_id: str) -> list[dict]:
        """Get all trip invites created by a user."""
        invites = list(self.trip_invites_collection.find({"organizer_clerk_id": clerk_user_id}))
        for invite in invites:
            invite.pop("_id", None)
        return invites

    def get_received_invites(self, email: str) -> list[dict]:
        """Get all trip invites where user is a participant (but not the organizer)."""
        invites = list(
            self.trip_invites_collection.find(
                {
                    "participants.email": email,
                    "participants": {"$elemMatch": {"email": email, "is_organizer": {"$ne": True}}},
                }
            )
        )
        for invite in invites:
            invite.pop("_id", None)
        return invites

    def delete_trip_invite(self, invite_id: str) -> bool:
        """Delete a trip invite."""
        result = self.trip_invites_collection.delete_one({"id": invite_id})
        return result.deleted_count > 0

    def add_participant(
        self,
        invite_id: str,
        email: str,
        first_name: str,
        last_name: str,
    ) -> bool:
        """Add a participant to a trip invite."""
        participant = {
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "is_organizer": False,
            "status": "pending",
            "available_dates": [],
            "has_completed_preferences": False,
            "submitted_at": None,
        }

        result = self.trip_invites_collection.update_one(
            {"id": invite_id},
            {
                "$push": {"participants": participant},
                "$set": {"updated_at": datetime.utcnow()},
            },
        )
        return result.modified_count > 0

    def update_participant(
        self,
        invite_id: str,
        old_email: str,
        new_email: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> bool:
        """Update a participant's information."""
        invite = self.get_trip_invite(invite_id)
        if not invite:
            return False

        participants = invite.get("participants", [])
        for participant in participants:
            if participant["email"] == old_email:
                if new_email:
                    participant["email"] = new_email
                if first_name:
                    participant["first_name"] = first_name
                if last_name:
                    participant["last_name"] = last_name
                break

        result = self.trip_invites_collection.update_one(
            {"id": invite_id},
            {
                "$set": {
                    "participants": participants,
                    "updated_at": datetime.utcnow(),
                }
            },
        )
        return result.modified_count > 0

    def remove_participant(self, invite_id: str, email: str) -> bool:
        """Remove a participant from a trip invite."""
        result = self.trip_invites_collection.update_one(
            {"id": invite_id},
            {
                "$pull": {"participants": {"email": email}},
                "$set": {"updated_at": datetime.utcnow()},
            },
        )
        return result.modified_count > 0

    def mark_invites_sent(self, invite_id: str) -> bool:
        """Mark all participants as invited and update invite status."""
        invite = self.get_trip_invite(invite_id)
        if not invite:
            return False

        participants = invite.get("participants", [])
        for participant in participants:
            if participant["status"] == "pending":
                participant["status"] = "invited"

        result = self.trip_invites_collection.update_one(
            {"id": invite_id},
            {
                "$set": {
                    "status": "sent",
                    "participants": participants,
                    "updated_at": datetime.utcnow(),
                }
            },
        )
        return result.modified_count > 0

    def submit_participant_response(
        self,
        invite_id: str,
        participant_email: str,
        available_dates: list[str],
    ) -> bool:
        """Submit a participant's availability response."""
        invite = self.get_trip_invite(invite_id)
        if not invite:
            return False

        participants = invite.get("participants", [])
        for participant in participants:
            if participant["email"] == participant_email:
                participant["status"] = "responded"
                participant["available_dates"] = available_dates
                participant["submitted_at"] = datetime.utcnow()
                break

        result = self.trip_invites_collection.update_one(
            {"id": invite_id},
            {
                "$set": {
                    "participants": participants,
                    "updated_at": datetime.utcnow(),
                }
            },
        )
        return result.modified_count > 0

    def update_invite_date_analysis(
        self,
        invite_id: str,
        calculated_start_date: str | None,
        calculated_end_date: str | None,
        no_common_dates: bool,
        common_dates_percentage: int | None,
    ) -> bool:
        """Update invite with date analysis results."""
        result = self.trip_invites_collection.update_one(
            {"id": invite_id},
            {
                "$set": {
                    "calculated_start_date": calculated_start_date,
                    "calculated_end_date": calculated_end_date,
                    "no_common_dates": no_common_dates,
                    "common_dates_percentage": common_dates_percentage,
                    "updated_at": datetime.utcnow(),
                }
            },
        )
        return result.modified_count > 0

    def finalize_invite_dates(
        self,
        invite_id: str,
        finalized_start_date: str,
        finalized_end_date: str,
        dates_finalized_by: str,
    ) -> bool:
        """Finalize dates for an invite (set by organizer)."""
        result = self.trip_invites_collection.update_one(
            {"id": invite_id},
            {
                "$set": {
                    "finalized_start_date": finalized_start_date,
                    "finalized_end_date": finalized_end_date,
                    "dates_finalized_by": dates_finalized_by,
                    "updated_at": datetime.utcnow(),
                }
            },
        )
        return result.modified_count > 0

    def update_invite_itinerary_id(
        self,
        invite_id: str,
        itinerary_id: str,
    ) -> bool:
        """Update an invite with the itinerary_id when itinerary is created."""
        result = self.trip_invites_collection.update_one(
            {"id": invite_id},
            {
                "$set": {
                    "itinerary_id": itinerary_id,
                    "updated_at": datetime.utcnow(),
                }
            },
        )
        return result.modified_count > 0

    def reset_participants_for_resend(
        self,
        invite_id: str,
        participant_emails: list[str],
    ) -> bool:
        """Reset specified participants to 'invited' status and clear their availability."""
        invite = self.get_trip_invite(invite_id)
        if not invite:
            return False

        participants = invite.get("participants", [])
        for participant in participants:
            if participant["email"] in participant_emails and not participant.get("is_organizer"):
                participant["status"] = "invited"
                participant["available_dates"] = []
                if "submitted_at" in participant:
                    del participant["submitted_at"]

        result = self.trip_invites_collection.update_one(
            {"id": invite_id},
            {
                "$set": {
                    "participants": participants,
                    "updated_at": datetime.utcnow(),
                }
            },
        )
        return result.modified_count > 0

    def mark_participant_preferences_completed(
        self,
        invite_id: str,
        participant_email: str,
    ) -> bool:
        """Mark that a participant has completed their preferences."""
        invite = self.get_trip_invite(invite_id)
        if not invite:
            return False

        participants = invite.get("participants", [])
        for participant in participants:
            if participant["email"] == participant_email:
                participant["has_completed_preferences"] = True
                if participant["status"] == "responded":
                    participant["status"] = "preferences_completed"
                break

        result = self.trip_invites_collection.update_one(
            {"id": invite_id},
            {
                "$set": {
                    "participants": participants,
                    "updated_at": datetime.utcnow(),
                }
            },
        )
        return result.modified_count > 0


# Create a single instance to be used throughout the app
repo = MongoDBRepo()
