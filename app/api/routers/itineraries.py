import json
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Request

from app.core.clerk_security import get_current_user_from_clerk
from app.core.cover_image_service import cover_image_service
from app.core.destination_profiling_service import destination_profiling_service
from app.core.places_service import places_service
from app.core.repository import repo
from app.core.schemas import (
    Activity,
    Day,
    ItineraryDocument,
    ItineraryGenerateRequest,
    ShareItineraryRequest,
    UpdateParticipantsRequest,
    User,
)
from app.core.semantic_category_service import semantic_category_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/itineraries", tags=["itineraries"])


def _optimize_day_times(
    day: Day,
    chosen_venues: list[dict[str, Any]],
    opening_hours_cache: dict[str, dict[str, dict[str, str | None]]],
    pace_style: int,
) -> None:
    """
    Optimize activity times: sort chronologically and adjust for travel.

    Args:
        day: Day object with activities
        chosen_venues: List of venue dicts with place_id, opening_hours, etc.
        opening_hours_cache: Cache of parsed opening hours by place_id
        pace_style: User's pace preference (0-100)
    """
    if len(day.activities) < 2:
        return  # Nothing to optimize

    from app.core.opening_hours_utils import (
        adjust_time_to_opening_hours,
        get_default_hours_by_type,
        is_venue_open_at_time,
        parse_opening_hours,
        parse_time_to_minutes,
    )
    from app.core.travel_time_utils import (
        estimate_activity_duration,
        estimate_travel_time,
    )

    # Helper to convert minutes back to time string
    def minutes_to_time_string(minutes: int) -> str:
        """Convert minutes since midnight to 12-hour format."""
        hours = minutes // 60
        mins = minutes % 60

        if hours == 0:
            return f"12:{mins:02d} AM"
        elif hours < 12:
            return f"{hours}:{mins:02d} AM"
        elif hours == 12:
            return f"12:{mins:02d} PM"
        else:
            return f"{hours - 12}:{mins:02d} PM"

    # Helper to get venue data by place_id
    def get_venue_data(place_id: str | None) -> dict[str, Any] | None:
        if not place_id:
            return None
        for v in chosen_venues:
            if v.get("place_id") == place_id:
                return v
        return None

    # Step 1: Parse times and create list of (activity, parsed_time) tuples
    activities_with_time = []
    for act in day.activities:
        try:
            parsed_time = parse_time_to_minutes(act.time)
            activities_with_time.append((act, parsed_time))
        except Exception as e:
            print(f"[TimeOptimize] Failed to parse time '{act.time}': {e}")
            # Use noon as fallback
            activities_with_time.append((act, 12 * 60))

    # Step 2: Sort by parsed time (chronological order)
    activities_with_time.sort(key=lambda x: x[1])
    print(f"[TimeOptimize] Sorted {len(activities_with_time)} activities " f"chronologically")

    # Step 3: Validate and adjust times based on travel constraints
    day_name = day.date.split(",")[0].strip()  # Extract day name (e.g., "Monday")
    BUFFER_MINUTES = 15  # Buffer between activities

    optimized_activities = []
    for idx, (act, parsed_time) in enumerate(activities_with_time):
        if idx > 0:
            # Check travel time constraint
            prev_act, prev_time = optimized_activities[-1]

            # Get venue data for duration and travel time
            prev_venue_data = get_venue_data(prev_act.place_id)
            prev_venue_types = prev_venue_data.get("types", []) if prev_venue_data else []

            # Calculate required start time
            prev_duration = estimate_activity_duration(prev_venue_types, pace_style)
            travel_mins = 0
            if prev_act.distance_to_next is not None:
                travel_mins = estimate_travel_time(prev_act.distance_to_next)

            required_start = prev_time + prev_duration + travel_mins + BUFFER_MINUTES

            # Adjust if current activity starts too early
            if parsed_time < required_start:
                proposed_time = required_start
                proposed_time_str = minutes_to_time_string(proposed_time)

                # Check opening hours before applying adjustment
                venue_data = get_venue_data(act.place_id)
                adjusted_time_str = proposed_time_str

                if venue_data:
                    # Try to get parsed opening hours from cache
                    parsed_hours = opening_hours_cache.get(act.place_id)

                    if not parsed_hours:
                        # Not in cache - parse and cache it
                        weekday_text = venue_data.get("opening_hours", [])
                        if weekday_text:
                            parsed_hours = parse_opening_hours(weekday_text)
                            opening_hours_cache[act.place_id] = parsed_hours

                    if parsed_hours:
                        # Check if proposed time is valid
                        is_open, reason = is_venue_open_at_time(
                            parsed_hours, day_name, proposed_time_str
                        )

                        if not is_open:
                            # Adjust to opening hours
                            adjusted_time_str = adjust_time_to_opening_hours(
                                proposed_time_str, parsed_hours, day_name
                            )
                            print(
                                f"[TimeOptimize] Adjusted '{act.title}' from "
                                f"{proposed_time_str} to {adjusted_time_str}: {reason}"
                            )
                    else:
                        # No opening hours - use type-based defaults
                        venue_types = venue_data.get("types", [])
                        if venue_types:
                            default_hours = get_default_hours_by_type(venue_types)
                            is_open, reason = is_venue_open_at_time(
                                default_hours, day_name, proposed_time_str
                            )

                            if not is_open:
                                adjusted_time_str = adjust_time_to_opening_hours(
                                    proposed_time_str, default_hours, day_name
                                )
                                print(
                                    f"[TimeOptimize] Adjusted '{act.title}' "
                                    f"using defaults from {proposed_time_str} "
                                    f"to {adjusted_time_str}: {reason}"
                                )

                    # Update parsed time from adjusted string
                    parsed_time = parse_time_to_minutes(adjusted_time_str)

                # Apply adjusted time
                act.time = adjusted_time_str
                print(
                    f"[TimeOptimize] Adjusted '{act.title}' from "
                    f"{minutes_to_time_string(required_start)} to "
                    f"{adjusted_time_str} for travel constraint"
                )

        optimized_activities.append((act, parsed_time))

    # Step 4: Re-sort after adjustments (in case adjustments changed order)
    optimized_activities.sort(key=lambda x: x[1])

    # Step 5: Update day.activities with optimized order
    day.activities = [act for act, _ in optimized_activities]

    print(
        f"[TimeOptimize] Optimized {len(day.activities)} activities with "
        f"chronological ordering and travel constraints"
    )


def _pass_b(
    destination: str,
    destination_place_id: str | None,
    budget_style: int,
    pace_style: int,
    pass_b_max: int,
    seen_ids: set[str],
    selected_interests: list[str],
    other_interests_texts: list[str],
    vibe_notes: str | None,
    payload_notes: str | None,
    trip_type: str,
) -> list[dict[str, Any]]:
    """
    Execute Pass B using semantic category matching.

    Returns:
        List of venue dictionaries
    """
    # Combine user preferences into a single text for embedding
    preference_parts = []

    if selected_interests:
        preference_parts.append(f"Interests: {', '.join(selected_interests)}")

    if other_interests_texts:
        preference_parts.append(" ".join(other_interests_texts))

    if vibe_notes:
        preference_parts.append(vibe_notes)

    if trip_type == "group" and payload_notes:
        preference_parts.append(payload_notes)

    # Add context from sliders
    if budget_style > 66:
        preference_parts.append("prefer luxury and high-end venues")
    elif budget_style < 33:
        preference_parts.append("prefer budget-friendly options")

    if pace_style < 33:
        preference_parts.append("prefer relaxed, slow-paced activities")
    elif pace_style > 66:
        preference_parts.append("prefer fast-paced, action-packed activities")

    user_preference = ". ".join(preference_parts)

    # Debug: Log preference text
    print(f"[Pass B] Preference parts: {preference_parts}")
    print(f"[Pass B] Combined preference text: '{user_preference}'")
    print(f"[Pass B] Preference text length: {len(user_preference)}")

    # Handle edge case: empty preference text
    if not user_preference or not user_preference.strip():
        print("[Pass B] WARNING: Empty preference text! " "Using fallback default preferences.")
        user_preference = "tourist attractions, popular places, things to do"

    # Get destination profile (available categories)
    destination_profile = destination_profiling_service.get_destination_profile(destination)
    print(
        f"[Pass B] Destination profile has "
        f"{len(destination_profile)} categories: "
        f"{list(destination_profile)[:10]}"
    )

    # Find relevant categories using semantic matching
    try:
        top_categories = semantic_category_service.find_relevant_categories(
            user_preference_text=user_preference,
            valid_city_categories=destination_profile,
            top_n=10,  # Get top 10 categories for Pass B
        )
    except Exception as e:
        print(f"[Pass B] ERROR in category matching: {e}")
        # Fallback to default categories
        top_categories = [
            ("tourist_attraction", 0.5),
            ("park", 0.5),
            ("museum", 0.5),
            ("restaurant", 0.5),
            ("cafe", 0.5),
        ]

    top_5 = [cat for cat, _ in top_categories[:5]]
    print(f"[Pass B] Top matched categories: {top_5}")

    # Search using semantic categories
    # Use local seen_ids to track duplicates within Pass B only
    # Don't modify the passed seen_ids - caller will handle that
    local_seen_ids = seen_ids.copy()
    new_venues = []
    targeted_search_types = [cat for cat, _ in top_categories]
    total_searched = 0
    total_found = 0
    total_duplicates = 0

    for category in targeted_search_types:
        print(f"[Pass B] Searching for '{category}' venues...")
        try:
            venues = places_service.search_places(
                location=destination,
                query=category.replace("_", " "),
                radius=10000,
                require_photo=True,
                allowed_types=[category],
                max_pages=4,  # Increased from 2 to fetch 2x more results per category
                place_id=destination_place_id,
            )
            total_searched += 1
            total_found += len(venues)
            print(f"[Pass B] Found {len(venues)} venues " f"for '{category}'")

            # Filter out duplicates (check against both Pass A and Pass B)
            category_new = 0
            for venue in venues:
                if venue["place_id"] not in local_seen_ids:
                    new_venues.append(venue)
                    local_seen_ids.add(venue["place_id"])
                    category_new += 1
                else:
                    total_duplicates += 1

            print(
                f"[Pass B] Added {category_new} new venues "
                f"({len(venues) - category_new} duplicates) for '{category}'"
            )

            # Stop if we have enough
            if len(new_venues) >= pass_b_max:
                print(f"[Pass B] Reached target ({pass_b_max} venues), " "stopping search")
                break
        except Exception as e:
            print(f"[Pass B] ERROR searching '{category}': {e}")
            continue

    print(
        f"[Pass B] Summary: Searched {total_searched} categories, "
        f"found {total_found} total venues, {total_duplicates} duplicates, "
        f"{len(new_venues)} new venues added"
    )

    return new_venues[:pass_b_max]


