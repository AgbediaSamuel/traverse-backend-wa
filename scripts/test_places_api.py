"""
Quick test script for Google Places API integration.
"""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.places_service import places_service


def test_places_api():
    """Test the Places API with a simple search."""
    print("Testing Google Places API...")
    print(f"API Key configured: {places_service.api_key[:10]}...")

    # Test 1: Search for museums in Paris
    print("\n--- Test 1: Searching for museums in Paris ---")
    results = places_service.search_places(
        location="Paris, France", query="museums", min_rating=4.0
    )

    print(f"Found {len(results)} museums")
    if results:
        print("\nFirst 3 results:")
        for i, place in enumerate(results[:3], 1):
            print(f"\n{i}. {place['name']}")
            print(f"   Rating: {place.get('rating', 'N/A')}")
            print(f"   Address: {place.get('address', 'N/A')}")
            print(f"   Place ID: {place['place_id']}")

            # Test getting photo URL
            if place.get("photo_reference"):
                photo_url = places_service.get_place_photo_url(place["photo_reference"])
                print(f"   Photo URL: {photo_url[:80]}...")

    # Test 2: Get place details
    if results:
        print("\n--- Test 2: Getting detailed info for first place ---")
        place_id = results[0]["place_id"]
        details = places_service.get_place_details(place_id)

        if details:
            print(f"Name: {details['name']}")
            print(f"Google Maps URL: {details.get('google_maps_url', 'N/A')}")
            print(f"Types: {', '.join(details.get('types', [])[:5])}")

    # Test 3: Search by preferences
    print("\n--- Test 3: Searching by user preferences ---")
    preference_results = places_service.search_by_preferences(
        destination="Paris, France",
        user_interests=["Museums", "Fine dining", "Art Galleries"],
        budget_style=75,  # Luxury
        max_results=10,
    )

    print(f"Found {len(preference_results)} places matching preferences")
    if preference_results:
        print("\nSample results:")
        for i, place in enumerate(preference_results[:5], 1):
            print(f"{i}. {place['name']} (Rating: {place.get('rating', 'N/A')})")

    print("\n✅ All tests completed!")


if __name__ == "__main__":
    test_places_api()
