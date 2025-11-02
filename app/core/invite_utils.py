"""Utility functions for trip invite date analysis."""

from collections import defaultdict
from datetime import datetime


def analyze_common_dates(participants: list[dict]) -> dict:
    """
    Analyze participant availability to find the longest consecutive date range
    with the highest participant overlap.

    Args:
        participants: List of participant dicts with 'available_dates' and 'status'

    Returns:
        Dict containing:
        - calculated_start_date: Best start date (ISO string) or None
        - calculated_end_date: Best end date (ISO string) or None
        - no_common_dates: True if no dates have >50% overlap
        - common_dates_percentage: Percentage of responded participants available
    """
    # Filter to only responded participants
    responded = [p for p in participants if p.get("status") == "responded"]

    if not responded:
        return {
            "calculated_start_date": None,
            "calculated_end_date": None,
            "no_common_dates": True,
            "common_dates_percentage": 0,
        }

    total_responded = len(responded)
    threshold = total_responded * 0.5  # 50% threshold

    # Build a map of date -> count of participants available
    date_counts = defaultdict(int)
    all_dates_set = set()

    for participant in responded:
        dates = participant.get("available_dates", [])
        if not dates:
            continue

        for date_str in dates:
            date_counts[date_str] += 1
            all_dates_set.add(date_str)

    if not date_counts:
        return {
            "calculated_start_date": None,
            "calculated_end_date": None,
            "no_common_dates": True,
            "common_dates_percentage": 0,
        }

    # Convert to sorted list of dates
    all_dates = sorted(list(all_dates_set))

    # Find all consecutive date ranges and their participant counts
    best_range = None
    best_count = 0
    best_length = 0

    for i, start_date_str in enumerate(all_dates):
        start_date = datetime.fromisoformat(start_date_str)

        # Try to extend this range as long as possible
        current_range = [start_date_str]
        current_date = start_date
        min_count_in_range = date_counts[start_date_str]

        # Extend forward day by day
        for j in range(i + 1, len(all_dates)):
            next_date_str = all_dates[j]
            next_date = datetime.fromisoformat(next_date_str)

            # Check if next date is consecutive (1 day apart)
            if (next_date - current_date).days == 1:
                current_range.append(next_date_str)
                current_date = next_date
                # Track minimum count in the range (weakest link)
                min_count_in_range = min(min_count_in_range, date_counts[next_date_str])
            else:
                # Gap in dates, stop extending
                break

        # Evaluate this range
        range_length = len(current_range)
        range_percentage = (min_count_in_range / total_responded) * 100

        # Prioritize: longer ranges, then higher participant count
        is_better = False
        if range_length > best_length or (
            range_length == best_length and min_count_in_range > best_count
        ):
            is_better = True

        if is_better:
            best_range = (current_range[0], current_range[-1])
            best_count = min_count_in_range
            best_length = range_length

    # Determine if we found acceptable dates
    if best_range and best_count > threshold:
        percentage = int((best_count / total_responded) * 100)
        return {
            "calculated_start_date": best_range[0],
            "calculated_end_date": best_range[1],
            "no_common_dates": False,
            "common_dates_percentage": percentage,
        }
    elif best_range:
        # Found dates but below 50% threshold
        percentage = int((best_count / total_responded) * 100)
        return {
            "calculated_start_date": best_range[0],
            "calculated_end_date": best_range[1],
            "no_common_dates": True,
            "common_dates_percentage": percentage,
        }
    else:
        # No consecutive range found
        return {
            "calculated_start_date": None,
            "calculated_end_date": None,
            "no_common_dates": True,
            "common_dates_percentage": 0,
        }
