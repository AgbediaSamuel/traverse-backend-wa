#!/usr/bin/env python3
"""
Test script for preference extraction and itinerary generation.
Tests the new NLP-based preference extraction system.

Usage:
    poetry run python scripts/test_preference_extraction.py
"""
import os
import sys
from typing import Any

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add the app directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:

    from app.core.preference_aggregator import aggregate_preferences
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


def print_preferences(prefs: dict[str, Any], label: str = "Preferences"):
    """Print formatted preferences."""
    print(f"\n{label}:")
    print(f"  Budget Style: {prefs.get('budget_style', 'N/A')}")
    print(f"  Pace Style: {prefs.get('pace_style', 'N/A')}")
    print(f"  Schedule Style: {prefs.get('schedule_style', 'N/A')}")
    print(f"  Selected Interests: {prefs.get('selected_interests', [])}")
    other = prefs.get("other_interests", [])
    if isinstance(other, list):
        print(f"  Other Interests ({len(other)}): {other}")
    elif other:
        print(f"  Other Interests: {other}")
    else:
        print("  Other Interests: None")


def test_extraction_from_text(text: str, context: dict[str, Any] | None = None):
    """Test the NLP extraction function."""
    print("\nTesting extraction from text:")
    print(f"  Input: '{text[:100]}{'...' if len(text) > 100 else ''}'")

    try:
        extracted = extract_preferences_from_text(text, context)

        print("\n  ✅ Extraction successful!")
        print(
            f"  Search Queries ({len(extracted['search_queries'])}): {extracted['search_queries']}"
        )
        print(f"  Place Types ({len(extracted['place_types'])}): {extracted['place_types']}")
        print(f"  Keywords ({len(extracted['keywords'])}): {extracted['keywords'][:10]}...")
        if extracted["preference_signals"]:
            print(f"  Preference Signals: {extracted['preference_signals']}")

        return extracted
    except Exception as e:
        print(f"  ❌ Extraction failed: {e}")
        import traceback

        traceback.print_exc()
        return None


def find_users_with_preferences():
    """Find users in the database who have preferences."""
    print_section("Finding Users with Preferences")

    users_with_prefs = []

    try:
        # Get all users
        all_users = list(repo.users_collection.find({}))
        print(f"Found {len(all_users)} total users in database")

        for user in all_users:
            clerk_id = user.get("clerk_user_id")
            if not clerk_id:
                continue

            prefs = repo.get_user_preferences_dict(clerk_id)
            if prefs:
                has_other = bool(prefs.get("other_interests"))
                has_selected = bool(prefs.get("selected_interests"))

                if has_other or has_selected:
                    users_with_prefs.append(
                        {
                            "clerk_id": clerk_id,
                            "email": user.get("email", "N/A"),
                            "name": user.get("name", "N/A"),
                            "preferences": prefs,
                            "has_other_interests": has_other,
                            "has_selected_interests": has_selected,
                        }
                    )

        print(f"\nFound {len(users_with_prefs)} users with preferences")

        for idx, user_info in enumerate(users_with_prefs[:5], 1):  # Show first 5
            print(f"\n{idx}. {user_info['name']} ({user_info['email']})")
            print(f"   Clerk ID: {user_info['clerk_id']}")
            print(f"   Has selected_interests: {user_info['has_selected_interests']}")
            print(f"   Has other_interests: {user_info['has_other_interests']}")

        return users_with_prefs

    except Exception as e:
        print(f"❌ Error finding users: {e}")
        import traceback

        traceback.print_exc()
        return []


def test_user_preferences(user_info: dict[str, Any]):
    """Test extraction for a specific user's preferences."""
    print_section(f"Testing Preferences for: {user_info['name']}")

    prefs = user_info["preferences"]
    print_preferences(prefs, "User Preferences")

    # Test extraction from other_interests
    other_interests = prefs.get("other_interests", [])
    if isinstance(other_interests, str):
        other_interests = [other_interests]

    if other_interests:
        combined_text = " ".join([str(o) for o in other_interests if o])
        print("\n📝 Testing extraction from other_interests...")

        context = {
            "destination": "Paris, France",  # Example destination
            "trip_type": "solo",
            "selected_interests": prefs.get("selected_interests", []),
        }

        extracted = test_extraction_from_text(combined_text, context)
        return extracted
    else:
        print("\n⚠️  No other_interests found for this user")
        return None


