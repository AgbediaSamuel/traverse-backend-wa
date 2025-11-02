"""
Utility for aggregating preferences from multiple users for group trips.
"""

from statistics import median
from typing import Any


def aggregate_preferences(preferences_list: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Aggregate preferences from multiple users.

    Args:
        preferences_list: List of user preference dictionaries

    Returns:
        Aggregated preferences dictionary
    """
    if not preferences_list:
        # Return default preferences if no preferences provided
        return {
            "budget_style": 50,
            "pace_style": 50,
            "schedule_style": 50,
            "selected_interests": [],
            "other_interests": [],  # NEW: Include empty list for other_interests
        }

    if len(preferences_list) == 1:
        # If only one set of preferences, return as-is
        return preferences_list[0]

    # Aggregate numeric values (use median for better balance)
    budget_values = [
        p.get("budget_style", 50)
        for p in preferences_list
        if p.get("budget_style") is not None
    ]
    pace_values = [
        p.get("pace_style", 50)
        for p in preferences_list
        if p.get("pace_style") is not None
    ]
    schedule_values = [
        p.get("schedule_style", 50)
        for p in preferences_list
        if p.get("schedule_style") is not None
    ]

    aggregated_budget = int(median(budget_values)) if budget_values else 50
    aggregated_pace = int(median(pace_values)) if pace_values else 50
    aggregated_schedule = int(median(schedule_values)) if schedule_values else 50

    # Aggregate interests (take union of all interests)
    all_interests = set()
    for prefs in preferences_list:
        interests = prefs.get("selected_interests", [])
        if interests:
            all_interests.update(interests)

    # Convert back to list and sort for consistency
    aggregated_interests = sorted(list(all_interests))

    # Aggregate other_interests (collect all free-text other interests)
    all_other_interests = []
    for prefs in preferences_list:
        other = prefs.get("other_interests")
        if other and other.strip():
            all_other_interests.append(other.strip())

    return {
        "budget_style": aggregated_budget,
        "pace_style": aggregated_pace,
        "schedule_style": aggregated_schedule,
        "selected_interests": aggregated_interests,
        "other_interests": all_other_interests,  # NEW: Include other_interests for extraction
        "is_aggregated": True,
        "participant_count": len(preferences_list),
    }


def get_preference_summary(aggregated_prefs: dict[str, Any]) -> str:
    """
    Generate a human-readable summary of aggregated preferences for LLM context.

    Args:
        aggregated_prefs: Aggregated preferences dictionary

    Returns:
        Human-readable summary string
    """
    if not aggregated_prefs.get("is_aggregated"):
        return ""

    participant_count = aggregated_prefs.get("participant_count", 1)
    budget = aggregated_prefs.get("budget_style", 50)
    pace = aggregated_prefs.get("pace_style", 50)
    schedule = aggregated_prefs.get("schedule_style", 50)
    interests = aggregated_prefs.get("selected_interests", [])

    # Convert numeric values to descriptive labels
    def get_budget_label(value: int) -> str:
        if value < 33:
            return "Budget-conscious"
        elif value < 67:
            return "Mid-range"
        else:
            return "Luxury"

    def get_pace_label(value: int) -> str:
        if value < 33:
            return "Relaxed"
        elif value < 67:
            return "Moderate"
        else:
            return "Energetic"

    def get_schedule_label(value: int) -> str:
        if value < 33:
            return "Flexible/spontaneous"
        elif value < 67:
            return "Balanced"
        else:
            return "Structured/planned"

    budget_label = get_budget_label(budget)
    pace_label = get_pace_label(pace)
    schedule_label = get_schedule_label(schedule)

    interests_str = ", ".join(interests) if interests else "varied activities"

    summary = f"""
GROUP TRIP - {participant_count} Travelers:
- Budget preference: {budget_label} (median: {budget}/100)
- Pace preference: {pace_label} (median: {pace}/100)
- Schedule preference: {schedule_label} (median: {schedule}/100)
- Combined interests: {interests_str}

Note: This itinerary should balance diverse preferences and include activities 
that cater to different interests within the group. Aim for variety to ensure 
everyone has experiences they'll enjoy.
    """.strip()

    return summary