def _parse_itinerary_json_or_502(raw_text: str) -> ItineraryDocument:
    """Parse LLM output into ItineraryDocument, handling various JSON formats."""
    text = raw_text.strip()
    # Try direct parse first
    try:
        return ItineraryDocument.model_validate_json(text)
    except Exception:
        pass

    # Strip markdown code fences ```json ... ``` or ``` ... ```
    if text.startswith("```"):
        body = text.lstrip("`")
        if body.lower().startswith("json"):
            body = body[4:]
        body = body.lstrip("\n ")
        if body.endswith("```"):
            body = body[:-3]
        text = body.strip()

    try:
        return ItineraryDocument.model_validate_json(text)
    except Exception:
        pass

    # Try loading as JSON and validating
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return ItineraryDocument.model_validate(data)
    except Exception:
        pass

    # Extract content between first '{' and last '}'
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start : end + 1]
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return ItineraryDocument.model_validate(data)
        except Exception:
            pass

    raise HTTPException(
        status_code=502,
        detail={"provider_error": "Schema validation failed", "raw": raw_text},
    )


# Test endpoint - commented out
# @router.get("/sample", response_model=ItineraryDocument)
# def get_sample_itinerary() -> ItineraryDocument:
#     return ItineraryDocument(
#         trip_name="Vegas Weekend",
#         traveler_name="Sheriff",
#         destination="Las Vegas",
#         dates="March 15-17, 2025",
#         duration="Three Day Weekend",
#         cover_image=(
#             "https://images.unsplash.com/"
#             "photo-1683645012230-e3a3c1255434"
#             "?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&q=80&w=1080"
#         ),
#         days=[
#             Day(
#                 date="Friday, March 15",
#                 activities=[
#                     Activity(
#                         time="12:00 PM",
#                         title="Arrival & Check-in",
#                         location="Bellagio Hotel & Casino",
#                         description=(
#                             "Check into the Bellagio suite and enjoy fountain views."
#                         ),
#                         image=(
#                             "https://images.unsplash.com/"
#                             "photo-1683645012230-e3a3c1255434?crop=entropy&cs=tinysrgb"
#                             "&fit=max&fm=jpg&q=80&w=1080"
#                         ),
#                     )
#                 ],
#             ),
#             Day(
#                 date="Saturday, March 16",
#                 activities=[
#                     Activity(
#                         time="10:00 AM",
#                         title="Brunch at Bacchanal",
#                         location="Caesars Palace",
#                         description="Legendary buffet experience.",
#                         image=(
#                             "https://images.unsplash.com/"
#                             "photo-1755862922067-8a0135afc1bb"
#                             "?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&q=80&w=1080"
#                         ),
#                     )
#                 ],
#             ),
#         ],
#         notes=[
#             "Bring ID - required everywhere in Vegas",
#             "Set gambling budget beforehand",
#             "Stay hydrated - desert climate",
#         ],
#     )


