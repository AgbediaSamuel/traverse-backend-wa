#!/usr/bin/env python3
"""
Test full itinerary generation with real user preferences.
Tests the complete flow from preferences to itinerary generation.

Usage:
    poetry run python scripts/test_itinerary_generation.py
"""
import os
import sys
from datetime import datetime, timedelta

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add the app directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from app.core.preference_extractor import extract_preferences_from_text
    from app.core.repository import repo
except Exception as e:
    print(f"❌ Failed to import modules: {e}")
    print("Make sure:")
    print("  1. You're running from the backend directory")
    print("  2. Poetry environment is activated: poetry install")
    print("  3. MONGODB_URI is set in your .env file")
    sys.exit(1)


def print_section(title: str):
    """Print a formatted section header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80 + "\n")


def test_itinerary_generation():
    """Test full itinerary generation with real user preferences."""
    print_section("Testing Full Itinerary Generation")

    # Find a user with preferences
    users = list(repo.users_collection.find({}))
    user_with_prefs = None

    for user in users:
        clerk_id = user.get("clerk_user_id")
        if not clerk_id:
            continue

        prefs = repo.get_user_preferences_dict(clerk_id)
        if prefs and prefs.get("other_interests"):
            user_with_prefs = {
                "clerk_id": clerk_id,
                "email": user.get("email", "N/A"),
                "name": user.get("name", "N/A"),
                "preferences": prefs,
            }
            break

    if not user_with_prefs:
        print("❌ No user with other_interests found")
        return

    print(f"Using user: {user_with_prefs['name']} ({user_with_prefs['email']})")
    print("\nPreferences:")
    print(f"  Selected Interests: {user_with_prefs['preferences'].get('selected_interests', [])}")
    other = user_with_prefs["preferences"].get("other_interests", "")
    print(f"  Other Interests: {other}")

    # Set up dates (7 days from now)
    start_date = datetime.now() + timedelta(days=7)
    end_date = start_date + timedelta(days=3)  # 3-day trip

    # Create generation request
    request_data = {
        "clerk_user_id": user_with_prefs["clerk_id"],
        "trip_name": "Test Trip - Preference Testing",
        "destination": "Paris, France",  # Using a well-known destination
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "trip_type": "solo",
        "vibe_notes": "romantic restaurants, rooftop bars with city views",  # Testing vibe_notes
    }

    # Create generation request
    request_data = {
        "clerk_user_id": user_with_prefs["clerk_id"],
        "trip_name": "Test Trip - Preference Testing",
        "traveler_name": user_with_prefs["name"] or "Test Traveler",
        "destination": "Paris, France",  # Using a well-known destination
        "dates": f"{start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}",
        "trip_type": "solo",
        "vibe_notes": "romantic restaurants, rooftop bars with city views",  # Testing vibe_notes
    }

    print("\n🚀 Generating itinerary...")
    print("  (This may take a while as it calls Google Places API and LLM)")

    try:
        # Import the function directly
        from app.api.routers.itineraries import generate_itinerary_v2

        # Generate itinerary (function expects a dict)
        result = generate_itinerary_v2(request_data)

        print("\n✅ Itinerary generated successfully!")

        # Display results
        if isinstance(result, dict):
            itinerary_id = result.get("id") or result.get("itinerary_id")
            print(f"\n📝 Itinerary ID: {itinerary_id}")

            # Get the full itinerary (result might already be the itinerary)
            if itinerary_id:
                itinerary = repo.get_itinerary(itinerary_id)
            else:
                itinerary = result  # result might already be the full itinerary

            if itinerary:
                # Itinerary might be nested under 'document'
                doc = itinerary.get("document", itinerary)

                print("\n📅 Itinerary Details:")
                print(f"  Trip Name: {doc.get('trip_name', 'N/A')}")
                print(f"  Destination: {doc.get('destination', 'N/A')}")
                print(f"  Days: {len(doc.get('days', []))}")

                # Show venues from first day
                days = doc.get("days", [])
                if days:
                    first_day = days[0]
                    activities = first_day.get("activities", [])
                    print(f"\n🎯 First Day Activities ({len(activities)}):")
                    for idx, activity in enumerate(activities[:5], 1):  # Show first 5
                        # Activity might have venue nested or directly
                        if isinstance(activity, dict):
                            venue = activity.get("venue", {})
                            if venue:
                                venue_name = venue.get("name", activity.get("title", "N/A"))
                                venue_type = venue.get("types", [])
                            else:
                                venue_name = activity.get("title", "N/A")
                                venue_type = []
                        else:
                            venue_name = getattr(activity, "title", "N/A")
                            venue_type = []

                        print(f"  {idx}. {venue_name}")
                        if venue_type:
                            print(f"     Types: {', '.join(venue_type[:3])}")
                        print(
                            f"     Time: {activity.get('time', 'N/A') if isinstance(activity, dict) else getattr(activity, 'time', 'N/A')}"
                        )
                else:
                    print("\n⚠️  No days found in itinerary")
                    print(f"  Full structure keys: {list(itinerary.keys())}")
                    if "document" in itinerary:
                        print(f"  Document keys: {list(itinerary['document'].keys())}")

        return result

    except Exception as e:
        print(f"\n❌ Error generating itinerary: {e}")
        import traceback

        traceback.print_exc()
        return None


def test_extraction_before_generation():
    """Test extraction on the user's preferences before generation."""
    print_section("Pre-Generation Extraction Test")

    # Find user with preferences
    users = list(repo.users_collection.find({}))
    user_with_prefs = None

    for user in users:
        clerk_id = user.get("clerk_user_id")
        if not clerk_id:
            continue

        prefs = repo.get_user_preferences_dict(clerk_id)
        if prefs and prefs.get("other_interests"):
            user_with_prefs = {"clerk_id": clerk_id, "preferences": prefs}
            break

    if not user_with_prefs:
        print("⚠️  No user with other_interests found for pre-test")
        return

    # Test extraction from other_interests
    other_interests = user_with_prefs["preferences"].get("other_interests", "")
    if isinstance(other_interests, list):
        other_interests = " ".join([str(o) for o in other_interests if o])

    print(f"Testing extraction from: '{other_interests}'")

    context = {
        "destination": "Paris, France",
        "trip_type": "solo",
        "selected_interests": user_with_prefs["preferences"].get("selected_interests", []),
    }

    extracted = extract_preferences_from_text(other_interests, context)

    print("\n✅ Extracted:")
    print(f"  Search Queries: {extracted['search_queries']}")
    print(f"  Place Types: {extracted['place_types']}")
    print(f"  Keywords: {extracted['keywords'][:10]}...")

    # Test extraction from vibe_notes
    vibe_notes = "romantic restaurants, rooftop bars with city views"
    print(f"\nTesting extraction from vibe_notes: '{vibe_notes}'")

    extracted_vibe = extract_preferences_from_text(vibe_notes, context)

    print("\n✅ Extracted from vibe_notes:")
    print(f"  Search Queries: {extracted_vibe['search_queries']}")
    print(f"  Place Types: {extracted_vibe['place_types']}")
    print(f"  Keywords: {extracted_vibe['keywords'][:10]}...")

    return extracted, extracted_vibe


def main():
    """Main test function."""
    print_section("Full Itinerary Generation Test Suite")
    print("Testing complete flow: Preferences → Extraction → Generation\n")

    # Test 1: Pre-generation extraction test
    test_extraction_before_generation()

    # Test 2: Full itinerary generation
    print("\n" + "=" * 80)
    print("NOTE: This will call Google Places API and generate a real itinerary.")
    print("It may take 30-60 seconds and will create a real trip in the database.")
    print("=" * 80)
    print("Starting full generation test...\n")

    result = test_itinerary_generation()

    # Summary
    print_section("Test Summary")
    print("✅ Extraction tested before generation")
    if result:
        print("✅ Full itinerary generation completed")
        print("\nCheck the generated itinerary to see:")
        print("  1. If venues match user preferences")
        print("  2. If extracted queries were used in search")
        print("  3. If interest match scores are applied")
    else:
        print("❌ Full itinerary generation failed")
        print("   Check error messages above")


if __name__ == "__main__":
    main()