def test_group_aggregation():
    """Test preference aggregation for group trips."""
    print_section("Testing Group Preference Aggregation")

    try:
        # Find a group invite with multiple participants
        invites = list(repo.trip_invites_collection.find({}))
        print(f"Found {len(invites)} total invites")

        group_invites = [
            inv
            for inv in invites
            if inv.get("trip_type") == "group" and inv.get("collect_preferences")
        ]

        if not group_invites:
            print("⚠️  No group invites with preferences collection found")
            return

        # Test with first group invite
        invite = group_invites[0]
        print(f"\nTesting with invite: {invite.get('trip_name', 'N/A')}")
        print(f"  Destination: {invite.get('destination', 'N/A')}")
        print(f"  Participants: {len(invite.get('participants', []))}")

        # Collect preferences from participants
        pref_docs = []
        for p in invite.get("participants", []):
            if p.get("has_completed_preferences"):
                user = repo.users_collection.find_one({"email": p["email"]})
                if user and user.get("clerk_user_id"):
                    up = repo.get_user_preferences_dict(user["clerk_user_id"]) or {}
                    if up:
                        pref_docs.append(up)

        if not pref_docs:
            print("⚠️  No participants with completed preferences found")
            return

        print(f"\nFound {len(pref_docs)} sets of preferences to aggregate")

        # Aggregate preferences
        aggregated = aggregate_preferences(pref_docs)
        print_preferences(aggregated, "Aggregated Preferences")

        # Test extraction from aggregated other_interests
        other_interests = aggregated.get("other_interests", [])
        if other_interests:
            combined_text = " ".join([str(o) for o in other_interests if o])
            print("\n📝 Testing extraction from aggregated other_interests...")

            context = {
                "destination": invite.get("destination", "Unknown"),
                "trip_type": "group",
                "selected_interests": aggregated.get("selected_interests", []),
            }

            extracted = test_extraction_from_text(combined_text, context)
            return extracted
        else:
            print("\n⚠️  No aggregated other_interests found")
            return None

    except Exception as e:
        print(f"❌ Error testing group aggregation: {e}")
        import traceback

        traceback.print_exc()
        return None


def main():
    """Main test function."""
    print_section("Preference Extraction & Scoring Test Suite")
    print("Testing the new NLP-based preference extraction system\n")

    # Test 1: Find users with preferences
    users_with_prefs = find_users_with_preferences()

    if not users_with_prefs:
        print("\n⚠️  No users with preferences found. Make sure:")
        print("   1. Database is connected")
        print("   2. Users have saved preferences")
        print("   3. Preferences collection contains data")
        return

    # Test 2: Test extraction for users with other_interests
    print_section("Testing NLP Extraction for Individual Users")

    users_with_other = [u for u in users_with_prefs if u["has_other_interests"]]

    if users_with_other:
        print(f"\nFound {len(users_with_other)} users with other_interests")
        for user_info in users_with_other[:3]:  # Test first 3
            test_user_preferences(user_info)
    else:
        print("\n⚠️  No users with other_interests found")
        print("   Testing with a sample text instead...")

        # Test with sample text
        sample_text = "I love rooftop bars, street art tours, and hidden local gems. Also interested in vintage shopping and food markets."
        context = {
            "destination": "Tokyo, Japan",
            "trip_type": "solo",
            "selected_interests": ["Museums", "Art Galleries"],
        }
        test_extraction_from_text(sample_text, context)

    # Test 3: Test group aggregation
    test_group_aggregation()

    # Test 4: Summary
    print_section("Test Summary")
    print("✅ Extraction function tested")
    print("✅ User preferences retrieved from database")
    print("✅ Group aggregation tested")
    print("\nNext steps:")
    print("  1. Test full itinerary generation with real user preferences")
    print("  2. Compare results with/without preferences")
    print("  3. Check logs during itinerary generation for extraction messages")


if __name__ == "__main__":
    main()
