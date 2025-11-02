import json
from typing import Any

from app.core.places_service import places_service
from app.core.repository import repo
from app.core.schemas import Activity, Day, ItineraryDocument
from fastapi import APIRouter, Header, HTTPException, Request

router = APIRouter(prefix="/itineraries", tags=["itineraries"])


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


@router.get("/sample", response_model=ItineraryDocument)
def get_sample_itinerary() -> ItineraryDocument:
    return ItineraryDocument(
        trip_name="Vegas Weekend",
        traveler_name="Sheriff",
        destination="Las Vegas",
        dates="March 15-17, 2025",
        duration="Three Day Weekend",
        cover_image=(
            "https://images.unsplash.com/"
            "photo-1683645012230-e3a3c1255434"
            "?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&q=80&w=1080"
        ),
        days=[
            Day(
                date="Friday, March 15",
                activities=[
                    Activity(
                        time="12:00 PM",
                        title="Arrival & Check-in",
                        location="Bellagio Hotel & Casino",
                        description=(
                            "Check into the Bellagio suite and enjoy fountain views."
                        ),
                        image=(
                            "https://images.unsplash.com/"
                            "photo-1683645012230-e3a3c1255434?crop=entropy&cs=tinysrgb"
                            "&fit=max&fm=jpg&q=80&w=1080"
                        ),
                    )
                ],
            ),
            Day(
                date="Saturday, March 16",
                activities=[
                    Activity(
                        time="10:00 AM",
                        title="Brunch at Bacchanal",
                        location="Caesars Palace",
                        description="Legendary buffet experience.",
                        image=(
                            "https://images.unsplash.com/"
                            "photo-1755862922067-8a0135afc1bb"
                            "?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&q=80&w=1080"
                        ),
                    )
                ],
            ),
        ],
        notes=[
            "Bring ID - required everywhere in Vegas",
            "Set gambling budget beforehand",
            "Stay hydrated - desert climate",
        ],
    )


