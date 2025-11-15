"""
Google Places API integration for fetching venue data and photos.
"""

import os
import time
from typing import Any
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

    def geocode_location(self, location: str) -> dict[str, float] | None:
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
            geocode_response = requests.get(
                geocode_url, params=geocode_params, timeout=10
            )
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

    def geocode_get_place_id(self, location: str) -> str | None:
        """
        Geocode a location and return its Google Place ID.

        Args:
            location: City/destination name (e.g., "Lagos, Nigeria")

        Returns:
            Place ID string or None if geocoding fails
        """
        geocode_url = "https://maps.googleapis.com/maps/api/geocode/json"
        geocode_params = {"address": location, "key": self.api_key}

        try:
            geocode_response = requests.get(
                geocode_url, params=geocode_params, timeout=10
            )
            geocode_response.raise_for_status()
            geocode_data = geocode_response.json()

            if geocode_data.get("status") != "OK" or not geocode_data.get("results"):
                return None

            # Extract place_id from the first result
            result = geocode_data["results"][0]
            place_id = result.get("place_id")
            return place_id

        except Exception as e:
            print(f"Error geocoding for place_id: {e}")
            return None

    def search_places(
        self,
        location: str,
        query: str,
        radius: int = 5000,
        min_rating: float | None = None,
        price_level: list[int] | None = None,
        require_photo: bool = False,
        allowed_types: list[str] | None = None,
        max_pages: int = 1,
        place_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Search for places using Text Search API.

        Args:
            location: City/destination name (e.g., "Paris, France")
            query: Search query (e.g., "museums", "fine dining restaurants")
            radius: Search radius in meters (default 5000m = 5km)
            min_rating: Minimum rating filter (default 3.5)
            price_level: List of acceptable price levels [1-4] (optional)
            place_id: Optional Google Place ID (more reliable than geocoding)

        Returns:
            List of place dictionaries with basic info
        """
        # Get coordinates: prefer place_id if provided, otherwise geocode
        lat = None
        lng = None

        if place_id:
            # Use Place Details API to get coordinates (more reliable)
            try:
                place_details = self.get_place_details(place_id)
                if (
                    place_details
                    and place_details.get("lat")
                    and place_details.get("lng")
                ):
                    lat = place_details["lat"]
                    lng = place_details["lng"]
                    print(f"[search_places] Using place_id {place_id} → ({lat}, {lng})")
                else:
                    print(
                        f"[search_places] Failed to get coordinates from place_id, falling back to geocoding"
                    )
            except Exception as e:
                print(
                    f"[search_places] Error getting place details for place_id: {e}, falling back to geocoding"
                )

        if lat is None or lng is None:
            # Fall back to geocoding if place_id not provided or failed
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

                if geocode_data.get("status") != "OK" or not geocode_data.get(
                    "results"
                ):
                    status = geocode_data.get("status")
                    print(f"Geocoding failed for {location}: {status}")
                    return []

                lat = geocode_data["results"][0]["geometry"]["location"]["lat"]
                lng = geocode_data["results"][0]["geometry"]["location"]["lng"]

            except Exception as e:
                print(f"Error geocoding location: {e}")
                return []

        # Now search for places near those coordinates
        search_url = f"{PLACES_API_BASE}/textsearch/json"

        def filter_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
            filtered: list[dict[str, Any]] = []
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

                # Extract coordinates from geometry.location
                lat = None
                lng = None
                geometry = place.get("geometry")
                if geometry and geometry.get("location"):
                    location = geometry["location"]
                    lat = location.get("lat")
                    lng = location.get("lng")

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
                        "lat": lat,
                        "lng": lng,
                    }
                )
            return filtered

        try:
            collected: list[dict[str, Any]] = []
            pages_fetched = 0
            next_token: str | None = None

            while True:
                params: dict[str, Any]
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

    def get_place_details(self, place_id: str) -> dict[str, Any] | None:
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

            # Extract coordinates from geometry.location
            lat = None
            lng = None
            geometry = result.get("geometry")
            if geometry and geometry.get("location"):
                location = geometry["location"]
                lat = location.get("lat")
                lng = location.get("lng")

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
                "lat": lat,
                "lng": lng,
            }
            opening = result.get("opening_hours", {})
            result_dict["opening_hours"] = opening.get("weekday_text", [])
            return result_dict

        except Exception as e:
            print(f"Error getting place details: {e}")
            return None

    def get_place_photo_url(
        self, photo_reference: str, max_width: int = 1080
    ) -> str | None:
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
        self, photo_reference: str, base_url: str = "", max_width: int = 1080
    ) -> str | None:
        """Build URL to backend photo proxy.

        Args:
            photo_reference: Google Places photo_reference
            base_url: Request base URL (e.g., "http://localhost:8765/") or empty string for relative paths
            max_width: Desired width
        """
        if not photo_reference:
            return None

        # Always use relative path /api/places/photo when behind nginx proxy
        # This works correctly when proxied through ngrok
        if not base_url:
            return f"/api/places/photo?ref={quote(photo_reference)}&w={max_width}"

        # If base_url is provided, ensure it includes /api prefix
        base = base_url.rstrip("/")
        # Check if base_url already includes /api, if not add it
        if not base.endswith("/api"):
            return f"{base}/api/places/photo?ref={quote(photo_reference)}&w={max_width}"
        else:
            return f"{base}/places/photo?ref={quote(photo_reference)}&w={max_width}"

    def autocomplete_places(self, query: str, limit: int = 6) -> list[dict[str, Any]]:
        """Return lightweight autocomplete suggestions for destinations.

        Uses Places Autocomplete API with improved filtering for realistic cities.
        Handles country searches by showing cities within that country.
        """
        try:
            # Common country names and their ISO codes
            country_map = {
                "spain": "ES",
                "france": "FR",
                "italy": "IT",
                "germany": "DE",
                "united kingdom": "GB",
                "uk": "GB",
                "portugal": "PT",
                "greece": "GR",
                "netherlands": "NL",
                "belgium": "BE",
                "switzerland": "CH",
                "austria": "AT",
                "czech republic": "CZ",
                "poland": "PL",
                "united states": "US",
                "usa": "US",
                "us": "US",
                "canada": "CA",
                "mexico": "MX",
                "brazil": "BR",
                "argentina": "AR",
                "chile": "CL",
                "japan": "JP",
                "china": "CN",
                "india": "IN",
                "south korea": "KR",
                "thailand": "TH",
                "vietnam": "VN",
                "singapore": "SG",
                "malaysia": "MY",
                "indonesia": "ID",
                "philippines": "PH",
                "australia": "AU",
                "new zealand": "NZ",
                "south africa": "ZA",
                "egypt": "EG",
                "morocco": "MA",
                "turkey": "TR",
                "israel": "IL",
                "uae": "AE",
                "united arab emirates": "AE",
                "dubai": "AE",  # Special case - Dubai is often searched as country
            }

            query_lower = query.lower().strip()
            country_code = None
            for name, code in country_map.items():
                if query_lower == name or query_lower.startswith(name + " "):
                    country_code = code
                    break

            url = f"{PLACES_API_BASE}/autocomplete/json"
            params = {
                "input": query,
                "key": self.api_key,
            }
            if country_code:
                params["components"] = f"country:{country_code}"

            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            
            if data.get("status") != "OK":
                return []
<<<<<<< HEAD

            preds = data.get("predictions", [])
            destination_keywords = {
                "island",
                "coast",
                "region",
                "valley",
                "mountain",
                "mountains",
                "bay",
                "peninsula",
                "archipelago",
                "riviera",
                "highlands",
                "plateau",
                "desert",
            }
            low_level_markers = {
                "county",
                "district",
                "parish",
                "township",
                "census",
                "borough",
            }
            query_tokens = {
                token for token in query_lower.replace(",", " ").split() if token
            }
            query_has_keyword = any(
                token in destination_keywords for token in query_tokens
            )

            def classify(types: list[str]) -> str:
                if "locality" in types:
                    return "city"
                if "country" in types:
                    return "country"
                if "administrative_area_level_1" in types:
                    return "region"
                if "administrative_area_level_2" in types:
                    return "subregion"
                return "other"

            def contains_destination_term(text: str) -> bool:
                lower = text.lower()
                return any(keyword in lower for keyword in destination_keywords)

            filtered_candidates: list[dict[str, Any]] = []
            for prediction in preds:
                types = prediction.get("types", [])
                description = (prediction.get("description") or "").strip()
                structured = prediction.get("structured_formatting") or {}
                main_text = (structured.get("main_text") or "").strip()
                main_lower = main_text.lower()
                desc_lower = description.lower()
                classification = classify(types)
                contains_keyword = contains_destination_term(
                    description + " " + main_text
                )
                has_low_level_marker = any(
                    marker in desc_lower for marker in low_level_markers
                )

                if classification == "other":
                    continue

                allow = False
                if classification in ("city", "country"):
                    allow = True
                elif classification == "region":
                    allow = (
                        query_has_keyword
                        or query_lower == main_lower
                        or (query_lower and query_lower in desc_lower)
                        or contains_keyword
                    ) and not has_low_level_marker
                elif classification == "subregion":
                    allow = (
                        query_has_keyword
                        or contains_keyword
                        or query_lower == main_lower
                    ) and not has_low_level_marker

                if not allow:
                    continue

                filtered_candidates.append(
                    {
                        "prediction": prediction,
                        "classification": classification,
                        "main_lower": main_lower,
                        "contains_keyword": contains_keyword,
                    }
                )

            if not filtered_candidates:
                return []

            base_weights = {
                "city": 18.0,
                "country": 15.0,
                "region": 11.0,
                "subregion": 8.0,
            }

            def score_candidate(candidate: dict[str, Any]) -> float:
                prediction = candidate["prediction"]
                classification = candidate["classification"]
                contains_keyword = candidate["contains_keyword"]
                main_lower = candidate["main_lower"]
                description = (prediction.get("description") or "").lower()
                score = base_weights.get(classification, 0.0)

                if query_lower == main_lower:
                    score += 12.0
                elif main_lower.startswith(query_lower):
                    score += 6.0
                elif query_lower and query_lower in description:
                    score += 4.0

                if query_has_keyword and classification in {"region", "subregion"}:
                    score += 5.0

                if contains_keyword:
                    score += 3.0

                if len(main_lower) > 25:
                    score -= 4.0

                return score

            scored_preds = [
                (score_candidate(candidate), candidate["prediction"])
                for candidate in filtered_candidates
            ]
            scored_preds.sort(key=lambda item: item[0], reverse=True)

            filtered_preds = [p for score, p in scored_preds if score >= -5.0][
                : limit * 2
            ]

            seen_names = set()
            final_preds = []
            for prediction in filtered_preds:
                description = prediction.get("description", "")
                city_name = description.split(",")[0].strip().lower()
                if not city_name or city_name in seen_names:
                    continue
                if len(city_name) > 60:
                    continue
                seen_names.add(city_name)
                final_preds.append(prediction)
                if len(final_preds) >= limit:
                    break

            def build_display_name(prediction: dict[str, Any]) -> str:
                description = prediction.get("description") or ""
                structured = prediction.get("structured_formatting") or {}
                main_text = (structured.get("main_text") or "").strip()
                secondary_text = (structured.get("secondary_text") or "").strip()

                if not main_text and description:
                    main_text = description.split(",")[0].strip()

                display_parts: list[str] = []
                seen_parts: set[str] = set()

                def add_part(part: str) -> None:
                    cleaned = part.strip()
                    if not cleaned:
                        return
                    lowered = cleaned.lower()
                    if lowered in seen_parts:
                        return
                    display_parts.append(cleaned)
                    seen_parts.add(lowered)

                if main_text:
                    add_part(main_text)

                if secondary_text:
                    segments = [
                        seg.strip() for seg in secondary_text.split(",") if seg.strip()
                    ]
                    if segments:
                        add_part(segments[-1])
                elif description:
                    segments = [
                        seg.strip() for seg in description.split(",") if seg.strip()
                    ]
                    if len(segments) >= 2:
                        add_part(segments[-1])

                if not display_parts and description:
                    return description

                return ", ".join(display_parts)

            return [
                {
                    "description": p.get("description"),
                    "display_name": build_display_name(p),
                    "place_id": p.get("place_id"),
                    "types": p.get("types", []),
                }
                for p in final_preds
            ]
        except Exception as e:
            print(f"Autocomplete error: {e}")
            return []

    def search_by_preferences(
        self,
        destination: str,
        user_interests: list[str],
        budget_style: int,
        max_results: int = 30,
        *,
        min_rating: float | None = None,
        require_photo: bool = False,
        allowed_types: list[str] | None = None,
        extracted_queries: list[str] | None = None,
        extracted_place_types: list[str] | None = None,
        pace_style: int = 50,  # Added for compatibility (not used in legacy)
        rank_preference: (
            str | None
        ) = None,  # Added for compatibility (not used in legacy)
        max_pages: int | None = None,  # Added for compatibility
        place_id: str | None = None,  # Google Place ID (more reliable than geocoding)
    ) -> list[dict[str, Any]]:
        """
        Search for places based on user preferences.

        Args:
            destination: City/location name
            user_interests: List of user's selected interests
            budget_style: Budget preference (0-100)
            max_results: Maximum number of results to return
            extracted_queries: Optional list of extracted search queries from NLP
            extracted_place_types: Optional list of extracted Google Places types from NLP

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

        # Build comprehensive query list: user interests + extracted queries + general categories
        all_queries = []

        # Add user-specific interests
        for interest in user_interests:
            query = interest_to_query.get(interest, interest.lower())
            all_queries.append(query)

        # NEW: Add extracted queries from NLP (other_interests/vibe_notes)
        if extracted_queries:
            for query in extracted_queries:
                if query and query.strip():
                    all_queries.append(query.strip())
            print(
                f"[PlacesService] Added {len(extracted_queries)} extracted queries to search"
            )

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

        # NEW: Merge extracted place types with allowed_types
        if extracted_place_types:
            # Filter to valid Google Places types
            valid_types = [
                "tourist_attraction",
                "museum",
                "art_gallery",
                "restaurant",
                "cafe",
                "bar",
                "night_club",
                "park",
                "beach",
                "spa",
                "shopping_mall",
                "theater",
                "stadium",
                "zoo",
                "aquarium",
                "amusement_park",
                "church",
                "temple",
                "mosque",
                "landmark",
                "point_of_interest",
                "natural_feature",
            ]
            for ext_type in extracted_place_types:
                if ext_type.lower() in valid_types and ext_type.lower() not in [
                    t.lower() for t in allowed_types
                ]:
                    allowed_types.append(ext_type.lower())
            print(
                f"[PlacesService] Added {len(extracted_place_types)} extracted place types to filter"
            )

        # Search all queries and deduplicate
        # Use max_pages if provided, otherwise default to 1
        search_max_pages = max_pages if max_pages is not None else 1

        for query in all_queries:
            places = self.search_places(
                location=destination,
                query=query,
                price_level=price_levels,
                min_rating=min_rating,
                require_photo=require_photo,
                allowed_types=allowed_types,
                max_pages=search_max_pages,
                place_id=place_id,  # Pass place_id for reliable location
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
