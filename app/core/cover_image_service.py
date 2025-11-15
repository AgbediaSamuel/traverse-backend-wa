"""
Cover image service using Unsplash API with caching.
"""

import os
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")
UNSPLASH_API_BASE = "https://api.unsplash.com"


class CoverImageService:
    """Service for fetching cover images from Unsplash with caching."""

    def __init__(self):
        if not UNSPLASH_ACCESS_KEY:
            print(
                "[CoverImage] WARNING: UNSPLASH_ACCESS_KEY not found. "
                "Cover images will not be available."
            )
        self.access_key = UNSPLASH_ACCESS_KEY

    def extract_city_country(self, destination: str) -> tuple[str, str]:
        """Extract city and country from destination string."""
        if not destination:
            return "", ""
        parts = destination.split(",")
        city = parts[0].strip() if parts else ""
        country = parts[-1].strip() if len(parts) > 1 else ""
        return city, country

    def get_cover_image(self, destination: str, repository: Any) -> str | None:
        """
        Get cover image URL for a destination.

        Flow:
        1. Check database cache
        2. If not found, call Unsplash API
        3. Store in database
        4. Return image URL

        Args:
            destination: City/destination name (e.g., "Lagos, Nigeria")
            repository: MongoDB repository instance

        Returns:
            Cover image URL or None if not found
        """
        if not destination:
            return None

        if not self.access_key:
            print("[CoverImage] No API key available")
            return None

        # Step 1: Check database cache
        try:
            cached = repository.get_cover_image(destination)
            if cached and cached.get("image_url"):
                print(f"[CoverImage] Using cached image for '{destination}'")
                return cached["image_url"]
        except Exception as e:
            print(f"[CoverImage] Cache lookup failed: {e}, proceeding to API")

        # Step 2: Call Unsplash API
        city, country = self.extract_city_country(destination)
        query = f"{destination} aerial view"

        print(f"[CoverImage] Fetching from Unsplash for '{destination}'")

        try:
            search_url = f"{UNSPLASH_API_BASE}/search/photos"
            params = {
                "query": query,
                "client_id": self.access_key,
                "per_page": 1,  # Just get first result
                "orientation": "landscape",  # Prefer landscape for covers
            }

            response = requests.get(search_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if not data.get("results") or len(data["results"]) == 0:
                print(f"[CoverImage] No results from Unsplash for '{destination}'")
                return None

            # Get first result
            photo = data["results"][0]

            # Add query_used to photo data for storage
            photo["query_used"] = query

            # Step 3: Store in database (non-blocking if it fails)
            try:
                repository.save_cover_image(destination, city, country, photo)
            except Exception as e:
                print(f"[CoverImage] Failed to cache image: {e}, continuing anyway")

            # Step 4: Return image URL
            image_url = photo.get("urls", {}).get("regular")
            if image_url:
                print(f"[CoverImage] Successfully fetched for '{destination}'")
                return image_url
            else:
                print(f"[CoverImage] No image URL in Unsplash response")
                return None

        except Exception as e:
            print(f"[CoverImage] Error fetching from Unsplash: {e}")
            return None


# Singleton instance (will warn if API key missing but won't crash)
try:
    cover_image_service = CoverImageService()
except Exception as e:
    print(f"[CoverImage] Failed to initialize service: {e}")
    # Create a dummy service that returns None
    cover_image_service = None