# ----------------------------------------------
# New deterministic generator (no LLM selection)
# ----------------------------------------------
@router.post("/generate2", response_model=dict[str, Any])
def generate_itinerary_v2(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """
    Deterministic itinerary generation using weighted scoring over Google Places
    results plus user/group preferences. No LLM is used for venue selection.

    Expected payload: {
      trip_name, traveler_name, destination, dates ("YYYY-MM-DD - YYYY-MM-DD"),
      duration?, clerk_user_id?, trip_type? (solo|group), invite_id?, notes?, vibe_notes?
    }
    """
    from datetime import datetime, timedelta

    from app.core.itinerary_planner import (
        calculate_daily_activities,
        get_budget_price_levels,
    )
    from app.core.preference_aggregator import aggregate_preferences
    from pydantic import HttpUrl

    trip_name = payload.get("trip_name") or ""
    traveler_name = payload.get("traveler_name") or "Traveler"
    destination = payload.get("destination") or ""
    dates = payload.get("dates") or ""
    duration = payload.get("duration") or ""
    clerk_user_id = payload.get("clerk_user_id")
    trip_type = payload.get("trip_type", "solo")
    invite_id = payload.get("invite_id")
    payload_participants = (
        payload.get("participants") or []
    )  # optional [{first_name,last_name}]
    notes_text = (payload.get("notes") or "").lower()
    vibe_notes = payload.get("vibe_notes") or ""  # Optional context for generation

    # Get base URL for proxy photo URLs
    base_url = str(request.base_url).rstrip("/") if request else "http://localhost:8765"

    if not trip_name or not traveler_name or not destination or not dates:
        raise HTTPException(
            status_code=400,
            detail="trip_name, traveler_name, destination and dates are required",
        )

    # Parse dates → list of day strings
    try:
        parts = dates.split(" - ")
        if len(parts) != 2:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid date format. Expected 'YYYY-MM-DD - YYYY-MM-DD', got '{dates}'",
            )
        start_s, end_s = parts[0].strip(), parts[1].strip()
        start = datetime.fromisoformat(start_s)
        end = datetime.fromisoformat(end_s)
        if (end - start).days + 1 > 7:
            raise HTTPException(
                status_code=400, detail="Trip duration cannot exceed 7 days"
            )
        day_list = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid dates: {e!s}")

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
    schedule_style = (
        aggregated_prefs.get("schedule_style", 50) if aggregated_prefs else 50
    )
    interests = (
        aggregated_prefs.get("selected_interests", []) if aggregated_prefs else []
    )
    other_interests_texts = (
        aggregated_prefs.get("other_interests", []) if aggregated_prefs else []
    )

    # Extract structured info from other_interests using NLP
    from app.core.preference_extractor import extract_preferences_from_text

    extracted_from_other = {
        "search_queries": [],
        "place_types": [],
        "keywords": [],
        "preference_signals": {},
    }

    if other_interests_texts:
        # Combine all other_interests texts
        combined_text = " ".join(other_interests_texts)

        # Extract with context
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

    # Extract structured info from vibe_notes (solo trips only, not group)
    extracted_from_vibe = {
        "search_queries": [],
        "place_types": [],
        "keywords": [],
        "preference_signals": {},
    }

    if vibe_notes and trip_type == "solo":
        extracted_from_vibe = extract_preferences_from_text(
            vibe_notes,
            context={
                "destination": destination,
                "trip_type": trip_type,
                "selected_interests": interests,
            },
        )

        # Merge with other_interests extraction
        extracted_from_other["search_queries"].extend(
            extracted_from_vibe["search_queries"]
        )
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
    try:
        pre_flight_venues = places_service.search_places(
            location=destination,
            query="tourist attractions",
            radius=20000,  # 20km radius for broad coverage
        )
        pre_flight_count = len(pre_flight_venues)
        print(f"[Pre-flight] Found {pre_flight_count} venues in exploratory search")

        if pre_flight_count < 10:
            # Impossible destination (e.g., North Korea, conflict zones)
            raise HTTPException(
                status_code=400,
                detail=(
                    f"We couldn't find enough activities in {destination} to create an itinerary. "
                    "This location may not be suitable for travel planning due to limited tourism "
                    "infrastructure, travel restrictions, or data availability. "
                    "Please try a different destination."
                ),
            )
        elif pre_flight_count < 30:
            # Marginal destination - warn but proceed
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
        max_candidates = 220
    elif num_days >= 4:
        # Mid-length trips
        min_candidates = 80
        max_candidates = 180
    else:
        # Short trips
        min_candidates = 50
        max_candidates = 150

    max_results = max(min_candidates, min(base_target, max_candidates))
    print(
        f"[Adaptive Pool] Days: {num_days}, Total needed: {total_needed}, "
        f"Target candidates: {max_results}"
    )

    # --- PASS A: STRICT SEARCH (interests + extracted queries + photos) ---
    print(
        "[Pass A] Searching with interests + extracted queries + photo requirement..."
    )

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
        extracted_queries=extracted_from_other[
            "search_queries"
        ],  # NEW: Pass extracted queries
        extracted_place_types=extracted_from_other[
            "place_types"
        ],  # NEW: Pass extracted types
    )
    pass_a_count = len(candidates)
    print(f"[Pass A] Found {pass_a_count} candidates")

    # --- PASS B: BROADEN IF NEEDED ---
    if pass_a_count < total_needed * 2:
        print(
            f"[Pass B] Insufficient candidates ({pass_a_count} < {total_needed * 2}). "
            "Broadening search..."
        )

        # Broader search: no interest filter, relax photo requirement
        broader_types = [
            "tourist_attraction",
            "point_of_interest",
            "museum",
            "park",
            "shopping_mall",
            "restaurant",
            "cafe",
            "bar",
            "landmark",
            "art_gallery",
            "aquarium",
            "zoo",
            "amusement_park",
            "stadium",
            "theater",
            "casino",
            "night_club",
            "spa",
            "beach",
            "natural_feature",
            "church",
            "mosque",
            "temple",
        ]

        # Allow some venues without photos (up to 15%)
        broad_search_results = places_service.search_places(
            location=destination,
            query="things to do",
            radius=10000,
            allowed_types=broader_types,
        )

        # Add unique results from Pass B
        seen_ids = {v["place_id"] for v in candidates}
        added_count = 0
        for venue in broad_search_results:
            if venue["place_id"] not in seen_ids:
                candidates.append(venue)
                seen_ids.add(venue["place_id"])
                added_count += 1
                if len(candidates) >= max_results:
                    break

        print(f"[Pass B] Added {added_count} venues. Total: {len(candidates)}")

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
                f"We found activities in {destination}, but many lack photos or detailed information. "
                "We're working on improving coverage for this area. Try a different destination."
            )
        else:
            detail = (
                f"We couldn't find enough activities in {destination} to create a quality itinerary. "
                "Try another destination."
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
            keyword_matches = sum(
                1 for kw in extracted_keywords if kw.lower() in venue_text
            )
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

    note_boost_terms = [
        "museum",
        "coffee",
        "hike",
        "beach",
        "park",
        "landmark",
        "live music",
    ]

    # Add extracted keywords to boost terms
    if all_extracted_keywords:
        note_boost_terms.extend(
            all_extracted_keywords[:10]
        )  # Limit to 10 additional terms

    def notes_boost(v: dict[str, Any]) -> float:
        text = (
            (v.get("name") or "")
            + " "
            + ((v.get("types") and " ".join(v.get("types"))) or "")
        )
        text = text.lower()
        # Reduced boost weight since we now have interest_match_score
        # Check against both extracted keywords and legacy notes_text
        boost_val = 0.15 if len(candidates) >= 100 else 0.1
        boost_terms_to_check = note_boost_terms.copy()
        if notes_text:
            boost_terms_to_check.extend(notes_text.split())
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
            print(
                "[InterestMatch] Semantic matching not available, using keyword matching only"
            )
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
        print(
            f"[Diversity] Relaxing cap to fill remaining slots ({len(chosen)}/{total_needed})"
        )
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

    # Build ItineraryDocument with per-day backfill
    days: list[Day] = []
    idx = 0
    remaining_unassigned = [v for v in scored if v["venue"]["place_id"] not in seen_ids]

    for i, d in enumerate(day_list):
        plan = daily_plan[i]
        target_n = (plan["min_activities"] + plan["max_activities"]) // 2
        activities: list[Activity] = []

        # Primary assignment from chosen venues
        for j in range(target_n):
            if idx >= len(chosen):
                break
            v = chosen[idx]
            idx += 1
            # assign simple timeslots
            slot = ["10:00 AM", "1:30 PM", "4:00 PM", "7:00 PM", "9:00 PM"][j % 5]
            img = None
            if v.get("photo_reference"):
                url = (
                    places_service.get_proxy_photo_url(v["photo_reference"], base_url)
                    or None
                )
                img = HttpUrl(url) if url else None
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

        # Per-day backfill if short
        if len(activities) < plan["min_activities"]:
            shortfall = plan["min_activities"] - len(activities)
            print(f"[Day {i+1}] Backfilling {shortfall} activities")

            for _ in range(shortfall):
                if remaining_unassigned:
                    item = remaining_unassigned.pop(0)
                    v = item["venue"]
                    seen_ids.add(v["place_id"])

                    slot = ["10:00 AM", "1:30 PM", "4:00 PM", "7:00 PM", "9:00 PM"][
                        len(activities) % 5
                    ]
                    img = None
                    if v.get("photo_reference"):
                        url = (
                            places_service.get_proxy_photo_url(
                                v["photo_reference"], base_url
                            )
                            or None
                        )
                        img = HttpUrl(url) if url else None

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
                else:
                    # No more venues - this shouldn't happen given our checks, but log it
                    print(f"[Day {i+1}] WARNING: Ran out of venues for backfill")
                    break

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

            # Build activity context with types and locations
            activity_context = []
            for idx, act in enumerate(day.activities):
                # Extract primary venue type
                venue_type = "general"
                if hasattr(act, "place_id") and act.place_id:
                    # Find the original venue to get types
                    for v in chosen:
                        if v.get("place_id") == act.place_id:
                            types = v.get("types", [])
                            if types:
                                venue_type = types[0].replace("_", " ")
                            break

                activity_context.append(
                    f"{idx+1}. {act.title} ({venue_type}) at {act.location or destination}"
                )

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
                    "VENUE OPERATING HOURS (respect these constraints):\n"
                    "- Museums/Attractions: 9:00 AM - 5:00/6:00 PM\n"
                    "- Restaurants (lunch): 11:30 AM - 2:30 PM\n"
                    "- Restaurants (dinner): 5:00 PM - 10:00 PM\n"
                    "- Cafes/Breakfast: 7:00 AM - 11:00 AM\n"
                    "- Bars/Nightlife: 7:00 PM onwards\n"
                    "- Parks/Outdoor: Daylight hours (6:00 AM - sunset)\n"
                    "- Shopping: 10:00 AM - 8:00 PM\n\n"
                    "OTHER FACTORS:\n"
                    "- Typical activity duration (museums 2-3h, meals 1-2h, attractions 1-2h)\n"
                    "- Travel time between venues (assume 15-30min in same area)\n"
                    "- Natural pacing (avoid rushing, include breaks)\n\n"
                    f"SCHEDULE PREFERENCE: {schedule_guidance}\n"
                    "Shift activities earlier/later within realistic venue hours based on this preference.\n\n"
                    "Return ONLY a JSON array of time strings in 12-hour format (e.g., ['9:00 AM', '12:30 PM', '3:00 PM']).\n"
                    "The array must have exactly the same number of times as activities provided."
                ),
            }

            timing_user = {
                "role": "user",
                "content": f"Day {day_idx+1} activities:\n"
                + "\n".join(activity_context),
            }

            timing_response = provider.chat(
                messages=[timing_prompt, timing_user], temperature=0.3
            )

            # Parse timing response
            import re

            print(f"[Timing Debug] Raw LLM response: {timing_response[:300]}")

            timing_text = timing_response.strip()

            if not timing_text:
                print("[Timing] Empty response from LLM")
                raise ValueError("Empty LLM response")

            # Remove markdown code fences
            if timing_text.startswith("```"):
                lines = timing_text.split("\n")
                timing_text = "\n".join(
                    [line for line in lines if not line.startswith("```")]
                )

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

            # Validate and apply times
            if isinstance(times, list) and len(times) == len(day.activities):
                for idx, time_str in enumerate(times):
                    day.activities[idx].time = time_str
                print(f"[Day {day_idx+1}] Applied {len(times)} LLM-generated times")
            else:
                print(
                    f"[Day {day_idx+1}] WARNING: LLM returned invalid timing ({len(times)} vs {len(day.activities)})"
                )
                # Fallback to rule-based times
                for idx, act in enumerate(day.activities):
                    fallback_slots = [
                        "9:00 AM",
                        "12:00 PM",
                        "3:00 PM",
                        "6:00 PM",
                        "8:30 PM",
                    ]
                    act.time = fallback_slots[idx % len(fallback_slots)]

    except Exception as e:
        print(f"[Timing] Error generating times with LLM: {e}")
        # Fallback: assign rule-based times
        for day in days:
            for idx, act in enumerate(day.activities):
                fallback_slots = [
                    "9:00 AM",
                    "12:00 PM",
                    "3:00 PM",
                    "6:00 PM",
                    "8:30 PM",
                ]
                act.time = fallback_slots[idx % len(fallback_slots)]

    # Calculate distances between consecutive activities
    print("[Distance] Calculating distances between activities...")
    from app.core.geo_utils import haversine_distance

    for day_idx, day in enumerate(days):
        if len(day.activities) < 2:
            continue

        for idx in range(len(day.activities) - 1):
            current_act = day.activities[idx]
            next_act = day.activities[idx + 1]

            # Find lat/lng for both activities from chosen venues
            current_coords = None
            next_coords = None

            if current_act.place_id:
                for v in chosen:
                    if v.get("place_id") == current_act.place_id:
                        if v.get("lat") is not None and v.get("lng") is not None:
                            current_coords = (v["lat"], v["lng"])
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

        notes_response = provider.chat(
            messages=[notes_prompt, notes_user], temperature=0.7
        )

        # Parse the JSON response
        # Try to extract JSON array from response
        # (json is already imported at top level)
        notes_text = notes_response.strip()
        if notes_text.startswith("```"):
            # Remove markdown code fences
            lines = notes_text.split("\n")
            notes_text = "\n".join(
                [line for line in lines if not line.startswith("```")]
            )

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
                            group_participants.append(
                                GroupParticipant(first_name=fn, last_name=ln)
                            )
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
                for p in payload_participants:
                    fn = (p.get("first_name") or p.get("firstName") or "").strip()
                    ln = (p.get("last_name") or p.get("lastName") or "").strip()
                    if fn or ln:
                        group_participants.append(
                            GroupParticipant(first_name=fn, last_name=ln)
                        )
                if group_participants:
                    doc.group = GroupInfo(
                        invite_id=None,
                        participants=group_participants,
                        collect_preferences=False,
                    )
        except Exception:
            # Non-fatal: proceed without group metadata if anything fails
            pass

    # Add cover if possible
    try:
        cover_qs = [
            f"{destination} skyline",
            f"{destination} cityscape",
            f"{destination} landmark",
        ]
        for q in cover_qs:
            res = places_service.search_places(location=destination, query=q)
            if res and res[0].get("photo_reference"):
                url = places_service.get_proxy_photo_url(
                    res[0]["photo_reference"], base_url
                )
                if url:
                    doc.cover_image = HttpUrl(url)
                    break
    except Exception:
        pass

    itn_id = repo.save_itinerary(doc, clerk_user_id=clerk_user_id)

    # Update invite with itinerary_id if this is a group trip
    if invite_id:
        try:
            success = repo.update_invite_itinerary_id(invite_id, itn_id)
            if not success:
                print(
                    f"Warning: Failed to update invite {invite_id} with itinerary_id {itn_id}"
                )
        except Exception as e:
            print(f"Error updating invite with itinerary_id: {e}")
            # Non-fatal: continue even if invite update fails

    return repo.get_itinerary(itn_id) or {"id": itn_id}


