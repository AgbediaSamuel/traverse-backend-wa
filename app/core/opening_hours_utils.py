"""
Utilities for parsing and validating venue opening hours.
"""

import re
from datetime import datetime
from datetime import time as time_obj
from typing import Any


def parse_opening_hours(weekday_text: list[str]) -> dict[str, dict[str, str | None]]:
    """
    Parse Google Places opening hours weekday_text into structured format.

    Args:
        weekday_text: List of strings like ["Monday: 9:00 AM – 5:00 PM", "Tuesday: Closed"]

    Returns:
        Dictionary mapping day name to {open, close} times:
        {
            "Monday": {"open": "09:00", "close": "17:00"},
            "Tuesday": {"open": None, "close": None},  # Closed
            ...
        }
    """
    hours_map = {}

    for entry in weekday_text:
        # Split on colon to separate day from hours
        if ":" not in entry:
            continue

        day, hours_str = entry.split(":", 1)
        day = day.strip()
        hours_str = hours_str.strip()

        # Handle special cases
        if "Closed" in hours_str or "closed" in hours_str:
            hours_map[day] = {"open": None, "close": None}
            continue

        if "Open 24 hours" in hours_str or "24 hours" in hours_str:
            hours_map[day] = {"open": "00:00", "close": "23:59"}
            continue

        # Parse time range (e.g., "9:00 AM – 5:00 PM")
        # Google uses various separators: –, -, to, etc.
        time_pattern = r"(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)"
        matches = re.findall(time_pattern, hours_str)

        if len(matches) >= 2:
            # First match = opening time, last match = closing time
            open_match = matches[0]
            close_match = matches[-1]

            # Convert to 24-hour format
            open_24 = convert_to_24h(int(open_match[0]), int(open_match[1]), open_match[2])
            close_24 = convert_to_24h(int(close_match[0]), int(close_match[1]), close_match[2])

            hours_map[day] = {"open": open_24, "close": close_24}
        else:
            # Can't parse - assume open all day to be safe
            hours_map[day] = {"open": "00:00", "close": "23:59"}

    return hours_map


def convert_to_24h(hour: int, minute: int, meridiem: str) -> str:
    """
    Convert 12-hour time to 24-hour format string.

    Args:
        hour: Hour (1-12)
        minute: Minute (0-59)
        meridiem: "AM" or "PM"

    Returns:
        Time string in HH:MM format (24-hour)
    """
    meridiem = meridiem.upper()

    if meridiem == "AM":
        if hour == 12:
            hour = 0
    else:  # PM
        if hour != 12:
            hour += 12

    return f"{hour:02d}:{minute:02d}"


def parse_time_to_minutes(time_str: str) -> int:
    """
    Convert time string to minutes since midnight.

    Args:
        time_str: Time in "HH:MM AM/PM" or "HH:MM" format

    Returns:
        Minutes since midnight (0-1439)
    """
    time_str = time_str.strip()

    # Handle 12-hour format with AM/PM
    am_pm_pattern = r"(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)"
    match = re.match(am_pm_pattern, time_str)

    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        meridiem = match.group(3).upper()

        # Validate hour range for 12-hour format (must be 1-12)
        if hour < 1 or hour > 12:
            print(
                f"[TimeParse] Invalid hour {hour} in 12-hour format '{time_str}', defaulting to noon"
            )
            return 12 * 60

        # Validate minute range
        if minute < 0 or minute > 59:
            print(f"[TimeParse] Invalid minute {minute} in '{time_str}', defaulting to noon")
            return 12 * 60

        if meridiem == "AM":
            if hour == 12:
                hour = 0
        else:  # PM
            if hour != 12:
                hour += 12

        return hour * 60 + minute

    # Handle 24-hour format (HH:MM)
    hour_min_pattern = r"(\d{1,2}):(\d{2})"
    match = re.match(hour_min_pattern, time_str)

    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))

        # Validate 24-hour format ranges
        if hour < 0 or hour > 23:
            print(
                f"[TimeParse] Invalid hour {hour} in 24-hour format '{time_str}', defaulting to noon"
            )
            return 12 * 60

        if minute < 0 or minute > 59:
            print(f"[TimeParse] Invalid minute {minute} in '{time_str}', defaulting to noon")
            return 12 * 60

        return hour * 60 + minute

    # Default to noon if can't parse
    print(f"[TimeParse] Could not parse time string '{time_str}', defaulting to noon")
    return 12 * 60


