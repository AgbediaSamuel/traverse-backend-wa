"""
Destination profiling service for caching available venue categories per city.
"""

import os
from datetime import datetime, timedelta
from typing import Any

from app.core.places_service import PlacesService
from app.core.repository import repo

# Cache TTL: 30 days
CACHE_TTL_DAYS = 30


class DestinationProfilingService:
    """Service for managing destination profiles (available venue categories per city)."""

    def __init__(self):
        self.places_service = PlacesService()

    def get_destination_profile(self, destination: str) -> set[str]:
        """
        Get the destination profile (available categories) for a city.

        Checks MongoDB cache first, then fetches from Google Places API if not cached.

        Args:
            destination: City name (e.g., "Paris, France")

        Returns:
            Set of Google Place type strings that exist in this destination
        """
        # Check cache first
        cached_profile = repo.get_destination_profile(destination)
        if cached_profile:
            return cached_profile.get("categories", set())

        # Not cached - fetch from Google Places API
        # For now, return a default set of common categories
        # In future, we can implement actual discovery by searching broadly
        default_categories = {
            "museum",
            "art_gallery",
            "tourist_attraction",
            "park",
            "cafe",
            "restaurant",
            "bar",
            "shopping_mall",
            "point_of_interest",
            "church",
            "library",
            "movie_theater",
            "bakery",
            "lodging",
            "university",
            "aquarium",
            "zoo",
            "beach",
            "spa",
            "gym",
            "night_club",
            "stadium",
            "amusement_park",
            "hindu_temple",
            "mosque",
            "synagogue",
            "theater",
            "casino",
        }

        # Cache the default profile
        repo.save_destination_profile(destination, default_categories)

        return default_categories

    def refresh_destination_profile(self, destination: str) -> set[str]:
        """
        Force refresh the destination profile by fetching from Google Places API.

        Args:
            destination: City name (e.g., "Paris, France")

        Returns:
            Set of Google Place type strings that exist in this destination
        """
        # For now, use default categories
        # In future, implement actual discovery
        default_categories = {
            "museum",
            "art_gallery",
            "tourist_attraction",
            "park",
            "cafe",
            "restaurant",
            "bar",
            "shopping_mall",
            "point_of_interest",
            "church",
            "library",
            "movie_theater",
            "bakery",
            "lodging",
            "university",
            "aquarium",
            "zoo",
            "beach",
            "spa",
            "gym",
            "night_club",
            "stadium",
            "amusement_park",
            "hindu_temple",
            "mosque",
            "synagogue",
            "theater",
            "casino",
        }

        repo.save_destination_profile(destination, default_categories)

        return default_categories


# Singleton instance
destination_profiling_service = DestinationProfilingService()