@router.get("/user/{clerk_user_id}")
def get_user_itineraries(clerk_user_id: str):
    """Get all itineraries for a specific user."""
    itineraries = repo.get_user_itineraries(clerk_user_id)
    return {"itineraries": itineraries}


@router.get("/{itinerary_id}")
def get_itinerary(itinerary_id: str):
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
def delete_itinerary(itinerary_id: str):
    """Delete an itinerary by ID and cascade delete linked invites."""
    # Find all invites linked to this itinerary
    linked_invites = list(
        repo.trip_invites_collection.find({"itinerary_id": itinerary_id})
    )

    # Delete all linked invites
    if linked_invites:
        repo.trip_invites_collection.delete_many({"itinerary_id": itinerary_id})

    # Delete the itinerary
    success = repo.delete_itinerary(itinerary_id)
    if not success:
        raise HTTPException(status_code=404, detail="Itinerary not found")
    return {"message": "Itinerary deleted successfully"}


@router.patch("/{itinerary_id}/participants")
async def update_itinerary_participants(
    itinerary_id: str,
    participants_data: dict,
    x_clerk_user_id: str = Header(..., alias="X-Clerk-User-Id"),
):
    """Update participants list for an itinerary."""
    clerk_user_id = x_clerk_user_id

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
    participants_list = participants_data.get("participants", [])
    group_participants = []

    for p in participants_list:
        group_participants.append(
            {
                "first_name": p.get("first_name", ""),
                "last_name": p.get("last_name", ""),
                "email": p.get("email"),
                "email_sent": p.get("email_sent", False),
                "email_sent_at": p.get("email_sent_at"),
            }
        )

    # Update group info
    group_info["participants"] = group_participants
    document["group"] = group_info

    # Update itinerary in database
    repo.itineraries_collection.update_one(
        {"id": itinerary_id}, {"$set": {"document": document}}
    )

    updated_itinerary = repo.get_itinerary(itinerary_id)
    return updated_itinerary