def is_venue_open_at_time(
    opening_hours: dict[str, dict[str, str | None]], day_name: str, activity_time: str
) -> tuple[bool, str]:
    """
    Check if a venue is open at a given time.

    Args:
        opening_hours: Parsed opening hours dict
        day_name: Day of week (e.g., "Monday")
        activity_time: Activity time string (e.g., "2:00 PM")

    Returns:
        Tuple of (is_open: bool, reason: str)
    """
    if not opening_hours or day_name not in opening_hours:
        # No hours data - assume open
        return True, "No opening hours data available"

    day_hours = opening_hours[day_name]

    # Check if closed
    if day_hours["open"] is None or day_hours["close"] is None:
        return False, f"Venue closed on {day_name}"

    # Check if 24 hours
    if day_hours["open"] == "00:00" and day_hours["close"] == "23:59":
        return True, "Open 24 hours"

    # Parse times to minutes
    activity_minutes = parse_time_to_minutes(activity_time)
    open_minutes = parse_time_to_minutes(day_hours["open"])
    close_minutes = parse_time_to_minutes(day_hours["close"])

    # Handle venues that close after midnight
    if close_minutes < open_minutes:
        # e.g., opens at 8 PM (20:00), closes at 2 AM (02:00)
        # Activity is valid if it's after opening OR before closing
        if activity_minutes >= open_minutes or activity_minutes <= close_minutes:
            return True, f"OK (open {day_hours['open']} - {day_hours['close']})"
        else:
            return False, f"Outside hours ({day_hours['open']} - {day_hours['close']})"
    else:
        # Normal hours: activity must be between open and close
        if open_minutes <= activity_minutes <= close_minutes:
            return True, f"OK (open {day_hours['open']} - {day_hours['close']})"
        else:
            return False, f"Outside hours ({day_hours['open']} - {day_hours['close']})"


def adjust_time_to_opening_hours(
    activity_time: str,
    opening_hours: dict[str, dict[str, str | None]],
    day_name: str,
    prefer_earlier: bool = True,
) -> str:
    """
    Adjust activity time to fall within venue opening hours.

    Args:
        activity_time: Original activity time (e.g., "7:00 PM")
        opening_hours: Parsed opening hours dict
        day_name: Day of week
        prefer_earlier: If True, prefer earlier time; if False, prefer later time

    Returns:
        Adjusted time string in same format, or original if venue is 24/7 or no hours data
    """
    # Check if adjustment is needed
    is_open, reason = is_venue_open_at_time(opening_hours, day_name, activity_time)

    if is_open:
        return activity_time

    # Venue is closed or outside hours - adjust
    if not opening_hours or day_name not in opening_hours:
        return activity_time

    day_hours = opening_hours[day_name]

    if day_hours["open"] is None:
        # Closed all day - can't adjust (shouldn't happen, but return original)
        return activity_time

    # Parse activity time
    activity_minutes = parse_time_to_minutes(activity_time)
    open_minutes = parse_time_to_minutes(day_hours["open"])
    close_minutes = parse_time_to_minutes(day_hours["close"])

    # Determine if activity is before opening or after closing
    if activity_minutes < open_minutes:
        # Too early - move to opening time
        adjusted_minutes = open_minutes
    elif activity_minutes > close_minutes:
        # Too late - move to 1 hour before closing
        adjusted_minutes = max(open_minutes, close_minutes - 60)
    else:
        # Shouldn't reach here, but return opening time as fallback
        adjusted_minutes = open_minutes

    # Convert back to 12-hour format
    hours = adjusted_minutes // 60
    minutes = adjusted_minutes % 60

    if hours == 0:
        return f"12:{minutes:02d} AM"
    elif hours < 12:
        return f"{hours}:{minutes:02d} AM"
    elif hours == 12:
        return f"12:{minutes:02d} PM"
    else:
        return f"{hours - 12}:{minutes:02d} PM"


def get_default_hours_by_type(venue_types: list[str]) -> dict[str, dict[str, str]]:
    """
    Get default opening hours based on venue type when actual hours are unavailable.

    Args:
        venue_types: List of Google Places types

    Returns:
        Default hours dict for weekdays (Monday-Sunday assumed same)
    """
    # Check primary type
    primary_type = venue_types[0] if venue_types else "other"

    # Default hours by category (24-hour format)
    type_defaults = {
        "museum": {"open": "09:00", "close": "17:00"},
        "art_gallery": {"open": "10:00", "close": "18:00"},
        "restaurant": {"open": "11:00", "close": "22:00"},
        "cafe": {"open": "07:00", "close": "19:00"},
        "bar": {"open": "17:00", "close": "02:00"},  # Closes after midnight
        "night_club": {"open": "21:00", "close": "04:00"},
        "park": {"open": "06:00", "close": "20:00"},
        "shopping_mall": {"open": "10:00", "close": "21:00"},
        "store": {"open": "09:00", "close": "20:00"},
        "spa": {"open": "08:00", "close": "20:00"},
        "tourist_attraction": {"open": "09:00", "close": "18:00"},
        "point_of_interest": {"open": "09:00", "close": "18:00"},
    }

    # Find matching default
    for vtype in venue_types:
        if vtype in type_defaults:
            hours = type_defaults[vtype]
            # Return same hours for all days
            return {
                day: hours.copy()
                for day in [
                    "Monday",
                    "Tuesday",
                    "Wednesday",
                    "Thursday",
                    "Friday",
                    "Saturday",
                    "Sunday",
                ]
            }

    # Default: 9 AM - 6 PM for unknown types
    default_hours = {"open": "09:00", "close": "18:00"}
    return {
        day: default_hours.copy()
        for day in [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
    }
