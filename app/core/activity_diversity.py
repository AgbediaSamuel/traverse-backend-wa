"""
Utilities for ensuring balanced activity diversity across days.
"""

from typing import Any


def categorize_activity(venue_types: list[str]) -> str:
    """
    Categorize a venue into a high-level activity category.

    Args:
        venue_types: List of Google Places types

    Returns:
        Category name (dining, culture, nightlife, outdoor, shopping, entertainment, wellness, other)
    """
    # Map Google Places types to categories
    category_map = {
        # Dining
        "dining": [
            "restaurant",
            "cafe",
            "food",
            "meal_takeaway",
            "meal_delivery",
            "bakery",
            "bar",  # bars can serve food
        ],
        # Culture / History
        "culture": [
            "museum",
            "art_gallery",
            "church",
            "mosque",
            "temple",
            "synagogue",
            "library",
            "university",
            "historical_landmark",
            "place_of_worship",
            "cultural_center",
        ],
        # Nightlife
        "nightlife": [
            "night_club",
            "casino",
            "bar",  # bars are both dining and nightlife
        ],
        # Outdoor / Nature
        "outdoor": [
            "park",
            "beach",
            "natural_feature",
            "campground",
            "hiking_area",
            "national_park",
            "rv_park",
            "playground",
        ],
        # Shopping
        "shopping": [
            "shopping_mall",
            "store",
            "clothing_store",
            "jewelry_store",
            "book_store",
            "electronics_store",
            "home_goods_store",
            "supermarket",
            "convenience_store",
            "department_store",
        ],
        # Entertainment
        "entertainment": [
            "movie_theater",
            "theater",
            "stadium",
            "amusement_park",
            "bowling_alley",
            "zoo",
            "aquarium",
            "tourist_attraction",
        ],
        # Wellness
        "wellness": ["spa", "gym", "physiotherapist", "hair_care", "beauty_salon"],
    }

    # Check each category
    for category, types in category_map.items():
        for vtype in venue_types:
            if vtype in types:
                # Special case: bars can be dining or nightlife
                if vtype == "bar":
                    # If other dining types present, categorize as dining
                    if any(t in ["restaurant", "cafe", "food"] for t in venue_types):
                        return "dining"
                    else:
                        return "nightlife"
                return category

    # If it's a point_of_interest, try to infer from other types
    if "point_of_interest" in venue_types and len(venue_types) > 1:
        # Recursively check other types
        return categorize_activity([t for t in venue_types if t != "point_of_interest"])

    return "other"


def calculate_diversity_score(day_activities: list[dict[str, Any]]) -> float:
    """
    Calculate diversity score for a day's activities (0.0 = all same category, 1.0 = all different).

    Args:
        day_activities: List of venue dicts with 'types' field

    Returns:
        Diversity score between 0.0 and 1.0
    """
    if not day_activities:
        return 1.0

    # Count categories
    category_counts = {}
    for venue in day_activities:
        category = categorize_activity(venue.get("types", []))
        category_counts[category] = category_counts.get(category, 0) + 1

    # Calculate diversity (number of unique categories / total activities)
    unique_categories = len(category_counts)
    total_activities = len(day_activities)

    # Normalize: perfect diversity would be all different categories
    # But cap at reasonable max (6-7 categories for typical day)
    max_possible_categories = min(total_activities, 7)

    diversity = unique_categories / max_possible_categories if max_possible_categories > 0 else 1.0

    return min(1.0, diversity)


def get_category_limit_for_day(category: str, total_activities: int, pace_style: int) -> int:
    """
    Get maximum number of activities from a single category allowed per day.

    Args:
        category: Activity category
        total_activities: Total number of activities for the day
        pace_style: User's pace preference (0=Relaxed, 100=Adventure)

    Returns:
        Maximum count for this category
    """
    # Base limits by category
    category_limits = {
        "dining": 3,  # Allow up to 3 dining experiences per day (breakfast, lunch, dinner)
        "nightlife": 2,  # Max 2 nightlife venues per day
        "culture": 3,  # Museums, galleries, etc. can be more
        "outdoor": 2,  # Parks, beaches
        "shopping": 2,  # Shopping venues
        "entertainment": 2,  # Shows, attractions
        "wellness": 2,  # Spas, gyms
        "other": 2,  # General limit
    }

    base_limit = category_limits.get(category, 2)

    # For high-pace trips, allow +1 more per category
    if pace_style > 66:
        base_limit += 1

    # Cap at 40% of total activities (prevents one category dominating)
    max_limit = max(2, int(total_activities * 0.4))

    return min(base_limit, max_limit)


def distribute_venues_with_diversity(
    venues: list[dict[str, Any]],
    num_days: int,
    activities_per_day: list[int],
    pace_style: int = 50,
) -> list[list[dict[str, Any]]]:
    """
    Distribute venues across days ensuring category diversity within each day.

    Args:
        venues: List of scored venues (already sorted by score)
        num_days: Number of days
        activities_per_day: List of activity counts for each day
        pace_style: User's pace preference

    Returns:
        List of venue lists, one per day, with balanced diversity
    """
    # Initialize day assignments
    days_venues: list[list[dict[str, Any]]] = [[] for _ in range(num_days)]
    day_category_counts: list[dict[str, int]] = [{} for _ in range(num_days)]

    # Assign venues one by one, choosing day with lowest count for that category
    for venue in venues:
        category = categorize_activity(venue.get("types", []))

        # Find best day for this venue
        best_day_idx = None
        min_category_count = float("inf")

        for day_idx in range(num_days):
            # Check if day still has capacity
            if len(days_venues[day_idx]) >= activities_per_day[day_idx]:
                continue

            # Check category limit for this day
            current_count = day_category_counts[day_idx].get(category, 0)
            limit = get_category_limit_for_day(category, activities_per_day[day_idx], pace_style)

            if current_count >= limit:
                continue

            # Prefer day with lowest count for this category
            if current_count < min_category_count:
                min_category_count = current_count
                best_day_idx = day_idx

        # Assign to best day
        if best_day_idx is not None:
            days_venues[best_day_idx].append(venue)
            day_category_counts[best_day_idx][category] = (
                day_category_counts[best_day_idx].get(category, 0) + 1
            )
        else:
            # No day has capacity or category limit reached - assign to day with most space
            # This is a fallback, shouldn't happen often
            day_with_space = min(range(num_days), key=lambda i: len(days_venues[i]))
            if len(days_venues[day_with_space]) < activities_per_day[day_with_space]:
                days_venues[day_with_space].append(venue)
                day_category_counts[day_with_space][category] = (
                    day_category_counts[day_with_space].get(category, 0) + 1
                )

    # Log diversity scores
    for day_idx, day_venues in enumerate(days_venues):
        diversity = calculate_diversity_score(day_venues)
        categories = {}
        for v in day_venues:
            cat = categorize_activity(v.get("types", []))
            categories[cat] = categories.get(cat, 0) + 1
        print(
            f"[Diversity] Day {day_idx+1}: {len(day_venues)} activities, diversity={diversity:.2f}, categories={categories}"
        )

    return days_venues
