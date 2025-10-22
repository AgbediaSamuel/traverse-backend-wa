"""
Google Places API integration for fetching venue data and photos.
"""

import os
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests
from dotenv import load_dotenv

load_dotenv()

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
PLACES_API_BASE = "https://maps.googleapis.com/maps/api/place"


class PlacesService:
    """Service for interacting with Google Places API."""

    def __init__(self):
        if not GOOGLE_MAPS_API_KEY:
            raise ValueError("GOOGLE_MAPS_API_KEY not found in environment variables")
        self.api_key = GOOGLE_MAPS_API_KEY

    def geocode_location(self, location: str) -> Optional[Dict[str, float]]:
        """
        Geocode a location string to latitude/longitude coordinates.

        Args:
            location: City/destination name (e.g., "Paris, France")

        Returns:
            Dictionary with 'lat' and 'lng' keys, or None if geocoding fails
        """
        geocode_url = "https://maps.googleapis.com/maps/api/geocode/json"
        geocode_params = {"address": location, "key": self.api_key}

        try:
            geocode_response = requests.get(geocode_url, params=geocode_params, timeout=10)
            geocode_response.raise_for_status()
            geocode_data = geocode_response.json()

            if geocode_data.get("status") != "OK" or not geocode_data.get("results"):
                status = geocode_data.get("status")
                print(f"Geocoding failed for {location}: {status}")
                return None

            lat = geocode_data["results"][0]["geometry"]["location"]["lat"]
            lng = geocode_data["results"][0]["geometry"]["location"]["lng"]

            return {"lat": lat, "lng": lng}

        except Exception as e:
            print(f"Error geocoding location: {e}")
            return None

    def search_places(
        self,
        location: str,
        query: str,
        radius: int = 5000,
        min_rating: Optional[float] = None,
        price_level: Optional[List[int]] = None,
        require_photo: bool = False,
        allowed_types: Optional[List[str]] = None,
        max_pages: int = 1,
    ) -> List[Dict[str, Any]]:
        """
        Search for places using Text Search API.

        Args:
            location: City/destination name (e.g., "Paris, France")
            query: Search query (e.g., "museums", "fine dining restaurants")
            radius: Search radius in meters (default 5000m = 5km)
            min_rating: Minimum rating filter (default 3.5)
            price_level: List of acceptable price levels [1-4] (optional)

        Returns:
            List of place dictionaries with basic info
        """
        # First, geocode the location to get coordinates
        geocode_url = "https://maps.googleapis.com/maps/api/geocode/json"
        geocode_params = {"address": location, "key": self.api_key}

        try:
            geocode_response = requests.get(
                geocode_url,
                params=geocode_params,
                timeout=10,
            )
            geocode_response.raise_for_status()
            geocode_data = geocode_response.json()

            if geocode_data.get("status") != "OK" or not geocode_data.get("results"):
                status = geocode_data.get("status")
                print(f"Geocoding failed for {location}: {status}")
                return []

            lat = geocode_data["results"][0]["geometry"]["location"]["lat"]
            lng = geocode_data["results"][0]["geometry"]["location"]["lng"]

        except Exception as e:
            print(f"Error geocoding location: {e}")
            return []

        # Now search for places near those coordinates, with optional pagination
        search_url = f"{PLACES_API_BASE}/textsearch/json"

        def filter_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            filtered: List[Dict[str, Any]] = []
            for place in results:
                # Check rating if requested
                if min_rating is not None and place.get("rating", 0) < min_rating:
                    continue

                # Check price level if specified
                if price_level is not None:
                    place_price = place.get("price_level")
                    if place_price is None or place_price not in price_level:
                        continue

                # Require photo if requested
                if require_photo:
                    has_photo = bool(place.get("photos")) and bool(
                        place.get("photos", [{}])[0].get("photo_reference")
                    )
                    if not has_photo:
                        continue

                # Limit to allowed Google types if provided
                if allowed_types is not None:
                    place_types = place.get("types", [])
                    if not any(t in allowed_types for t in place_types):
                        continue

                # Extract lat/lng from geometry if available
                geometry = place.get("geometry", {})
                location = geometry.get("location", {})
                lat_val = location.get("lat")
                lng_val = location.get("lng")

                filtered.append(
                    {
                        "place_id": place.get("place_id"),
                        "name": place.get("name"),
                        "address": place.get("formatted_address"),
                        "rating": place.get("rating"),
                        "price_level": place.get("price_level"),
                        "types": place.get("types", []),
                        "photo_reference": (
                            place.get("photos", [{}])[0].get("photo_reference")
                            if place.get("photos")
                            else None
                        ),
                        "lat": lat_val,
                        "lng": lng_val,
                    }
                )
            return filtered

        try:
            collected: List[Dict[str, Any]] = []
            pages_fetched = 0
            next_token: Optional[str] = None

            while True:
                params: Dict[str, Any]
                if next_token:
                    # When using next_page_token, only send token + key
                    params = {
                        "pagetoken": next_token,
                        "key": self.api_key,
                    }
                else:
                    params = {
                        "query": query,
                        "location": f"{lat},{lng}",
                        "radius": radius,
                        "key": self.api_key,
                    }

                response = requests.get(search_url, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()

                status = data.get("status")
                if status not in ("OK", "ZERO_RESULTS"):
                    # When token not ready, Google returns INVALID_REQUEST briefly
                    if status == "INVALID_REQUEST" and next_token:
                        time.sleep(2)
                        continue
                    print(f"Places search failed: {status}")
                    break

                results = data.get("results", [])
                collected.extend(filter_results(results))

                pages_fetched += 1
                next_token = data.get("next_page_token")

                if not next_token or pages_fetched >= max_pages:
                    break

                # Per Google docs, next_page_token requires a short wait
                time.sleep(2)

            return collected

        except Exception as e:
            print(f"Error searching places: {e}")
            return []

    def get_place_details(self, place_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a specific place.

        Args:
            place_id: Google Place ID

        Returns:
            Dictionary with detailed place information
        """
        url = f"{PLACES_API_BASE}/details/json"
        params = {
            "place_id": place_id,
            "fields": (
                "name,formatted_address,rating,price_level,photos,"
                "geometry,url,types,opening_hours"
            ),
            "key": self.api_key,
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get("status") != "OK":
                print(f"Place details failed: {data.get('status')}")
                return None

            result = data.get("result", {})

            result_dict = {
                "place_id": place_id,
                "name": result.get("name"),
                "address": result.get("formatted_address"),
                "rating": result.get("rating"),
                "price_level": result.get("price_level"),
                "types": result.get("types", []),
                "google_maps_url": result.get("url"),
                "photo_reference": (
                    result.get("photos", [{}])[0].get("photo_reference")
                    if result.get("photos")
                    else None
                ),
            }
            opening = result.get("opening_hours", {})
            result_dict["opening_hours"] = opening.get("weekday_text", [])
            return result_dict

        except Exception as e:
            print(f"Error getting place details: {e}")
            return None

    def get_place_photo_url(self, photo_reference: str, max_width: int = 1080) -> Optional[str]:
        """
        Get a photo URL from a photo reference.

        Args:
            photo_reference: Photo reference from Places API
            max_width: Maximum width in pixels (default 1080)

        Returns:
            Photo URL string
        """
        if not photo_reference:
            return None

        return (
            f"{PLACES_API_BASE}/photo"
            f"?maxwidth={max_width}"
            f"&photo_reference={photo_reference}"
            f"&key={self.api_key}"
        )

    def get_proxy_photo_url(
        self, photo_reference: str, base_url: str, max_width: int = 1080
    ) -> Optional[str]:
        """Build absolute URL to backend photo proxy.

        Args:
            photo_reference: Google Places photo_reference
            base_url: Request base URL (e.g., "http://localhost:8765/")
            max_width: Desired width
        """
        if not photo_reference or not base_url:
            return None
        base = base_url.rstrip("/")
        return f"{base}/places/photo?ref={quote(photo_reference)}&w={max_width}"

    def autocomplete_places(self, query: str, limit: int = 6) -> List[Dict[str, Any]]:
        """Return lightweight autocomplete suggestions for destinations.

        Uses Places Autocomplete API. Falls back to geocode when needed.
        """
        try:
            url = f"{PLACES_API_BASE}/autocomplete/json"
            params = {
                "input": query,
                "types": "(cities)",
                "key": self.api_key,
            }
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") != "OK":
                return []
            preds = data.get("predictions", [])[:limit]
            return [
                {
                    "description": p.get("description"),
                    "place_id": p.get("place_id"),
                    "types": p.get("types", []),
                }
                for p in preds
            ]
        except Exception as e:
            print(f"Autocomplete error: {e}")
            return []

    def search_by_preferences(
        self,
        destination: str,
        user_interests: List[str],
        budget_style: int,
        max_results: int = 30,
        *,
        min_rating: Optional[float] = None,
        require_photo: bool = False,
        allowed_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for places based on user preferences.

        Args:
            destination: City/location name
            user_interests: List of user's selected interests
            budget_style: Budget preference (0-100)
            max_results: Maximum number of results to return

        Returns:
            List of places matching user preferences
        """
        # Map budget style to price levels
        if budget_style <= 33:
            price_levels = [1, 2]  # Budget
        elif budget_style <= 66:
            price_levels = [2, 3]  # Moderate
        else:
            price_levels = [3, 4]  # Luxury

        # Map user interests to search queries
        interest_to_query = {
            "Museums": "museums",
            "Art Galleries": "art galleries",
            "Fine dining": "fine dining restaurants",
            "Street food": "street food markets",
            "Coffee & café hopping": "cafes coffee shops",
            "Local Festivals": "festivals events",
            "Architecture & Landmarks": "landmarks monuments",
            "Historical Tours": "historical sites",
            "Live Music / Concerts": "live music venues",
            "Bar Crawls": "bars pubs",
            "Clubs": "nightclubs",
            "Beach & Water Activities": "beaches water activities",
            "Hiking": "hiking trails nature",
            "Mountains & Scenic Views": "scenic viewpoints",
            "Spas": "spas wellness",
            "Shopping": "shopping",
            "Luxury Boutiques": "luxury shopping boutiques",
            "Vintage & Thrift": "vintage shops thrift stores",
            "Instagrammable Spots": "photo spots instagram",
        }

        all_places = []
        seen_place_ids = set()

        # Build comprehensive query list: user interests + general categories upfront
        all_queries = []

        # Add user-specific interests
        for interest in user_interests:
            query = interest_to_query.get(interest, interest.lower())
            all_queries.append(query)

        # Always include broader categories upfront (not as fallback)
        all_queries.extend(
            ["tourist attractions", "top restaurants", "things to do", "popular places"]
        )

        # Default allowed types if not provided (travel-relevant)
        if allowed_types is None:
            allowed_types = [
                "tourist_attraction",
                "museum",
                "art_gallery",
                "restaurant",
                "cafe",
                "bar",
                "night_club",
                "park",
                "point_of_interest",
                "shopping_mall",
                "clothing_store",
                "spa",
                "movie_theater",
                "stadium",
                "premise",
            ]

        # Search all queries and deduplicate
        for query in all_queries:
            places = self.search_places(
                location=destination,
                query=query,
                price_level=price_levels,
                min_rating=min_rating,
                require_photo=require_photo,
                allowed_types=allowed_types,
            )

            # Add unique places
            for place in places:
                if place["place_id"] not in seen_place_ids:
                    seen_place_ids.add(place["place_id"])
                    all_places.append(place)

                    if len(all_places) >= max_results:
                        return all_places

        return all_places[:max_results]


# Singleton instance
places_service = PlacesService()