@router.post("/{itinerary_id}/share")
async def share_itinerary(
    itinerary_id: str,
    share_data: dict,
    x_clerk_user_id: str = Header(..., alias="X-Clerk-User-Id"),
):
    """Share an itinerary with participants by creating or updating an invite."""
    from app.core.email_service import send_trip_invite_email

    clerk_user_id = x_clerk_user_id

    # Get itinerary
    itinerary = repo.get_itinerary(itinerary_id)
    if not itinerary:
        raise HTTPException(status_code=404, detail="Itinerary not found")

    # Verify ownership
    if itinerary.get("clerk_user_id") != clerk_user_id:
        raise HTTPException(
            status_code=403, detail="Only the itinerary owner can share it"
        )

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
    existing_invite = repo.trip_invites_collection.find_one(
        {"itinerary_id": itinerary_id}
    )

    if existing_invite:
        existing_invite.pop("_id", None)  # Remove MongoDB ObjectId
        invite_id = existing_invite["id"]
        # Update existing invite with new participants
        participant_emails = share_data.get("participant_emails", [])
        organizer_name = share_data.get(
            "organizer_name", user.first_name or "Trip Organizer"
        )

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
                    first_name=(
                        participant_info.get("first_name", "")
                        if participant_info
                        else ""
                    ),
                    last_name=(
                        participant_info.get("last_name", "")
                        if participant_info
                        else ""
                    ),
                )

        # Send emails to selected participants
        sent_count = 0
        failed_emails = []

        for email in participant_emails:
            try:
                send_trip_invite_email(
                    to_email=email,
                    invite_id=invite_id,
                    organizer_name=organizer_name,
                    trip_name=trip_name,
                )
                sent_count += 1
            except Exception as e:
                print(f"Failed to send email to {email}: {e}")
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
            organizer_name=f"{user.first_name or ''} {user.last_name or ''}".strip()
            or None,
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
        participant_emails = share_data.get("participant_emails", [])
        organizer_name = share_data.get(
            "organizer_name", user.first_name or "Trip Organizer"
        )

        group_participants = document.get("group", {}).get("participants", [])
        for email in participant_emails:
            participant_info = next(
                (p for p in group_participants if p.get("email") == email), None
            )

            repo.add_participant(
                invite_id=invite_id,
                email=email,
                first_name=(
                    participant_info.get("first_name", "") if participant_info else ""
                ),
                last_name=(
                    participant_info.get("last_name", "") if participant_info else ""
                ),
            )

        # Send emails
        sent_count = 0
        failed_emails = []

        for email in participant_emails:
            try:
                send_trip_invite_email(
                    to_email=email,
                    invite_id=invite_id,
                    organizer_name=organizer_name,
                    trip_name=trip_name,
                )
                sent_count += 1
            except Exception as e:
                print(f"Failed to send email to {email}: {e}")
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
