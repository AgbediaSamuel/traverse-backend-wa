"""
Helper functions for planning itinerary structure based on user preferences.
"""


def calculate_daily_activities(
    pace_style: int, schedule_style: int, total_days: int
) -> list[dict[str, int]]:
    """
    Calculate how many activities should be in each day based on user preferences.

    Args:
        pace_style: User's pace preference (0=Relaxation, 100=Adventure)
        schedule_style: User's schedule preference (0=Early Bird, 100=Night Owl)
        total_days: Total number of days in the trip

    Returns:
        List of dicts with activity counts per day:
        [
            {"day": 1, "min_activities": 2, "max_activities": 3},
            {"day": 2, "min_activities": 3, "max_activities": 4},
            ...
        ]
    """
    # Base activity count based on pace style
    if pace_style <= 33:  # Relaxation
        base_min = 2
        base_max = 3
    elif pace_style <= 66:  # Moderate
        base_min = 3
        base_max = 4
    else:  # Adventure
        base_min = 4
        base_max = 6

    daily_activities = []

    for day_num in range(1, total_days + 1):
        # Adjust for first and last day (lighter schedule)
        if day_num == 1:
            # First day: arrival, lighter schedule
            min_acts = max(2, base_min - 1)
            max_acts = max(3, base_max - 1)
        elif day_num == total_days:
            # Last day: departure, lighter schedule
            min_acts = max(2, base_min - 1)
            max_acts = max(3, base_max - 1)
        else:
            # Middle days: full schedule
            min_acts = base_min
            max_acts = base_max

        daily_activities.append(
            {"day": day_num, "min_activities": min_acts, "max_activities": max_acts}
        )

    return daily_activities


def get_activity_mix_guidance(
    pace_style: int, schedule_style: int, day_number: int, total_days: int
) -> str:
    """
    Generate guidance text for LLM about activity mix for a specific day.

    Args:
        pace_style: User's pace preference (0=Relaxation, 100=Adventure)
        schedule_style: User's schedule preference (0=Early Bird, 100=Night Owl)
        day_number: Current day number
        total_days: Total days in trip

    Returns:
        Guidance string for LLM
    """
    # Determine pace label
    if pace_style <= 33:
        pace_label = "relaxed"
        duration_mix = "Include 1-2 long activities (3-4 hours like museums or spa), and 1-2 shorter activities."
    elif pace_style <= 66:
        pace_label = "moderate"
        duration_mix = (
            "Mix of 1 long activity (2-3 hours), 2-3 medium activities (1.5-2 hours)."
        )
    else:
        pace_label = "energetic"
        duration_mix = "Pack the day with 2-3 medium activities (1.5-2 hours) and 2-3 short activities (30min-1 hour)."

    # Determine schedule guidance
    if schedule_style <= 33:
        schedule_guidance = "Start early (7-8 AM), end by 8 PM."
    elif schedule_style <= 66:
        schedule_guidance = "Start around 9 AM, can go until 9-10 PM."
    else:
        schedule_guidance = "Can start later (10-11 AM), include evening/nightlife activities until midnight."

    # Day-specific guidance
    if day_number == 1:
        day_note = "First day - lighter schedule, nearby attractions, allow for travel fatigue."
    elif day_number == total_days:
        day_note = "Last day - lighter schedule, flexible timing for departure."
    else:
        day_note = f"Full day {day_number} - {pace_label} pace."

    return f"{day_note} {duration_mix} {schedule_guidance}"


def map_interests_to_place_types(interests: list[str]) -> list[str]:
    """
    Map user interest selections to Google Places types and search queries.

    Args:
        interests: List of user's selected interests

    Returns:
        List of search queries for Places API
    """
    interest_mapping = {
        # Dining
        "Street food": "street food markets food stalls",
        "Fine dining": "fine dining restaurants michelin",
        "Franchise restaurants": "restaurants chains",
        "Coffee & café hopping": "cafes coffee shops",
        "Food festivals": "food markets festivals",
        # Shopping
        "Vintage & Thrift": "vintage shops thrift stores",
        "Luxury Boutiques": "luxury shopping boutiques designer",
        "Malls": "shopping malls centers",
        # Relaxation / Wellness
        "Spas": "spas wellness massage",
        "Yoga": "yoga studios wellness",
        "Pilates": "pilates studios fitness",
        "Sunrise / Sunset Spots": "scenic viewpoints sunset spots",
        # Culture / History
        "Local Festivals": "cultural events festivals",
        "Architecture & Landmarks": "landmarks monuments architecture",
        "Museums": "museums",
        "Local Traditions": "cultural sites traditional",
        "Historical Tours": "historical sites heritage",
        # Social / Nightlife
        "Live Music / Concerts": "live music venues concert halls",
        "Beach Parties": "beach clubs party",
        "Bar Crawls": "bars pubs",
        "Clubs": "nightclubs dance clubs",
        # Arts / Creativity
        "Art Galleries": "art galleries contemporary art",
        "Creative Workshops": "workshops classes creative",
        "Film / Theatre Events": "theaters cinema performing arts",
        # Adventure / Nature
        "Beach & Water Activities": "beaches water sports",
        "Hiking": "hiking trails nature walks",
        "Rock Climbing": "climbing gyms outdoor climbing",
        "Mountains & Scenic Views": "mountains viewpoints scenic",
        "Safaris": "wildlife safari nature",
        "Zip-lining": "adventure parks zip line",
        "Paragliding": "paragliding adventure sports",
        "Diving": "diving scuba snorkeling",
        "ATV Riding": "atv tours adventure",
        "Local Sporting Events": "stadiums sports venues",
        # Content / Aesthetics
        "Instagrammable Spots": "photo spots instagram worthy scenic",
        "Scenic Drone Locations": "viewpoints panoramic scenic",
        "Trendy Cafés / Colorful Streets": "trendy cafes colorful streets aesthetic",
    }

    queries = []
    for interest in interests:
        if interest in interest_mapping:
            queries.append(interest_mapping[interest])
        else:
            # Fallback: use the interest as-is
            queries.append(interest.lower())

    return queries


def get_budget_price_levels(budget_style: int) -> list[int]:
    """
    Map budget style to Google Places price levels.

    Args:
        budget_style: Budget preference (0=Budget, 100=Luxury)

    Returns:
        List of acceptable price levels [1-4]
    """
    if budget_style <= 33:
        return [1, 2]  # Budget to Moderate
    elif budget_style <= 66:
        return [2, 3]  # Moderate to Upscale
    else:
        return [3, 4]  # Upscale to Luxury
