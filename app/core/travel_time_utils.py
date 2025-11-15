"""
Utilities for calculating travel time between activities.
"""

from typing import Literal


def estimate_travel_time(
    distance_km: float, mode: Literal["auto", "walking", "transit", "driving"] = "auto"
) -> int:
    """
    Estimate travel time in minutes based on distance.

    Args:
        distance_km: Distance in kilometers
        mode: Transportation mode
            - "auto": automatically choose based on distance
            - "walking": ~5 km/h
            - "transit": ~25 km/h + 10 min wait/buffer
            - "driving": ~40 km/h + 5 min parking/buffer

    Returns:
        Travel time in minutes
    """
    if mode == "auto":
        # Auto-select mode based on distance
        if distance_km < 2.0:
            mode = "walking"
        elif distance_km < 10.0:
            mode = "transit"
        else:
            mode = "driving"

    if mode == "walking":
        # Walking: ~5 km/h = ~12 min/km
        return int(distance_km * 12) + 5  # +5 min buffer
    elif mode == "transit":
        # Public transit: ~25 km/h = ~2.4 min/km + 10 min wait
        return int(distance_km * 2.4) + 10
    elif mode == "driving":
        # Driving: ~40 km/h = ~1.5 min/km + 5 min parking
        return int(distance_km * 1.5) + 5
    else:
        # Fallback
        return int(distance_km * 5) + 10


def estimate_activity_duration(venue_types: list[str], pace_style: int = 50) -> int:
    """
    Estimate how long an activity will take based on venue type and user pace.

    Args:
        venue_types: List of Google Places types
        pace_style: User's pace preference (0=Relaxed, 100=Adventure)

    Returns:
        Estimated duration in minutes
    """
    # Determine pace multiplier (relaxed = longer durations, adventurous = shorter)
    if pace_style <= 33:
        pace_multiplier = 1.2  # Relaxed: 20% longer
    elif pace_style <= 66:
        pace_multiplier = 1.0  # Moderate: baseline
    else:
        pace_multiplier = 0.8  # Adventurous: 20% shorter

    # Base durations by venue type (in minutes)
    type_durations = {
        "museum": 150,  # 2.5 hours
        "art_gallery": 120,  # 2 hours
        "tourist_attraction": 90,  # 1.5 hours
        "restaurant": 90,  # 1.5 hours
        "cafe": 45,  # 45 minutes
        "bar": 120,  # 2 hours
        "night_club": 180,  # 3 hours
        "park": 90,  # 1.5 hours
        "shopping_mall": 120,  # 2 hours
        "store": 60,  # 1 hour
        "spa": 120,  # 2 hours
        "beach": 120,  # 2 hours
        "landmark": 60,  # 1 hour
        "church": 45,  # 45 minutes
        "mosque": 45,  # 45 minutes
        "temple": 45,  # 45 minutes
        "theater": 150,  # 2.5 hours (includes show)
        "stadium": 180,  # 3 hours (includes event)
        "amusement_park": 240,  # 4 hours
        "zoo": 180,  # 3 hours
        "aquarium": 120,  # 2 hours
    }

    # Find matching type
    duration = 90  # Default: 1.5 hours

    for vtype in venue_types:
        if vtype in type_durations:
            duration = type_durations[vtype]
            break

    # Apply pace multiplier
    duration = int(duration * pace_multiplier)

    return duration


def add_minutes_to_time(time_str: str, minutes: int) -> str:
    """
    Add minutes to a time string.

    Args:
        time_str: Time in "H:MM AM/PM" format (e.g., "2:00 PM", "10:30 AM")
        minutes: Minutes to add

    Returns:
        New time string in same format
    """
    # Parse the time string
    import re

    pattern = r"(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)"
    match = re.match(pattern, time_str.strip())

    if not match:
        # Can't parse - return original
        return time_str

    hour = int(match.group(1))
    minute = int(match.group(2))
    meridiem = match.group(3).upper()

    # Convert to 24-hour
    if meridiem == "AM":
        if hour == 12:
            hour = 0
    else:  # PM
        if hour != 12:
            hour += 12

    # Add minutes
    total_minutes = hour * 60 + minute + minutes

    # Handle day overflow (wrap to next day)
    total_minutes = total_minutes % (24 * 60)

    # Convert back to 12-hour format
    new_hour = total_minutes // 60
    new_minute = total_minutes % 60

    if new_hour == 0:
        return f"12:{new_minute:02d} AM"
    elif new_hour < 12:
        return f"{new_hour}:{new_minute:02d} AM"
    elif new_hour == 12:
        return f"12:{new_minute:02d} PM"
    else:
        return f"{new_hour - 12}:{new_minute:02d} PM"