# ----------------------------------------------
# New deterministic generator (no LLM selection)
# ----------------------------------------------
@router.post("/generate2", response_model=dict[str, Any])
def generate_itinerary_v2(payload: ItineraryGenerateRequest, request: Request) -> dict[str, Any]:
    """
    Deterministic itinerary generation using weighted scoring over Google Places
    results plus user/group preferences. No LLM is used for venue selection.

    All input is validated using Pydantic schemas for security and data integrity.
    """
    from app.core.itinerary_planner import (
        calculate_daily_activities,
        get_budget_price_levels,
    )
    from app.core.preference_aggregator import aggregate_preferences

    # Extract validated data from schema
    trip_name = payload.trip_name
    traveler_name = payload.traveler_name
    destination = payload.destination
    destination_place_id = payload.destination_place_id  # Google Place ID from autocomplete
    dates = payload.dates
    duration = payload.duration or ""
    clerk_user_id = payload.clerk_user_id
    trip_type = payload.trip_type
    invite_id = payload.invite_id
    payload_participants = payload.participants
    notes_text = (payload.notes or "").lower()
    vibe_notes = payload.vibe_notes or ""  # Optional context for generation

    # For proxy photo URLs, we need to determine the base URL
    # In production (Render), use BACKEND_URL to generate absolute URLs for the template
    # In local development (nginx proxy), use empty string for relative paths
    backend_url = os.getenv("BACKEND_URL", "").rstrip("/")
    base_url = backend_url if backend_url else ""

    # Parse dates → list of day strings (dates already validated by schema)
    # But we still need to parse them for use in the function
    parts = dates.split(" - ")
    start_s, end_s = parts[0].strip(), parts[1].strip()
    start = datetime.fromisoformat(start_s)
    end = datetime.fromisoformat(end_s)
    day_list = [start + timedelta(days=i) for i in range((end - start).days + 1)]

    # Load preferences (solo: user, group: aggregated if enabled)
    aggregated_prefs = None
    if trip_type == "group" and invite_id:
        invite = repo.get_trip_invite(invite_id)
        if invite and invite.get("collect_preferences"):
            pref_docs = []
            for p in invite.get("participants", []):
                if p.get("has_completed_preferences"):
                    user = repo.users_collection.find_one({"email": p["email"]})
                    if user and user.get("clerk_user_id"):
                        up = repo.get_user_preferences_dict(user["clerk_user_id"]) or {}
                        if up:
                            pref_docs.append(up)
            if clerk_user_id:
                org_p = repo.get_user_preferences_dict(clerk_user_id) or {}
                if org_p:
                    pref_docs.append(org_p)
            aggregated_prefs = aggregate_preferences(pref_docs)
        elif clerk_user_id:
            aggregated_prefs = repo.get_user_preferences_dict(clerk_user_id)
    elif clerk_user_id:
        aggregated_prefs = repo.get_user_preferences_dict(clerk_user_id)

    budget_style = aggregated_prefs.get("budget_style", 50) if aggregated_prefs else 50
    pace_style = aggregated_prefs.get("pace_style", 50) if aggregated_prefs else 50
    schedule_style = aggregated_prefs.get("schedule_style", 50) if aggregated_prefs else 50
    interests = aggregated_prefs.get("selected_interests", []) if aggregated_prefs else []

    raw_other_interests = aggregated_prefs.get("other_interests") if aggregated_prefs else None
    if isinstance(raw_other_interests, list):
        other_interests_texts = [
            str(item).strip() for item in raw_other_interests if str(item).strip()
        ]
    elif isinstance(raw_other_interests, str):
        other_interests_texts = [
            part.strip() for part in re.split(r"[,\n]", raw_other_interests) if part.strip()
        ]
    else:
        other_interests_texts = []

    # Extract structured info from other_interests using NLP
    from app.core.preference_extractor import extract_preferences_from_text

    # Initialize with extraction from other_interests if available, otherwise empty
    if other_interests_texts:
        combined_text = " ".join(other_interests_texts)
        extracted_from_other = extract_preferences_from_text(
            combined_text,
            context={
                "destination": destination,
                "trip_type": trip_type,
                "selected_interests": interests,
            },
        )
        print(
            f"[PreferenceExtractor] Extracted {len(extracted_from_other['search_queries'])} search queries from other_interests"
        )
    else:
        extracted_from_other = {
            "search_queries": [],
            "place_types": [],
            "keywords": [],
            "preference_signals": {},
        }

    # Extract structured info from vibe_notes (solo trips only, not group)
    if vibe_notes:
        extracted_from_vibe = extract_preferences_from_text(
            vibe_notes,
            context={
                "destination": destination,
                "trip_type": trip_type,
                "selected_interests": interests,
            },
        )

        # Merge with other_interests extraction
        extracted_from_other["search_queries"].extend(extracted_from_vibe["search_queries"])
        extracted_from_other["place_types"].extend(extracted_from_vibe["place_types"])
        extracted_from_other["keywords"].extend(extracted_from_vibe["keywords"])

        # Merge preference signals
        for key, value in extracted_from_vibe["preference_signals"].items():
            if key not in extracted_from_other["preference_signals"]:
                extracted_from_other["preference_signals"][key] = []
            # Convert existing value to list if it's a string
            existing = extracted_from_other["preference_signals"][key]
            if isinstance(existing, str):
                extracted_from_other["preference_signals"][key] = [existing]
            # Now merge the new value
            if isinstance(value, list):
                extracted_from_other["preference_signals"][key].extend(value)
            else:
                extracted_from_other["preference_signals"][key].append(value)

        print(
            f"[VibeNotes] Extracted {len(extracted_from_vibe['search_queries'])} search queries from vibe notes"
        )

    # Group planning flow stores vibe information in payload.notes
    if trip_type == "group" and payload.notes:
        extracted_group_vibe = extract_preferences_from_text(
            payload.notes,
            context={
                "destination": destination,
                "trip_type": trip_type,
                "selected_interests": interests,
            },
        )

        extracted_from_other["search_queries"].extend(extracted_group_vibe["search_queries"])
        extracted_from_other["place_types"].extend(extracted_group_vibe["place_types"])
        extracted_from_other["keywords"].extend(extracted_group_vibe["keywords"])

        for key, value in extracted_group_vibe["preference_signals"].items():
            if key not in extracted_from_other["preference_signals"]:
                extracted_from_other["preference_signals"][key] = []
            existing = extracted_from_other["preference_signals"][key]
            if isinstance(existing, str):
                extracted_from_other["preference_signals"][key] = [existing]
            if isinstance(value, list):
                extracted_from_other["preference_signals"][key].extend(value)
            else:
                extracted_from_other["preference_signals"][key].append(value)

        print(
            f"[GroupNotes] Extracted {len(extracted_group_vibe['search_queries'])} search queries from group vibe notes"
        )

    # Combine all extracted keywords for scoring
    all_extracted_keywords = extracted_from_other["keywords"]

    # Estimate activities per day
    daily_plan = calculate_daily_activities(pace_style, schedule_style, len(day_list))
    total_needed = 0
    for d in daily_plan:
        total_needed += (d["min_activities"] + d["max_activities"]) // 2

    # --- PRE-FLIGHT FEASIBILITY CHECK ---
    # Quick sanity check: does Google Places know *anything* about this destination?
    print(f"[Pre-flight] Checking feasibility for {destination}...")
    if destination_place_id:
        print(f"[Pre-flight] Using place_id: {destination_place_id}")

    # Collect warnings to return to user
    warnings: list[str] = []
    try:
        pre_flight_venues = places_service.search_places(
            location=destination,
            query="tourist attractions",
            radius=20000,  # 20km radius for broad coverage
            place_id=destination_place_id,  # Use place_id if available
        )
        pre_flight_count = len(pre_flight_venues)
        print(f"[Pre-flight] Found {pre_flight_count} venues in exploratory search")

        if pre_flight_count < 20:  # Doubled from 10 to 20
            # Impossible destination (e.g., North Korea, conflict zones)
            raise HTTPException(
                status_code=400,
                detail=(
                    f"We couldn't find enough activities in {destination} to create a quality itinerary. "
                    "This location may have limited tourism infrastructure or data availability. "
                    "Please try a different destination, reduce your trip duration, or select a nearby major city."
                ),
            )
        elif pre_flight_count < 60:  # Doubled from 30 to 60
            # Marginal destination - warn but proceed
            warning_msg = (
                f"Limited activities found for {destination}. "
                "Consider reducing your trip duration or selecting a nearby major city for better results."
            )
            warnings.append(warning_msg)
            print(
                f"[Pre-flight] WARNING: Limited data for {destination}. "
                "Itinerary quality may be affected."
            )
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Pre-flight] Error during feasibility check: {e}")
        # Continue anyway - main search might still succeed

    # --- ADAPTIVE CANDIDATE POOL ---
    # Bigger pool for longer trips, scaled by pace
    num_days = len(day_list)

    # Base multiplier by pace
    if pace_style <= 33:
        buffer_multiplier = 2.5  # Relaxed: need fewer options but want quality
    elif pace_style <= 66:
        buffer_multiplier = 3.0  # Moderate: balanced
    else:
        buffer_multiplier = 3.5  # Energetic: need more options to fill packed days

    # Calculate target with adaptive bounds
    base_target = int(total_needed * buffer_multiplier)

    # Adaptive min/max based on trip length
    if num_days >= 6:
        # Long trips: need significantly more headroom
        min_candidates = 120
        max_candidates = 440  # Doubled from 220
    elif num_days >= 4:
        # Mid-length trips
        min_candidates = 80
        max_candidates = 360  # Doubled from 180
    else:
        # Short trips
        min_candidates = 50
        max_candidates = 300  # Doubled from 150

    max_results = max(min_candidates, min(base_target, max_candidates))
    print(
        f"[Adaptive Pool] Days: {num_days}, Total needed: {total_needed}, "
        f"Target candidates: {max_results}"
    )

    # --- PASS A: STRICT SEARCH (interests + extracted queries + photos) ---
    print("[Pass A] Searching with interests + extracted queries + photo requirement...")

    # Merge interests with extracted search queries
    all_search_queries = interests.copy()
    if extracted_from_other["search_queries"]:
        all_search_queries.extend(extracted_from_other["search_queries"])
        print(
            f"[Pass A] Added {len(extracted_from_other['search_queries'])} extracted search queries"
        )

    candidates = places_service.search_by_preferences(
        destination=destination,
        user_interests=interests,  # Keep original interests for mapping
        budget_style=budget_style,
        max_results=max_results,
        require_photo=True,
        pace_style=pace_style,
        extracted_queries=extracted_from_other["search_queries"],  # NEW: Pass extracted queries
        extracted_place_types=extracted_from_other["place_types"],  # NEW: Pass extracted types
        place_id=destination_place_id,  # Use place_id if available
        max_pages=3,  # Increased from default 1 to fetch 3x more results
    )
    pass_a_count = len(candidates)
    print(f"[Pass A] Found {pass_a_count} candidates")

    # --- PASS B: BROADEN IF NEEDED ---
    if pass_a_count < total_needed * 2:
        print(
            f"[Pass B] Insufficient candidates ({pass_a_count} < {total_needed * 2}). "
            "Broadening search..."
        )

        # Calculate how many venues Pass B needs to find
        pass_b_max = max(
            max_results - pass_a_count,
            total_needed * 3,  # Ensure we search for at least 3x what we need
        )

        # Track seen place IDs to avoid duplicates
        seen_ids = {v["place_id"] for v in candidates}

        # Execute Pass B using semantic category matching
        broader_candidates = _pass_b(
            destination=destination,
            destination_place_id=destination_place_id,
            budget_style=budget_style,
            pace_style=pace_style,
            pass_b_max=pass_b_max,
            seen_ids=seen_ids,
            selected_interests=interests,
            other_interests_texts=other_interests_texts,
            vibe_notes=vibe_notes,
            payload_notes=(payload.notes if hasattr(payload, "notes") else None),
            trip_type=trip_type,
        )

        # Add unique results from Pass B
        added_count = 0
        for venue in broader_candidates:
            if venue["place_id"] not in seen_ids:
                candidates.append(venue)
                seen_ids.add(venue["place_id"])
                added_count += 1
                if len(candidates) >= max_results:
                    break

        print(f"[Pass B] Added {added_count} venues. Total: {len(candidates)}")

    # --- LOCATION VALIDATION ---
    # Filter out venues that are clearly not in the destination
    from app.core.geo_utils import haversine_distance

    def extract_city_country(dest: str) -> tuple[str, str]:
        """Extract city and country from destination string."""
        if not dest:
            return "", ""
        parts = dest.split(",")
        city = parts[0].strip() if parts else ""
        country = parts[-1].strip() if len(parts) > 1 else ""
        return city, country

    def is_valid_location(
        venue: dict[str, Any],
        destination_city: str,
        destination_country: str,
        destination_lat: float | None,
        destination_lng: float | None,
        max_distance_km: float = 15.0,
    ) -> bool:
        """
        Validate that a venue is actually in the destination location.

        Checks:
        1. Address contains city name or country
        2. Distance from destination center (if coordinates available)
        3. Country matches (if country specified)
        """
        address = (venue.get("address") or "").lower()
        venue_lat = venue.get("lat")
        venue_lng = venue.get("lng")

        # Check 1: Address validation
        city_lower = destination_city.lower()
        country_lower = destination_country.lower()

        # Must contain city name OR country in address
        address_valid = False
        if city_lower and city_lower in address:
            address_valid = True
        elif country_lower and country_lower in address:
            address_valid = True

        # If no city/country extracted, skip address check
        if not city_lower and not country_lower:
            address_valid = True

        # Check 2: Country validation (strict if country specified)
        country_valid = True
        if country_lower:
            # Check if address contains wrong country indicators
            wrong_countries = []
            if country_lower not in ["usa", "us", "united states"]:
                wrong_countries.extend(["united states", " usa", ", usa", " u.s.a"])
            if country_lower not in ["uk", "united kingdom", "england"]:
                wrong_countries.extend(["united kingdom", " uk", ", uk", " england"])

            # If address contains wrong country, reject
            for wrong_country in wrong_countries:
                if wrong_country.lower() in address:
                    country_valid = False
                    break

        # Check 3: Distance validation (if coordinates available)
        distance_valid = True
        if destination_lat and destination_lng and venue_lat and venue_lng:
            distance = haversine_distance(destination_lat, destination_lng, venue_lat, venue_lng)
            if distance > max_distance_km:
                distance_valid = False

        # All checks must pass
        return address_valid and country_valid and distance_valid

    # Get destination coordinates for distance validation
    destination_city, destination_country = extract_city_country(destination)
    destination_coords = None
    if destination_place_id:
        # Use Place Details to get exact coordinates
        try:
            place_details = places_service.get_place_details(destination_place_id)
            if place_details and place_details.get("lat") and place_details.get("lng"):
                destination_coords = (
                    place_details["lat"],
                    place_details["lng"],
                )
        except Exception as e:
            print(f"[LocationValidation] Failed to get destination coords: {e}")
    else:
        # Fallback to geocoding
        try:
            coords = places_service.geocode_location(destination)
            if coords:
                destination_coords = (coords["lat"], coords["lng"])
        except Exception as e:
            print(f"[LocationValidation] Failed to geocode destination: {e}")

    # Filter candidates by location
    original_count = len(candidates)
    destination_lat = destination_coords[0] if destination_coords else None
    destination_lng = destination_coords[1] if destination_coords else None

    filtered_candidates = []
    invalid_count = 0
    for venue in candidates:
        if is_valid_location(
            venue,
            destination_city,
            destination_country,
            destination_lat,
            destination_lng,
        ):
            filtered_candidates.append(venue)
        else:
            invalid_count += 1

    candidates = filtered_candidates
    if invalid_count > 0:
        print(
            f"[LocationValidation] Filtered out {invalid_count} invalid venues "
            f"({original_count} -> {len(candidates)})"
        )

    # --- POST-FETCH FEASIBILITY CHECK ---
    # More stringent threshold based on pace
    if pace_style <= 33:
        min_threshold = num_days * 2.5
    elif pace_style <= 66:
        min_threshold = num_days * 3.0
    else:
        min_threshold = num_days * 3.5

    if len(candidates) < min_threshold:
        # Provide helpful error based on what we found
        if pass_a_count > 0 and pass_a_count < 30:
            detail = (
                f"We found some activities in {destination}, but not enough for a quality "
                f"{num_days}-day itinerary. Try a shorter trip (2-4 days) or explore nearby cities."
            )
        elif len(candidates) > 50:
            detail = (
                f"We found activities in {destination}, but not enough meet our quality standards "
                "for a complete itinerary. Try a different destination or a shorter trip duration."
            )
        else:
            detail = (
                f"We couldn't find enough activities in {destination} to create a quality itinerary. "
                "Try reducing your trip duration or selecting a nearby major city."
            )

        raise HTTPException(status_code=400, detail=detail)

    # Scoring helpers
    def price_fit_score(price_level: int | None) -> float:
        if price_level is None:
            return 0.5
        target_levels = get_budget_price_levels(budget_style)
        return 1.0 if price_level in target_levels else 0.5

    def popularity_score(rating: float | None) -> float:
        if not rating:
            return 0.5
        return max(0.0, min(1.0, (rating - 3.5) / 1.5))  # 3.5→0, 5.0→1

    # Build interest mapping for scoring
    from app.core.itinerary_planner import map_interests_to_place_types

    interest_mapping = {}
    for interest in interests:
        queries = map_interests_to_place_types([interest])
        if queries:
            interest_mapping[interest] = queries[0]

    def keyword_match_score(
        venue: dict[str, Any],
        selected_interests: list[str],
        extracted_keywords: list[str],
        interest_mapping: dict[str, str],
    ) -> float:
        """
        Calculate keyword-based matching score (fallback/complement to semantic).

        Returns:
            Score between 0.0 and 1.0
        """
        venue_name = (venue.get("name") or "").lower()
        venue_types = [t.lower() for t in (venue.get("types") or [])]
        venue_text = venue_name + " " + " ".join(venue_types)

        score = 0.0
        matches = 0

        # Check against selected_interests mapping
        for interest in selected_interests:
            if interest in interest_mapping:
                query_terms = interest_mapping[interest].lower().split()
                # Check if any query term appears in venue
                if any(term in venue_text for term in query_terms):
                    matches += 1

        # Normalize: 0-1 based on number of interests matched
        if selected_interests:
            score = min(1.0, matches / len(selected_interests))

        # Boost from extracted keywords (from other_interests/vibe_notes)
        if extracted_keywords:
            keyword_matches = sum(1 for kw in extracted_keywords if kw.lower() in venue_text)
            keyword_score = min(0.3, keyword_matches / len(extracted_keywords) * 0.3)
            score += keyword_score

        return min(1.0, score)  # Cap at 1.0

    def interest_match_score(
        venue: dict[str, Any],
        selected_interests: list[str],
        extracted_keywords: list[str],
        interest_mapping: dict[str, str],
        semantic_score: float | None = None,
    ) -> float:
        """
        Score how well a venue matches user's selected interests.
        Uses hybrid scoring: combines semantic and keyword matching.

        Args:
            venue: Venue dictionary
            selected_interests: List of user's selected interests
            extracted_keywords: List of extracted keywords
            interest_mapping: Mapping of interests to query terms
            semantic_score: Pre-computed semantic score (if available)

        Returns:
            Score between 0.0 and 1.0
        """
        # Calculate keyword score
        keyword_score = keyword_match_score(
            venue, selected_interests, extracted_keywords, interest_mapping
        )

        # If semantic score is provided, use hybrid scoring
        if semantic_score is not None and semantic_score > 0.0:
            # Hybrid: combine semantic (70%) and keyword (30%)
            # Semantic captures meaning, keyword captures exact matches
            hybrid_score = 0.7 * semantic_score + 0.3 * keyword_score
            return min(1.0, hybrid_score)

        # Fallback to keyword only
        return keyword_score

    # Use only extracted keywords for boost (no hardcoded terms)
    # This ensures we only boost venues based on user preferences, not generic terms
    def notes_boost(v: dict[str, Any]) -> float:
        """
        Boost venues that match extracted keywords or notes_text.
        No hardcoded generic terms to avoid boosting venues globally.
        """
        text = (v.get("name") or "") + " " + ((v.get("types") and " ".join(v.get("types"))) or "")
        text = text.lower()

        # Reduced boost weight since we now have interest_match_score
        boost_val = 0.15 if len(candidates) >= 100 else 0.1

        # Only check extracted keywords and notes_text (user-provided)
        boost_terms_to_check = []
        if all_extracted_keywords:
            boost_terms_to_check.extend([k.lower() for k in all_extracted_keywords[:10]])
        if notes_text:
            boost_terms_to_check.extend(notes_text.split())

        # Only boost if there are actual user-provided terms
        if not boost_terms_to_check:
            return 0.0

        return boost_val if any(t in text for t in boost_terms_to_check) else 0.0

    # Batch compute semantic scores for all venues (much faster!)
    semantic_scores: list[float] | None = None
    try:
        from app.core.semantic_matcher import get_semantic_matcher

        matcher = get_semantic_matcher()
        if matcher.is_available():
            print(
                f"[InterestMatch] Computing semantic scores for {len(candidates)} venues in batch..."
            )
            semantic_scores = matcher.match_interests_batch(
                candidates, interests, all_extracted_keywords
            )
            print(f"[InterestMatch] Batch semantic matching completed")
        else:
            print("[InterestMatch] Semantic matching not available, using keyword matching only")
    except Exception as e:
        print(f"[InterestMatch] Semantic matching failed: {e}")
        print("[InterestMatch] Falling back to keyword matching only")

    # Score each candidate with updated weights
    scored: list[dict[str, Any]] = []
    for idx, v in enumerate(candidates):
        s = 0.0

        # Updated weights: more emphasis on interest matching
        s += 0.35 * popularity_score(v.get("rating"))  # Reduced from 0.5
        s += 0.25 * price_fit_score(v.get("price_level"))  # Reduced from 0.3
        s += 0.15 * (1.0 if v.get("photo_reference") else 0.3)  # Reduced from 0.2

        # NEW: Interest match score (25% of total) - hybrid semantic + keyword
        semantic_score = semantic_scores[idx] if semantic_scores else None
        interest_score = interest_match_score(
            v, interests, all_extracted_keywords, interest_mapping, semantic_score
        )
        s += 0.25 * interest_score

        # Existing notes boost (reduced weight)
        s += notes_boost(v)

        scored.append({"venue": v, "score": s})

    # Sort by score and enforce uniqueness & diversity
    scored.sort(key=lambda x: x["score"], reverse=True)

    chosen: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_types: dict[str, int] = {}

    def type_key(vtypes: list[str]):
        return vtypes[0] if vtypes else "other"

    # Initial diversity cap (will relax if needed)
    diversity_cap = max(4, total_needed // 3)
    print(f"[Diversity] Initial type cap: {diversity_cap}")

    # First pass: respect diversity cap
    for item in scored:
        v = item["venue"]
        if v["place_id"] in seen_ids:
            continue
        tkey = type_key(v.get("types", []))
        if seen_types.get(tkey, 0) >= diversity_cap:
            continue
        chosen.append(v)
        seen_ids.add(v["place_id"])
        seen_types[tkey] = seen_types.get(tkey, 0) + 1
        if len(chosen) >= total_needed:
            break

    # Second pass: relax diversity cap if we're short
    if len(chosen) < total_needed:
        print(f"[Diversity] Relaxing cap to fill remaining slots ({len(chosen)}/{total_needed})")
        relaxed_cap = diversity_cap + 2  # Allow +2 more per type
        for item in scored:
            v = item["venue"]
            if v["place_id"] in seen_ids:
                continue
            tkey = type_key(v.get("types", []))
            if seen_types.get(tkey, 0) >= relaxed_cap:
                continue
            chosen.append(v)
            seen_ids.add(v["place_id"])
            seen_types[tkey] = seen_types.get(tkey, 0) + 1
            if len(chosen) >= total_needed:
                break

    # Third pass: if still short, take best remaining regardless of type
    if len(chosen) < total_needed:
        print(
            f"[Diversity] Final pass: adding best remaining venues ({len(chosen)}/{total_needed})"
        )
        for item in scored:
            v = item["venue"]
            if v["place_id"] not in seen_ids:
                chosen.append(v)
                seen_ids.add(v["place_id"])
                if len(chosen) >= total_needed:
                    break

    print(f"[Selection] Chose {len(chosen)} venues from {len(candidates)} candidates")

    # Fetch opening hours for chosen venues
    print("[OpeningHours] Fetching opening hours for selected venues...")
    for v in chosen:
        if v.get("place_id"):
            details = places_service.get_place_details(v["place_id"])
            if details and details.get("opening_hours"):
                v["opening_hours"] = details["opening_hours"]
                print(f"[OpeningHours] Fetched hours for {v.get('name')}")
            else:
                v["opening_hours"] = []

    # Create opening hours cache (parse once per venue)
    opening_hours_cache: dict[str, dict[str, dict[str, str | None]]] = {}
    from app.core.opening_hours_utils import parse_opening_hours

    def get_parsed_opening_hours(
        place_id: str | None, venue_data: dict[str, Any] | None
    ) -> dict[str, dict[str, str | None]] | None:
        """Get parsed opening hours, using cache if available."""
        if not place_id:
            return None

        if place_id in opening_hours_cache:
            return opening_hours_cache[place_id]

        if venue_data:
            weekday_text = venue_data.get("opening_hours", [])
            if weekday_text:
                parsed = parse_opening_hours(weekday_text)
                opening_hours_cache[place_id] = parsed
                return parsed

        return None

    # Distribute venues across days with category diversity
    print("[Diversity] Distributing venues across days with category balance...")
    from app.core.activity_diversity import distribute_venues_with_diversity

    # Calculate target activities per day
    target_activities_per_day = []
    for plan in daily_plan:
        target_n = (plan["min_activities"] + plan["max_activities"]) // 2
        target_activities_per_day.append(target_n)

    # Use diversity-aware distribution
    days_venues = distribute_venues_with_diversity(
        chosen,
        num_days=len(day_list),
        activities_per_day=target_activities_per_day,
        pace_style=pace_style,
    )

    # Build ItineraryDocument from distributed venues
    days: list[Day] = []

    for i, d in enumerate(day_list):
        day_venues = days_venues[i]
        activities: list[Activity] = []

        for v in day_venues:
            # assign simple timeslots (will be refined by LLM)
            slot = ["10:00 AM", "1:30 PM", "4:00 PM", "7:00 PM", "9:00 PM"][len(activities) % 5]
            img = None
            if v.get("photo_reference"):
                url = places_service.get_proxy_photo_url(v["photo_reference"], base_url) or None
                img = url  # Use string directly (can be relative or absolute)
            activities.append(
                Activity(
                    time=slot,
                    title=v.get("name") or "Activity",
                    location=v.get("address") or destination,
                    description="",
                    image=img,
                    place_id=v.get("place_id"),
                )
            )
        days.append(
            Day(
                date=d.strftime("%A, %B %d"),
                activities=activities,
            )
        )

    # Log final distribution
    for i, day in enumerate(days):
        print(f"[Day {i+1}] {len(day.activities)} activities assigned")

    # Apply LLM-based timing to each day's activities
    print("[Timing] Generating realistic activity times with LLM...")
    try:
        from app.core.llm_provider import LLMProvider
        from app.core.settings import get_settings

        settings = get_settings()
        provider = LLMProvider(model=settings.aisuite_model)

        for day_idx, day in enumerate(days):
            if not day.activities:
                continue

            # Build activity context with types, locations, opening hours, and distances
            activity_context = []
            for idx, act in enumerate(day.activities):
                # Extract venue info
                venue_type = "general"
                venue_hours = None
                venue_distance_to_next = None

                if hasattr(act, "place_id") and act.place_id:
                    # Find the original venue to get types, opening hours, and distance
                    for v in chosen:
                        if v.get("place_id") == act.place_id:
                            types = v.get("types", [])
                            if types:
                                venue_type = types[0].replace("_", " ")
                            venue_hours = v.get("opening_hours", [])
                            break

                # Get distance to next activity (if available)
                if idx < len(day.activities) - 1:
                    # Check if distance is already calculated (from previous logic)
                    if hasattr(act, "distance_to_next") and act.distance_to_next:
                        venue_distance_to_next = act.distance_to_next

                # Build context string with opening hours
                context_str = (
                    f"{idx+1}. {act.title} ({venue_type}) at {act.location or destination}"
                )

                if venue_hours:
                    # Extract hours for the current day
                    day_name = day.date.split(",")[0]  # e.g., "Monday" from "Monday, January 1"
                    relevant_hours = [h for h in venue_hours if day_name in h]
                    if relevant_hours:
                        context_str += f" | Hours: {relevant_hours[0]}"

                if venue_distance_to_next:
                    from app.core.travel_time_utils import estimate_travel_time

                    travel_mins = estimate_travel_time(venue_distance_to_next)
                    context_str += (
                        f" | {venue_distance_to_next}km to next ({travel_mins}min travel)"
                    )

                activity_context.append(context_str)

            # Interpret schedule preference for timing guidance (3 profiles)
            if schedule_style <= 33:
                schedule_guidance = (
                    "EARLY BIRD: Start first activity 7:00-8:00 AM, end day by 9:00 PM"
                )
            elif schedule_style <= 66:
                schedule_guidance = (
                    "BALANCED: Start first activity 9:00-10:00 AM, end day by 10:00 PM"
                )
            else:
                schedule_guidance = "NIGHT OWL: Start first activity 10:00-11:00 AM, end day around 11:00 PM-midnight"

            timing_prompt = {
                "role": "system",
                "content": (
                    "You are a travel itinerary timing optimizer. Given a list of activities for a single day, "
                    "assign realistic start times considering:\n\n"
                    "IMPORTANT RULES:\n"
                    "1. RESPECT ACTUAL VENUE HOURS: Each activity shows its actual operating hours (if available). "
                    "Schedule activities ONLY during their open hours.\n"
                    "2. ACCOUNT FOR TRAVEL TIME: Travel time and distance to the next activity are provided. "
                    "Ensure next activity starts AFTER current activity ends + travel time + small buffer.\n"
                    "3. ESTIMATE ACTIVITY DURATION: Museums/attractions (2-3h), meals (1-2h), cafes (45min-1h), "
                    "bars/nightlife (2-3h), parks (1-2h), shopping (1-2h).\n"
                    "4. NATURAL PACING: Allow 10-15min buffer between activities for breaks/transitions.\n\n"
                    f"SCHEDULE PREFERENCE: {schedule_guidance}\n"
                    "Shift activities earlier/later within venue hours based on this preference.\n\n"
                    "Return ONLY a JSON array of time strings in 12-hour format (e.g., ['9:00 AM', '12:30 PM', '3:00 PM']).\n"
                    "The array must have exactly the same number of times as activities provided."
                ),
            }

            timing_user = {
                "role": "user",
                "content": f"Day {day_idx+1} activities:\n" + "\n".join(activity_context),
            }

            timing_response = provider.chat(messages=[timing_prompt, timing_user], temperature=0.3)

            # Parse timing response
            print(f"[Timing Debug] Raw LLM response: {timing_response[:300]}")

            timing_text = timing_response.strip()

            if not timing_text:
                print("[Timing] Empty response from LLM")
                raise ValueError("Empty LLM response")

            # Remove markdown code fences
            if timing_text.startswith("```"):
                lines = timing_text.split("\n")
                timing_text = "\n".join([line for line in lines if not line.startswith("```")])

            # Try to extract JSON array from text
            # Look for [...] pattern
            match = re.search(r"\[.*?\]", timing_text, re.DOTALL)
            if match:
                timing_text = match.group(0)
            else:
                print(f"[Timing] No JSON array found in response: {timing_text[:200]}")
                raise ValueError("No JSON array in response")

            # LLM might return Python list with single quotes - convert to JSON
            timing_text = timing_text.replace("'", '"')

            print(f"[Timing Debug] Extracted JSON: {timing_text[:200]}")
            # Parse JSON (json is imported at top level)
            try:
                times = json.loads(timing_text)
            except ValueError as e:
                # json.JSONDecodeError is a subclass of ValueError
                print(f"[Timing] JSON decode error: {e}")
                raise ValueError(f"Invalid JSON format: {e}")

            # Validate and apply times with opening hours check
            if isinstance(times, list) and len(times) == len(day.activities):
                from app.core.opening_hours_utils import (
                    adjust_time_to_opening_hours,
                    get_default_hours_by_type,
                    is_venue_open_at_time,
                )

                day_name = day.date.split(",")[0]  # Extract day name (e.g., "Monday")

                for idx, time_str in enumerate(times):
                    act = day.activities[idx]
                    # Find venue opening hours (using cache)
                    if act.place_id:
                        for v in chosen:
                            if v.get("place_id") == act.place_id:
                                # Use cached parsed hours if available
                                parsed_hours = get_parsed_opening_hours(act.place_id, v)

                                if parsed_hours:
                                    is_open, reason = is_venue_open_at_time(
                                        parsed_hours, day_name, time_str
                                    )

                                    if not is_open:
                                        # Adjust time to fit opening hours
                                        adjusted_time = adjust_time_to_opening_hours(
                                            time_str, parsed_hours, day_name
                                        )
                                        print(
                                            f"[OpeningHours] Adjusted '{act.title}' from {time_str} to {adjusted_time}: {reason}"
                                        )
                                        time_str = adjusted_time
                                else:
                                    # No opening hours data - use type-based defaults
                                    default_hours = get_default_hours_by_type(v.get("types", []))
                                    is_open, reason = is_venue_open_at_time(
                                        default_hours, day_name, time_str
                                    )

                                    if not is_open:
                                        adjusted_time = adjust_time_to_opening_hours(
                                            time_str, default_hours, day_name
                                        )
                                        print(
                                            f"[OpeningHours] Adjusted '{act.title}' using defaults from {time_str} to {adjusted_time}"
                                        )
                                        time_str = adjusted_time
                                break

                    act.time = time_str

                print(
                    f"[Day {day_idx+1}] Applied {len(times)} times (with opening hours validation)"
                )

                # Optimize times: sort chronologically and adjust for travel constraints
                _optimize_day_times(day, chosen, opening_hours_cache, pace_style)
            else:
                print(
                    f"[Day {day_idx+1}] WARNING: LLM returned invalid timing ({len(times)} vs {len(day.activities)})"
                )
                # Fallback to rule-based times with opening hours validation
                from app.core.opening_hours_utils import (
                    adjust_time_to_opening_hours,
                    get_default_hours_by_type,
                    parse_opening_hours,
                )

                day_name = day.date.split(",")[0]

                for idx, act in enumerate(day.activities):
                    fallback_slots = [
                        "9:00 AM",
                        "12:00 PM",
                        "3:00 PM",
                        "6:00 PM",
                        "8:30 PM",
                    ]
                    time_str = fallback_slots[idx % len(fallback_slots)]

                    # Validate against opening hours (using cache)
                    if act.place_id:
                        for v in chosen:
                            if v.get("place_id") == act.place_id:
                                # Use cached parsed hours if available
                                parsed_hours = get_parsed_opening_hours(act.place_id, v)
                                if parsed_hours:
                                    time_str = adjust_time_to_opening_hours(
                                        time_str, parsed_hours, day_name
                                    )
                                else:
                                    default_hours = get_default_hours_by_type(v.get("types", []))
                                    time_str = adjust_time_to_opening_hours(
                                        time_str, default_hours, day_name
                                    )
                                break

                    act.time = time_str

                # Optimize times: sort chronologically and adjust for travel constraints
                _optimize_day_times(day, chosen, opening_hours_cache, pace_style)

    except Exception as e:
        print(f"[Timing] Error generating times with LLM: {e}")
        # Fallback: assign rule-based times with opening hours validation
        from app.core.opening_hours_utils import (
            adjust_time_to_opening_hours,
            get_default_hours_by_type,
            parse_opening_hours,
        )

        for day in days:
            day_name = day.date.split(",")[0]

            for idx, act in enumerate(day.activities):
                fallback_slots = [
                    "9:00 AM",
                    "12:00 PM",
                    "3:00 PM",
                    "6:00 PM",
                    "8:30 PM",
                ]
                time_str = fallback_slots[idx % len(fallback_slots)]

                # Validate against opening hours (using cache)
                if act.place_id:
                    for v in chosen:
                        if v.get("place_id") == act.place_id:
                            # Use cached parsed hours if available
                            parsed_hours = get_parsed_opening_hours(act.place_id, v)
                            if parsed_hours:
                                time_str = adjust_time_to_opening_hours(
                                    time_str, parsed_hours, day_name
                                )
                            else:
                                default_hours = get_default_hours_by_type(v.get("types", []))
                                time_str = adjust_time_to_opening_hours(
                                    time_str, default_hours, day_name
                                )
                            break

                act.time = time_str

            # Optimize times: sort chronologically and adjust for travel constraints
            _optimize_day_times(day, chosen, opening_hours_cache, pace_style)

    # Calculate distances and validate timing with travel time
    print("[Distance] Calculating distances and validating travel time between activities...")
    from app.core.travel_time_utils import (
        add_minutes_to_time,
        estimate_activity_duration,
        estimate_travel_time,
    )

    for day_idx, day in enumerate(days):
        if len(day.activities) < 2:
            continue

        for idx in range(len(day.activities) - 1):
            current_act = day.activities[idx]
            next_act = day.activities[idx + 1]

            # Find lat/lng for both activities from chosen venues
            current_coords = None
            next_coords = None
            current_venue_types = []

            if current_act.place_id:
                for v in chosen:
                    if v.get("place_id") == current_act.place_id:
                        if v.get("lat") is not None and v.get("lng") is not None:
                            current_coords = (v["lat"], v["lng"])
                        current_venue_types = v.get("types", [])
                        break

            if next_act.place_id:
                for v in chosen:
                    if v.get("place_id") == next_act.place_id:
                        if v.get("lat") is not None and v.get("lng") is not None:
                            next_coords = (v["lat"], v["lng"])
                        break

            # Calculate distance if we have both coordinates
            if current_coords and next_coords:
                distance_km = haversine_distance(
                    current_coords[0], current_coords[1], next_coords[0], next_coords[1]
                )
                # Round to 1 decimal place
                current_act.distance_to_next = round(distance_km, 1)

                # Validate timing: check if there's enough time between activities
                travel_mins = estimate_travel_time(distance_km)
                activity_duration = estimate_activity_duration(current_venue_types, pace_style)

                # Calculate expected end time of current activity
                expected_next_start = add_minutes_to_time(
                    current_act.time, activity_duration + travel_mins
                )

                print(
                    f"[Day {day_idx+1}] Activity {idx+1} → {idx+2}: {distance_km}km, "
                    f"{travel_mins}min travel, duration ~{activity_duration}min"
                )

        print(
            f"[Day {day_idx+1}] Calculated {len([a for a in day.activities if a.distance_to_next is not None])} distances"
        )

    # Generate personalized trip notes using LLM
    trip_notes = []
    try:
        from app.core.llm_provider import LLMProvider
        from app.core.settings import get_settings

        settings = get_settings()
        provider = LLMProvider(model=settings.aisuite_model)

        # Build context for notes generation
        notes_context = f"Destination: {destination}\n"
        notes_context += f"Trip Type: {trip_type}\n"
        notes_context += f"Duration: {len(day_list)} days\n"
        if interests:
            notes_context += f"Interests: {', '.join(interests[:5])}\n"

        notes_prompt = {
            "role": "system",
            "content": (
                "Generate 6-8 comprehensive, practical travel tips for this trip. "
                "Cover these essential categories (mix and match as relevant to the destination):\n"
                "1. Safety & Security - local safety tips, areas to avoid, emergency contacts\n"
                "2. Money & Payments - cash vs card, tipping customs, currency tips\n"
                "3. Local Customs & Etiquette - cultural norms, dress codes, behavior expectations\n"
                "4. Practical Logistics - transport, booking recommendations, best times to visit\n"
                "5. Weather & Packing - seasonal considerations, what to bring\n"
                "6. Communication - WiFi, SIM cards, language basics\n\n"
                "Make each tip specific to the destination, actionable, and genuinely useful. "
                "Return ONLY a JSON array of strings, no other text. "
                'Example: ["Tip 1", "Tip 2", "Tip 3"]'
            ),
        }

        notes_user = {"role": "user", "content": notes_context}

        notes_response = provider.chat(messages=[notes_prompt, notes_user], temperature=0.7)

        # Parse the JSON response
        # Try to extract JSON array from response
        # (json is already imported at top level)
        notes_text = notes_response.strip()
        if notes_text.startswith("```"):
            # Remove markdown code fences
            lines = notes_text.split("\n")
            notes_text = "\n".join([line for line in lines if not line.startswith("```")])

        trip_notes = json.loads(notes_text)

        # Validate it's a list
        if not isinstance(trip_notes, list):
            raise ValueError("Notes must be a list")

    except Exception as e:
        print(f"Error generating trip notes with LLM: {e}")
        # Fallback to generic notes
        trip_notes = [
            "Times are flexible—adjust based on opening hours and energy levels.",
            "Book popular restaurants in advance during peak seasons.",
            "Check venue closures and events the day before.",
        ]

    # Extract city name from destination for browser title
    # Format: "Paris, France" -> "Paris" or "Las Vegas" -> "Las Vegas"
    def extract_city(dest: str) -> str:
        """Extract city name from destination string (before comma)."""
        if not dest:
            return ""
        # Split by comma and take first part, trim whitespace
        parts = dest.split(",")
        city = parts[0].strip()
        return city

    city_name = extract_city(destination)

    # Build itinerary document (with optional group metadata)
    doc = ItineraryDocument(
        trip_name=trip_name,
        traveler_name=traveler_name,
        destination=destination,
        dates=f"{day_list[0].date()} - {day_list[-1].date()}",
        duration=duration or f"{len(day_list)} days",
        cover_image=None,
        days=days,
        notes=trip_notes,
        trip_type=trip_type if trip_type in ("solo", "group") else None,
        city=city_name if city_name else None,
    )

    # Attach group metadata when applicable
    if trip_type == "group":
        try:
            from app.core.schemas import GroupInfo, GroupParticipant

            group_participants: list[GroupParticipant] = []
            # Prefer invite participants if invite_id is present
            if invite_id:
                inv = repo.get_trip_invite(invite_id)
                if inv:
                    for p in inv.get("participants", []):
                        fn = p.get("first_name") or ""
                        ln = p.get("last_name") or ""
                        if fn or ln:
                            group_participants.append(GroupParticipant(first_name=fn, last_name=ln))
                    doc.group = GroupInfo(
                        invite_id=invite_id,
                        participants=group_participants,
                        collect_preferences=bool(inv.get("collect_preferences")),
                    )
                    # If preferences were collected, add a note for the template
                    if inv.get("collect_preferences"):
                        doc.notes.append(
                            "This itinerary reflects preferences collected from all participants."
                        )
            # If no invite provided, but participants are in payload, attach them
            elif not invite_id and payload_participants:
                # payload_participants is now a list of ParticipantName objects
                for p in payload_participants:
                    fn = p.first_name.strip()
                    ln = p.last_name.strip()
                    if fn or ln:
                        group_participants.append(GroupParticipant(first_name=fn, last_name=ln))
                if group_participants:
                    doc.group = GroupInfo(
                        invite_id=None,
                        participants=group_participants,
                        collect_preferences=False,
                    )
        except Exception:
            # Non-fatal: proceed without group metadata if anything fails
            pass

    # Add cover image using Unsplash (with caching)
    try:
        if cover_image_service:
            cover_image_url = cover_image_service.get_cover_image(destination, repo)
            if cover_image_url:
                doc.cover_image = cover_image_url
    except Exception as e:
        print(f"[CoverImage] Failed to get cover image: {e}")
        # Non-fatal: continue without cover image

    itn_id = repo.save_itinerary(doc, clerk_user_id=clerk_user_id)

    # Check if this is the user's first itinerary and send email
    try:
        # Get user synchronously (MongoDB find_one is sync)
        user_doc = repo.users_collection.find_one({"clerk_user_id": clerk_user_id})
        if user_doc:
            user_doc.pop("_id", None)
            from app.core.schemas import User

            # Ensure first_itinerary_email_sent exists (migration for existing users)
            if "first_itinerary_email_sent" not in user_doc:
                user_doc["first_itinerary_email_sent"] = False

            user = User(**{k: v for k, v in user_doc.items() if k != "hashed_password"})

            # Check if user hasn't received first itinerary email yet
            if not user.first_itinerary_email_sent:
                from app.core.email_service import email_service

                frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3456")
                itinerary_link = f"{frontend_url}/trips"

                # Format dates for email
                trip_dates = doc.dates

                # Extract first name
                first_name = user.first_name or user.email.split("@")[0].split(".")[0].title()

                # Send email
                email_service.send_first_itinerary_email(
                    recipient_email=user.email,
                    recipient_first_name=first_name,
                    destination=destination,
                    trip_name=trip_name,
                    trip_dates=trip_dates,
                    itinerary_link=itinerary_link,
                )

                # Mark email as sent in database
                repo.users_collection.update_one(
                    {"clerk_user_id": clerk_user_id},
                    {
                        "$set": {
                            "first_itinerary_email_sent": True,
                            "updated_at": datetime.utcnow(),
                        }
                    },
                )
                print(f"[Email] Sent first itinerary email to {user.email}")
    except Exception as e:
        print(f"[Email] Error sending first itinerary email: {e}")
        # Non-fatal: continue even if email fails

    # Update invite with itinerary_id if this is a group trip
    if invite_id:
        try:
            success = repo.update_invite_itinerary_id(invite_id, itn_id)
            if not success:
                print(f"Warning: Failed to update invite {invite_id} with itinerary_id {itn_id}")
        except Exception as e:
            print(f"Error updating invite with itinerary_id: {e}")
            # Non-fatal: continue even if invite update fails

    # Return itinerary with warnings if any
    result = repo.get_itinerary(itn_id) or {"id": itn_id}
    if warnings:
        result["warnings"] = warnings
    return result


@router.get("/user/me")
async def get_user_itineraries(
    current_user: User = Depends(get_current_user_from_clerk),
):
    """Get all itineraries for the authenticated user."""
    clerk_user_id = current_user.clerk_user_id
    itineraries = repo.get_user_itineraries(clerk_user_id)
    return {"itineraries": itineraries}


@router.get("/{itinerary_id}")
def get_itinerary(
    itinerary_id: str = Path(
        ...,
        min_length=1,
        max_length=50,
        pattern="^[a-zA-Z0-9_-]+$",
        description="Itinerary ID",
    ),
):
    data = repo.get_itinerary(itinerary_id)
    if not data:
        raise HTTPException(status_code=404, detail="not found")
    return data


@router.get("")
def list_itineraries():
    """List all itineraries."""
    all_itineraries = list(repo.itineraries_collection.find({}))
    # Remove MongoDB ObjectId from each document
    for itn in all_itineraries:
        itn.pop("_id", None)
    return {"itineraries": all_itineraries}


@router.post("")
def create_itinerary(doc: ItineraryDocument):
    itn_id = repo.save_itinerary(doc)
    data = repo.get_itinerary(itn_id)
    if not data:
        raise HTTPException(status_code=500, detail="failed to persist itinerary")
    return data


@router.delete("/{itinerary_id}")
async def delete_itinerary(
    itinerary_id: str = Path(
        ...,
        min_length=1,
        max_length=50,
        pattern="^[a-zA-Z0-9_-]+$",
        description="Itinerary ID",
    ),
    current_user: User = Depends(get_current_user_from_clerk),
):
    """Delete an itinerary by ID and cascade delete linked invites."""
    # Find all invites linked to this itinerary
    linked_invites = list(repo.trip_invites_collection.find({"itinerary_id": itinerary_id}))

    # Delete all linked invites
    if linked_invites:
        repo.trip_invites_collection.delete_many({"itinerary_id": itinerary_id})

    # Delete the itinerary
    success = repo.delete_itinerary(itinerary_id)
    if not success:
        raise HTTPException(status_code=404, detail="Itinerary not found")
    return {"message": "Itinerary deleted successfully"}


@router.get("/{itinerary_id}/invite")
async def get_itinerary_invite(
    itinerary_id: str = Path(
        ...,
        min_length=1,
        max_length=50,
        pattern="^[a-zA-Z0-9_-]+$",
        description="Itinerary ID",
    ),
    current_user: User = Depends(get_current_user_from_clerk),
):
    """Get the invite associated with an itinerary."""
    clerk_user_id = current_user.clerk_user_id

    # Get itinerary to verify ownership
    itinerary = repo.get_itinerary(itinerary_id)
    if not itinerary:
        raise HTTPException(status_code=404, detail="Itinerary not found")

    # Verify ownership
    if itinerary.get("clerk_user_id") != clerk_user_id:
        raise HTTPException(status_code=403, detail="Only the itinerary owner can access this")

    # Find invite linked to this itinerary
    invite = repo.trip_invites_collection.find_one({"itinerary_id": itinerary_id})
    if not invite:
        raise HTTPException(status_code=404, detail="No invite found for this itinerary")

    invite.pop("_id", None)  # Remove MongoDB ObjectId

    # Filter out organizer from participants
    participants = [p for p in invite.get("participants", []) if not p.get("is_organizer")]

    # Return all non-organizer participants (with or without emails)
    invite["participants"] = participants

    return invite


@router.patch("/{itinerary_id}/participants")
async def update_itinerary_participants(
    itinerary_id: str = Path(
        ...,
        min_length=1,
        max_length=50,
        pattern="^[a-zA-Z0-9_-]+$",
        description="Itinerary ID",
    ),
    participants_data: UpdateParticipantsRequest = Body(...),
    current_user: User = Depends(get_current_user_from_clerk),
):
    """Update participants list for an itinerary."""
    clerk_user_id = current_user.clerk_user_id

    # Get itinerary
    itinerary = repo.get_itinerary(itinerary_id)
    if not itinerary:
        raise HTTPException(status_code=404, detail="Itinerary not found")

    # Verify ownership
    if itinerary.get("clerk_user_id") != clerk_user_id:
        raise HTTPException(
            status_code=403, detail="Only the itinerary owner can update participants"
        )

    # Update the document's group participants
    document = itinerary.get("document", {})
    group_info = document.get("group")

    if not group_info:
        # Create group info if it doesn't exist
        group_info = {
            "participants": [],
            "invite_id": None,
            "collect_preferences": False,
        }

    # Parse participants from request
    participants_list = participants_data.participants
    group_participants = []

    for p in participants_list:
        group_participants.append(
            {
                "first_name": p.first_name,
                "last_name": p.last_name,
                "email": None,  # ParticipantName doesn't include email
                "email_sent": False,
                "email_sent_at": None,
            }
        )

    # Update group info
    group_info["participants"] = group_participants
    document["group"] = group_info

    # Update itinerary in database
    repo.itineraries_collection.update_one({"id": itinerary_id}, {"$set": {"document": document}})

    updated_itinerary = repo.get_itinerary(itinerary_id)
    return updated_itinerary


@router.post("/{itinerary_id}/share")
async def share_itinerary(
    itinerary_id: str = Path(
        ...,
        min_length=1,
        max_length=50,
        pattern="^[a-zA-Z0-9_-]+$",
        description="Itinerary ID",
    ),
    share_data: ShareItineraryRequest = Body(...),
    current_user: User = Depends(get_current_user_from_clerk),
):
    """Share an itinerary with participants by creating or updating an invite."""
    from datetime import datetime

    from app.core.email_service import send_trip_invite_email

    clerk_user_id = current_user.clerk_user_id

    # Get itinerary
    itinerary = repo.get_itinerary(itinerary_id)
    if not itinerary:
        raise HTTPException(status_code=404, detail="Itinerary not found")

    # Verify ownership
    if itinerary.get("clerk_user_id") != clerk_user_id:
        raise HTTPException(status_code=403, detail="Only the itinerary owner can share it")

    # Get user info
    user = await repo.get_user_by_clerk_id(clerk_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    document = itinerary.get("document", {})
    if not document:
        raise HTTPException(status_code=400, detail="Itinerary document is missing")

    destination = document.get("destination", "Unknown")
    trip_name = document.get("trip_name", "Group Trip")

    # Extract dates from itinerary
    dates_str = document.get("dates", "")
    # Parse dates (format: "YYYY-MM-DD - YYYY-MM-DD")
    date_parts = dates_str.split(" - ")
    date_range_start = date_parts[0].strip() if len(date_parts) > 0 else None
    date_range_end = date_parts[1].strip() if len(date_parts) > 1 else None

    # Get or create invite linked to this itinerary
    existing_invite = repo.trip_invites_collection.find_one({"itinerary_id": itinerary_id})

    if existing_invite:
        existing_invite.pop("_id", None)  # Remove MongoDB ObjectId
        invite_id = existing_invite["id"]

        # Update trip_name if it exists in itinerary document
        if trip_name and trip_name != existing_invite.get("trip_name"):
            repo.trip_invites_collection.update_one(
                {"id": invite_id},
                {
                    "$set": {
                        "trip_name": trip_name,
                        "updated_at": datetime.utcnow(),
                    }
                },
            )

        # Update existing invite with new participants
        participant_emails = share_data.participants
        organizer_name = share_data.get("organizer_name", user.first_name or "Trip Organizer")

        # Update participants in the invite
        participants = existing_invite.get("participants", [])

        # Add new participants if they don't exist
        existing_emails = {p["email"] for p in participants if p.get("email")}
        for email in participant_emails:
            if email not in existing_emails:
                # Find participant in itinerary group if exists
                group_participants = document.get("group", {}).get("participants", [])
                participant_info = next(
                    (p for p in group_participants if p.get("email") == email), None
                )

                repo.add_participant(
                    invite_id=invite_id,
                    email=email,
                    first_name=(participant_info.get("first_name", "") if participant_info else ""),
                    last_name=(participant_info.get("last_name", "") if participant_info else ""),
                )

        # Send emails to selected participants
        sent_count = 0
        failed_emails = []

        for email in participant_emails:
            try:
                # Find participant to get first_name
                updated_invite = repo.get_trip_invite(invite_id)
                participant = next(
                    (p for p in updated_invite.get("participants", []) if p.get("email") == email),
                    None,
                )
                recipient_first_name = (
                    participant.get("first_name", "").strip() if participant else None
                )

                send_trip_invite_email(
                    to_email=email,
                    invite_id=invite_id,
                    organizer_name=organizer_name,
                    trip_name=trip_name,
                    recipient_first_name=(recipient_first_name if recipient_first_name else None),
                )
                sent_count += 1
            except Exception as e:
                logger.error(f"Failed to send email to {email}: {e}", exc_info=True)
                failed_emails.append(email)

        # Mark invites as sent
        repo.mark_invites_sent(invite_id)

        return {
            "message": f"Itinerary shared with {sent_count} participant(s)",
            "invite_id": invite_id,
            "itinerary_id": itinerary_id,
            "sent_count": sent_count,
            "failed_count": len(failed_emails),
            "failed_emails": failed_emails,
        }
    else:
        # Create new invite
        invite_doc = repo.create_trip_invite(
            organizer_clerk_id=clerk_user_id,
            organizer_email=user.email,
            organizer_name=f"{user.first_name or ''} {user.last_name or ''}".strip() or None,
            trip_name=trip_name,
            destination=destination,
            date_range_start=date_range_start,
            date_range_end=date_range_end,
            collect_preferences=True,
            trip_type="group",
        )

        invite_id = invite_doc["id"]

        # Link invite to itinerary
        repo.update_invite_itinerary_id(invite_id, itinerary_id)

        # Add participants
        participant_emails = share_data.participants
        organizer_name = share_data.get("organizer_name", user.first_name or "Trip Organizer")

        group_participants = document.get("group", {}).get("participants", [])
        for email in participant_emails:
            participant_info = next(
                (p for p in group_participants if p.get("email") == email), None
            )

            repo.add_participant(
                invite_id=invite_id,
                email=email,
                first_name=(participant_info.get("first_name", "") if participant_info else ""),
                last_name=(participant_info.get("last_name", "") if participant_info else ""),
            )

        # Send emails
        sent_count = 0
        failed_emails = []

        for email in participant_emails:
            try:
                # Find participant to get first_name
                participant = next(
                    (
                        p
                        for p in repo.get_trip_invite(invite_id).get("participants", [])
                        if p.get("email") == email
                    ),
                    None,
                )
                recipient_first_name = (
                    participant.get("first_name", "").strip() if participant else None
                )

                send_trip_invite_email(
                    to_email=email,
                    invite_id=invite_id,
                    organizer_name=organizer_name,
                    trip_name=trip_name,
                    recipient_first_name=(recipient_first_name if recipient_first_name else None),
                )
                sent_count += 1
            except Exception as e:
                logger.error(f"Failed to send email to {email}: {e}", exc_info=True)
                failed_emails.append(email)

        # Mark invites as sent
        repo.mark_invites_sent(invite_id)

        return {
            "message": f"Itinerary shared with {sent_count} participant(s)",
            "invite_id": invite_id,
            "itinerary_id": itinerary_id,
            "sent_count": sent_count,
            "failed_count": len(failed_emails),
            "failed_emails": failed_emails,
        }
