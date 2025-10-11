from __future__ import annotations

import os
import time
import uuid
from datetime import datetime
from typing import Dict, Optional

from pymongo import MongoClient
from dotenv import load_dotenv

from app.core.schemas import ItineraryDocument, User, UserCreate, UserInDB, ClerkUserSync, OnboardingUpdate, UserPreferences, UserPreferencesCreate
from app.core.auth import get_password_hash, verify_password

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
        self.preferences_collection = self.db.user_preferences
        
        # Test connection and create indexes only if connection works
        try:
            # Test the connection
            self.client.admin.command('ping')
            print("✅ MongoDB connection successful!")
            
            # Create indexes for better performance (only if connection works)
            try:
                self.users_collection.create_index("email", unique=True)
                print("✅ Database indexes created")
            except Exception as index_error:
                print(f"⚠️ Index creation failed (might already exist): {index_error}")
                
        except Exception as e:
            print(f"❌ MongoDB connection failed: {e}")
            print("⚠️ Will continue without database connection (for development)")

    # Sessions
    def create_session(self, session: dict) -> None:
        session_doc = {**session, "created_at": time.time()}
        self.sessions_collection.insert_one(session_doc)

    def get_session(self, session_id: str) -> Optional[dict]:
        session_doc = self.sessions_collection.find_one({"id": session_id})
        if session_doc:
            session_doc.pop("_id", None)  # Remove MongoDB ObjectId
        return session_doc

    def update_session(self, session_id: str, data: dict) -> None:
        self.sessions_collection.update_one(
            {"id": session_id},
            {"$set": data}
        )

    # Itineraries
    def save_itinerary(self, doc: ItineraryDocument, session_id: str | None = None) -> str:
        itn_id = f"itn_{uuid.uuid4().hex[:12]}"
        itinerary_doc = {
            "id": itn_id,
            "document": doc.model_dump(mode="json"),
            "session_id": session_id,
            "created_at": time.time(),
        }
        self.itineraries_collection.insert_one(itinerary_doc)
        return itn_id

    def get_itinerary(self, itinerary_id: str) -> Optional[dict]:
        itinerary_doc = self.itineraries_collection.find_one({"id": itinerary_id})
        if itinerary_doc:
            itinerary_doc.pop("_id", None)  # Remove MongoDB ObjectId
        return itinerary_doc

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
    
    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email from MongoDB."""
        user_doc = self.users_collection.find_one({"email": email})
        if user_doc:
            user_doc.pop("_id", None)  # Remove MongoDB ObjectId
            # Return User model (without hashed_password)
            return User(**{k: v for k, v in user_doc.items() if k != "hashed_password"})
        return None
    
    def get_user_by_email_sync(self, email: str) -> Optional[User]:
        """Synchronous version for optional auth dependency."""
        user_doc = self.users_collection.find_one({"email": email})
        if user_doc:
            user_doc.pop("_id", None)  # Remove MongoDB ObjectId
            return User(**{k: v for k, v in user_doc.items() if k != "hashed_password"})
        return None
    
    async def get_user_in_db(self, email: str) -> Optional[UserInDB]:
        """Get complete user including hashed password (for authentication)."""
        user_doc = self.users_collection.find_one({"email": email})
        if user_doc:
            user_doc.pop("_id", None)  # Remove MongoDB ObjectId
            return UserInDB(**user_doc)
        return None

    async def authenticate_user(self, email: str, password: str) -> Optional[User]:
        """Authenticate user with email and password."""
        user_in_db = await self.get_user_in_db(email)
        if not user_in_db:
            return None
        
        if not verify_password(password, user_in_db.hashed_password):
            return None
        
        # Return User model (without hashed_password)
        return User(**{k: v for k, v in user_in_db.model_dump().items() if k != "hashed_password"})

    # Clerk Integration Methods
    async def sync_clerk_user(self, clerk_data: ClerkUserSync) -> User:
        """Sync or create user from Clerk data."""
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()
        
        # Check if user already exists by clerk_user_id or email
        existing_user = self.users_collection.find_one({
            "$or": [
                {"clerk_user_id": clerk_data.clerk_user_id},
                {"email": clerk_data.email}
            ]
        })
        
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
                {"_id": existing_user["_id"]},
                {"$set": update_data}
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
                "username": clerk_data.username or f"user_{user_id[-8:]}",  # Generate username if not provided
                "first_name": clerk_data.first_name,
                "last_name": clerk_data.last_name,
                "full_name": clerk_data.full_name,
                "image_url": clerk_data.image_url,
                "is_active": True,
                "scopes": ["user"],
                "onboarding_completed": False,  # New users haven't completed onboarding
                "onboarding_skipped": False,    # New users haven't skipped onboarding
                "created_at": now,
                "updated_at": now,
            }
            
            result = self.users_collection.insert_one(user_doc)
            if result.inserted_id:
                user_doc.pop("_id", None)  # Remove MongoDB ObjectId
                return User(**user_doc)
            else:
                raise Exception("Failed to create user from Clerk data")

    async def get_user_by_clerk_id(self, clerk_user_id: str) -> Optional[User]:
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

    async def update_user_onboarding(self, clerk_user_id: str, onboarding_completed: bool = None, onboarding_skipped: bool = None) -> Optional[User]:
        """Update user onboarding status."""
        update_data = {"updated_at": datetime.utcnow()}
        
        if onboarding_completed is not None:
            update_data["onboarding_completed"] = onboarding_completed
        
        if onboarding_skipped is not None:
            update_data["onboarding_skipped"] = onboarding_skipped
        
        result = self.users_collection.update_one(
            {"clerk_user_id": clerk_user_id},
            {"$set": update_data}
        )
        
        if result.modified_count > 0:
            return await self.get_user_by_clerk_id(clerk_user_id)
        return None

    async def save_user_preferences(self, clerk_user_id: str, preferences_data: UserPreferencesCreate) -> UserPreferences:
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
        result = self.preferences_collection.update_one(
            {"clerk_user_id": clerk_user_id},
            {"$set": preferences_doc},
            upsert=True
        )
        
        # Return the saved preferences
        saved_doc = self.preferences_collection.find_one({"clerk_user_id": clerk_user_id})
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


# Create a single instance to be used throughout the app
repo = MongoDBRepo()
