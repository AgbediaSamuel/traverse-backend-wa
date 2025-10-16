"""
Foursquare Places API service for venue discovery and details.
"""

import os
from typing import Any, Dict, List, Optional

import requests

FOURSQUARE_API_BASE = "https://places-api.foursquare.com/places"


class FoursquareService:
    """Service for interacting with Foursquare Places API (2025 version)."""

    def __init__(self):
        self.api_key = os.getenv("FOURSQUARE_API_KEY")
        if not self.api_key:
            raise ValueError("FOURSQUARE_API_KEY environment variable not set")

        self.headers = {
            "Accept": "application/json",
            "X-Places-Api-Version": "2025-06-17",
            "Authorization": f"Bearer {self.api_key}",
        }

    def search_places(
        self,
        lat: float,
        lng: float,
        query: Optional[str] = None,
        categories: Optional[List[str]] = None,
        radius: int = 5000,
        limit: int = 50,
        min_rating: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for places near a location.

        Args:
            lat: Latitude
            lng: Longitude
            query: Search query (optional)
            categories: List of Foursquare category IDs (optional)
            radius: Search radius in meters (default 5000m = 5km)
            limit: Maximum number of results
            min_rating: Minimum rating filter (0-10 scale)

        Returns:
            List of place dictionaries with standardized fields
        """
        url = f"{FOURSQUARE_API_BASE}/search"

        params = {
            "ll": f"{lat},{lng}",
            "radius": radius,
            "limit": limit,
            "fields": "fsq_id,name,location,categories,rating,price,distance,photos",
        }

        if query:
            params["query"] = query

        if categories:
            params["categories"] = ",".join(categories)

        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            results = data.get("results", [])
            places = []

            for result in results:
                # Extract rating (Foursquare uses 0-10 scale)
                rating = result.get("rating")

                # Apply rating filter if specified
                if min_rating and (not rating or rating < min_rating):
                    continue

                # Extract photo if available
                photos = result.get("photos", [])
                photo_url = None
                if photos:
                    photo = photos[0]
                    prefix = photo.get("prefix")
                    suffix = photo.get("suffix")
                    if prefix and suffix:
                        photo_url = f"{prefix}1080x720{suffix}"

                place = {
                    "fsq_id": result.get("fsq_id"),
                    "name": result.get("name"),
                    "categories": [cat.get("name") for cat in result.get("categories", [])],
                    "location": result.get("location", {}),
                    "rating": rating,
                    "price": result.get("price"),  # 1-4 scale
                    "distance": result.get("distance"),
                    "photo_url": photo_url,
                    "address": result.get("location", {}).get("formatted_address"),
                }
                places.append(place)

            return places

        except Exception as e:
            print(f"Error searching Foursquare places: {e}")
            return []

    def get_place_details(self, fsq_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a specific place.

        Args:
            fsq_id: Foursquare place ID

        Returns:
            Dictionary with detailed place information
        """
        url = f"{FOURSQUARE_API_BASE}/{fsq_id}"

        params = {
            "fields": "fsq_id,name,location,categories,rating,price,hours,website,tel,email,description,photos"
        }

        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            location = data.get("location", {})

            return {
                "fsq_id": data.get("fsq_id"),
                "name": data.get("name"),
                "address": location.get("formatted_address"),
                "rating": data.get("rating"),
                "price": data.get("price"),
                "categories": [cat.get("name") for cat in data.get("categories", [])],
                "hours": data.get("hours", {}).get("display"),
                "website": data.get("website"),
                "phone": data.get("tel"),
                "description": data.get("description"),
                "photos": data.get("photos", []),
            }

        except Exception as e:
            print(f"Error getting Foursquare place details for {fsq_id}: {e}")
            return None

    def get_place_photo_url(
        self, fsq_id: str, width: int = 1080, height: int = 720
    ) -> Optional[str]:
        """
        Get a photo URL for a place.

        Args:
            fsq_id: Foursquare place ID
            width: Desired photo width
            height: Desired photo height

        Returns:
            Photo URL or None
        """
        details = self.get_place_details(fsq_id)
        if not details or not details.get("photos"):
            return None

        photos = details["photos"]
        if not photos:
            return None

        # Get first photo
        photo = photos[0]
        prefix = photo.get("prefix")
        suffix = photo.get("suffix")

        if prefix and suffix:
            return f"{prefix}{width}x{height}{suffix}"

        return None

    def search_by_preferences(
        self,
        lat: float,
        lng: float,
        user_interests: List[str],
        budget_style: int,
        max_results: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Search for places based on user preferences.

        Args:
            lat: Latitude
            lng: Longitude
            user_interests: List of user interest strings
            budget_style: Budget preference (0-100 scale)
            max_results: Maximum number of results

        Returns:
            List of places matching user preferences
        """
        # Map user interests to Foursquare category IDs
        interest_to_categories = {
            "Museums": ["10027"],  # Museum
            "Art Galleries": ["10028"],  # Art Gallery
            "Fine dining": ["13065"],  # Restaurant (fine dining)
            "Street food": ["13145"],  # Food Stand
            "Coffee & café hopping": ["13035"],  # Café
            "Local Festivals": ["10032"],  # Event Space
            "Architecture & Landmarks": ["16000"],  # Landmark
            "Historical Tours": ["10027"],  # Museum/Historical
            "Live Music / Concerts": ["10032"],  # Music Venue
            "Bar Crawls": ["13003"],  # Bar
            "Clubs": ["10032"],  # Nightclub
            "Beach & Water Activities": ["16001"],  # Beach
            "Hiking": ["16019"],  # Trail
            "Mountains & Scenic Views": ["16000"],  # Scenic Lookout
            "Spas": ["10077"],  # Spa
            "Shopping": ["17000"],  # Shop
            "Luxury Boutiques": ["17043"],  # Clothing Store
            "Vintage & Thrift": ["17143"],  # Thrift Store
            "Instagrammable Spots": ["16000"],  # Landmark
        }

        all_places = []
        seen_fsq_ids = set()

        # Build category list from user interests
        all_categories = []
        for interest in user_interests:
            cats = interest_to_categories.get(interest, [])
            all_categories.extend(cats)

        # Always include general categories for variety
        all_categories.extend(
            [
                "16000",  # Landmark
                "13065",  # Restaurant
                "10032",  # Nightlife/Entertainment
                "17000",  # Shopping
            ]
        )

        # Remove duplicates
        all_categories = list(set(all_categories))

        # Search with all categories
        places = self.search_places(
            lat=lat,
            lng=lng,
            categories=all_categories,
            radius=5000,
            limit=max_results,
            min_rating=7.0,  # Foursquare uses 0-10 scale
        )

        # Add unique places
        for place in places:
            if place["fsq_id"] not in seen_fsq_ids:
                seen_fsq_ids.add(place["fsq_id"])
                all_places.append(place)

                if len(all_places) >= max_results:
                    break

        # If we don't have enough, do a broader search without category filter
        if len(all_places) < 20:
            print(f"Only found {len(all_places)} places, doing broader search...")
            broader_places = self.search_places(
                lat=lat, lng=lng, radius=5000, limit=max_results, min_rating=6.5
            )

            for place in broader_places:
                if place["fsq_id"] not in seen_fsq_ids:
                    seen_fsq_ids.add(place["fsq_id"])
                    all_places.append(place)

                    if len(all_places) >= max_results:
                        break

        return all_places[:max_results]


# Singleton instance
foursquare_service = FoursquareService()
