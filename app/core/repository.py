from __future__ import annotations

import os
import time
import uuid
from datetime import datetime
from typing import Any, Optional

from dotenv import load_dotenv
from pymongo import MongoClient

from app.core.schemas import (
    ClerkUserSync,
    ItineraryDocument,
    User,
    UserPreferences,
    UserPreferencesCreate,
)

# Load environment variables
load_dotenv()


class MongoDBRepo:
    def __init__(self):
        # Load environment variables
        load_dotenv()

        # Determine which MongoDB URI to use based on environment
        environment = os.getenv("ENVIRONMENT", "production").lower()

        if environment == "development":
            # In development, prefer MONGODB_URI_TEST, fallback to MONGODB_URI
            mongodb_uri = os.getenv("MONGODB_URI_TEST") or os.getenv("MONGODB_URI")
            database_name = os.getenv("DATABASE_NAME_TEST", "traverse_db_test")
            if not mongodb_uri:
                raise ValueError(
                    "MONGODB_URI_TEST or MONGODB_URI environment variable is required for development"
                )
            print(f"🔧 Using TEST database: {database_name} (ENVIRONMENT={environment})")
        else:
            mongodb_uri = os.getenv("MONGODB_URI")
            database_name = os.getenv("DATABASE_NAME", "traverse_db")
            if not mongodb_uri:
                raise ValueError("MONGODB_URI environment variable is required")
            print(f"🚀 Using PRODUCTION database: {database_name} (ENVIRONMENT={environment})")

        # Initialize MongoDB client with robust connection settings
        # Add connection options to handle replica sets and SSL issues
        self.client = MongoClient(
            mongodb_uri,
            serverSelectionTimeoutMS=5000,  # 5 second timeout
            connectTimeoutMS=10000,  # 10 second connection timeout
            socketTimeoutMS=20000,  # 20 second socket timeout
            retryWrites=True,
            retryReads=True,
            # Handle replica set issues more gracefully
            directConnection=False,  # Allow replica set connections
            # SSL/TLS options - relaxed for development (remove in production)
            tlsAllowInvalidCertificates=True,  # Allow invalid certs for dev
            tlsAllowInvalidHostnames=True,  # Allow invalid hostnames for dev
        )

        self.db = self.client[database_name]

        # Collections
        self.itineraries_collection = self.db.itineraries
        self.users_collection = self.db.users
        self.preferences_collection = self.db.user_preferences
        self.trip_invites_collection = self.db.trip_invites
        self.cover_images_collection = self.db.cover_images
        self.destination_profiles_collection = self.db.destination_profiles

        # Test connection and create indexes only if connection works
        try:
            # Test the connection with a shorter timeout
            self.client.admin.command("ping", serverSelectionTimeoutMS=3000)
            print("MongoDB connection successful")

            # Create indexes for better performance (only if connection works)
            try:
                self.users_collection.create_index("email", unique=True)
                self.cover_images_collection.create_index("destination", unique=True)
                self.destination_profiles_collection.create_index("destination", unique=True)
                self.itineraries_collection.create_index("fingerprint")
                print("Database indexes created")
            except Exception as index_error:
                print(f"Index creation failed (might already exist): {index_error}")

        except Exception as e:
            # Suppress verbose error messages for development
            error_msg = str(e)
            if "No replica set members match selector" in error_msg:
                print(
                    "MongoDB connection warning: "
                    "Replica set connection issue (continuing without DB)"
                )
            elif "SSL handshake failed" in error_msg:
                print("MongoDB connection warning: " "SSL handshake issue (continuing without DB)")
            else:
                print(f"MongoDB connection failed: {error_msg[:200]}...")
            print("Will continue without database connection (for development)")

    # Itineraries
    def find_itinerary_by_fingerprint(self, fingerprint: str) -> dict | None:
        """Find an existing itinerary by its fingerprint hash."""
        itinerary_doc = self.itineraries_collection.find_one({"fingerprint": fingerprint})
        if itinerary_doc:
            itinerary_doc.pop("_id", None)  # Remove MongoDB ObjectId
        return itinerary_doc

    def save_itinerary(
        self,
        doc: ItineraryDocument,
        clerk_user_id: str | None = None,
        fingerprint: str | None = None,
    ) -> str:
        itn_id = f"itn_{uuid.uuid4().hex[:12]}"
        itinerary_doc = {
            "id": itn_id,
            "document": doc.model_dump(mode="json"),
            "clerk_user_id": clerk_user_id,
            "created_at": time.time(),
        }
        if fingerprint:
            itinerary_doc["fingerprint"] = fingerprint
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
        """Get all itineraries for a user by clerk_user_id."""
        # Get user email for group trip participant matching
        user_doc = self.users_collection.find_one({"clerk_user_id": clerk_user_id})
        user_email = user_doc.get("email") if user_doc and user_doc.get("email") else None

        # Find itineraries directly linked to user
        direct_itineraries = list(
            self.itineraries_collection.find({"clerk_user_id": clerk_user_id}).sort(
                "created_at", -1
            )
        )

        itineraries = []
        seen_ids = set()

        # Add direct itineraries first
        for itn in direct_itineraries:
            itn.pop("_id", None)
            itineraries.append(itn)
            seen_ids.add(itn["id"])

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

            # Also include itineraries from invites where user is a participant
            # This handles cases where emails weren't stored in the itinerary document
            invites_with_itineraries = list(
                self.trip_invites_collection.find(
                    {
                        "participants.email": user_email,
                        "itinerary_id": {"$exists": True, "$ne": None},
                    }
                )
            )

            # Fetch itineraries linked to these invites
            for invite in invites_with_itineraries:
                itinerary_id = invite.get("itinerary_id")
                if itinerary_id and itinerary_id not in seen_ids:
                    itinerary = self.itineraries_collection.find_one({"id": itinerary_id})
                    if itinerary:
                        itinerary.pop("_id", None)
                        itineraries.append(itinerary)
                        seen_ids.add(itinerary_id)

        return itineraries

    # Users
    async def get_user_by_email(self, email: str) -> User | None:
        """Get user by email from MongoDB."""
        import asyncio

        def _find_user():
            return self.users_collection.find_one({"email": email})

        user_doc = await asyncio.to_thread(_find_user)
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

    # Clerk Integration Methods
    async def sync_clerk_user(self, clerk_data: ClerkUserSync) -> User:
        """Sync or create user from Clerk data."""
        import asyncio

        user_id = f"user_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        # Wrap blocking MongoDB operations in executor to avoid blocking event loop
        def _find_user():
            return self.users_collection.find_one(
                {
                    "$or": [
                        {"clerk_user_id": clerk_data.clerk_user_id},
                        {"email": clerk_data.email},
                    ]
                }
            )

        existing_user = await asyncio.to_thread(_find_user)

        sanitized_first = clerk_data.first_name.strip() if clerk_data.first_name else None
        sanitized_last = clerk_data.last_name.strip() if clerk_data.last_name else None
        sanitized_full = (
            clerk_data.full_name.strip()
            if clerk_data.full_name and clerk_data.full_name.strip()
            else " ".join(part for part in [sanitized_first, sanitized_last] if part) or None
        )
        sanitized_image = clerk_data.image_url.strip() if clerk_data.image_url else None

        if existing_user:
            updates: dict[str, Any] = {}

            if clerk_data.email_verified and not existing_user.get("email_verified"):
                updates["email_verified"] = True

            if sanitized_first and not existing_user.get("first_name"):
                updates["first_name"] = sanitized_first

            if sanitized_last and not existing_user.get("last_name"):
                updates["last_name"] = sanitized_last

            if sanitized_full and not existing_user.get("full_name"):
                updates["full_name"] = sanitized_full

            if sanitized_image and not existing_user.get("image_url"):
                updates["image_url"] = sanitized_image

            if updates:
                updates["updated_at"] = now

                def _update_user():
                    self.users_collection.update_one(
                        {"_id": existing_user["_id"]}, {"$set": updates}
                    )

                await asyncio.to_thread(_update_user)
                existing_user.update(updates)

            existing_user.pop("_id", None)
            existing_user.pop("hashed_password", None)
            if "onboarding_completed" not in existing_user:
                existing_user["onboarding_completed"] = False
            if "onboarding_skipped" not in existing_user:
                existing_user["onboarding_skipped"] = False
            return User(**existing_user)

        else:
            # Create new user from Clerk data
            user_doc = {
                "id": user_id,
                "clerk_user_id": clerk_data.clerk_user_id,
                "email": clerk_data.email,
                "email_verified": clerk_data.email_verified,
                "username": clerk_data.username
                or f"user_{user_id[-8:]}",  # Generate username if not provided
                "first_name": sanitized_first,
                "last_name": sanitized_last,
                "full_name": sanitized_full,
                "image_url": sanitized_image,
                "is_active": True,
                "scopes": ["user"],
                "onboarding_completed": False,  # New users haven't completed onboarding
                "onboarding_skipped": False,  # New users haven't skipped onboarding
                "first_itinerary_email_sent": False,  # New users haven't received first email
                "created_at": now,
                "updated_at": now,
            }

            def _insert_user():
                return self.users_collection.insert_one(user_doc)

            result = await asyncio.to_thread(_insert_user)
            if result.inserted_id:
                user_doc.pop("_id", None)  # Remove MongoDB ObjectId
                return User(**user_doc)
            else:
                raise Exception("Failed to create user from Clerk data")

    async def get_user_by_clerk_id(self, clerk_user_id: str) -> User | None:
        """Get user by Clerk user ID."""
        import asyncio

        def _find_user():
            return self.users_collection.find_one({"clerk_user_id": clerk_user_id})

        user_doc = await asyncio.to_thread(_find_user)
        if user_doc:
            user_doc.pop("_id", None)  # Remove MongoDB ObjectId
            user_doc.pop("hashed_password", None)  # Remove if present

            # Ensure onboarding fields exist (migration for existing users)
            if "onboarding_completed" not in user_doc:
                user_doc["onboarding_completed"] = False
            if "onboarding_skipped" not in user_doc:
                user_doc["onboarding_skipped"] = False
            if "first_itinerary_email_sent" not in user_doc:
                user_doc["first_itinerary_email_sent"] = False

            return User(**user_doc)
        return None

    async def update_user_onboarding(
        self,
        clerk_user_id: str,
        onboarding_completed: bool = None,
        onboarding_skipped: bool = None,
    ) -> User | None:
        """Update user onboarding status."""
        import asyncio

        update_data = {"updated_at": datetime.utcnow()}

        if onboarding_completed is not None:
            update_data["onboarding_completed"] = onboarding_completed

        if onboarding_skipped is not None:
            update_data["onboarding_skipped"] = onboarding_skipped

        def _update_user():
            return self.users_collection.update_one(
                {"clerk_user_id": clerk_user_id}, {"$set": update_data}
            )

        result = await asyncio.to_thread(_update_user)

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
        import asyncio

        def _upsert_preferences():
            self.preferences_collection.update_one(
                {"clerk_user_id": clerk_user_id}, {"$set": preferences_doc}, upsert=True
            )

        await asyncio.to_thread(_upsert_preferences)

        # Return the saved preferences
        def _find_preferences():
            return self.preferences_collection.find_one({"clerk_user_id": clerk_user_id})

        saved_doc = await asyncio.to_thread(_find_preferences)
        if saved_doc:
            saved_doc.pop("_id", None)  # Remove MongoDB ObjectId
            return UserPreferences(**saved_doc)
        else:
            raise Exception("Failed to save user preferences")

    async def get_user_preferences(self, clerk_user_id: str) -> Optional[UserPreferences]:
        """Get user travel preferences by Clerk user ID."""
        preferences_doc = self.preferences_collection.find_one({"clerk_user_id": clerk_user_id})
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
        cover_image: str | None = None,
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
            "cover_image": cover_image,
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

    # Cover Images
    def get_cover_image(self, destination: str) -> dict | None:
        """Get cached cover image for a destination."""
        cover_doc = self.cover_images_collection.find_one({"destination": destination})
        if cover_doc:
            cover_doc.pop("_id", None)  # Remove MongoDB ObjectId
        return cover_doc

    def save_cover_image(
        self,
        destination: str,
        city: str,
        country: str,
        image_data: dict[str, Any],
    ) -> bool:
        """Save cover image data to cache."""
        cover_doc = {
            "destination": destination,
            "city": city,
            "country": country,
            "unsplash_image_id": image_data.get("id"),
            "image_url": image_data.get("urls", {}).get("regular"),
            "image_url_small": image_data.get("urls", {}).get("small"),
            "image_url_thumb": image_data.get("urls", {}).get("thumb"),
            "photographer_name": image_data.get("user", {}).get("name"),
            "photographer_username": image_data.get("user", {}).get("username"),
            "unsplash_url": image_data.get("links", {}).get("html"),
            "query_used": image_data.get("query_used", ""),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }

        # Upsert: update if exists, insert if not
        result = self.cover_images_collection.update_one(
            {"destination": destination},
            {"$set": cover_doc},
            upsert=True,
        )
        return result.upserted_id is not None or result.modified_count > 0

    # Destination Profiles
    def get_destination_profile(self, destination: str) -> dict | None:
        """Get cached destination profile (available categories) for a city."""
        profile_doc = self.destination_profiles_collection.find_one({"destination": destination})
        if profile_doc:
            profile_doc.pop("_id", None)  # Remove MongoDB ObjectId
            # Convert list back to set
            if "categories" in profile_doc and isinstance(profile_doc["categories"], list):
                profile_doc["categories"] = set(profile_doc["categories"])
        return profile_doc

    def save_destination_profile(self, destination: str, categories: set[str]) -> bool:
        """Save destination profile (available categories) to cache."""
        profile_doc = {
            "destination": destination,
            "categories": list(categories),  # Convert set to list for MongoDB
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }

        # Upsert: update if exists, insert if not
        result = self.destination_profiles_collection.update_one(
            {"destination": destination},
            {"$set": profile_doc},
            upsert=True,
        )
        return result.upserted_id is not None or result.modified_count > 0


# Create a single instance to be used throughout the app
repo = MongoDBRepo()
