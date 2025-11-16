"""
Extract structured information from free-text preferences using LLM.
"""

import json
import re

from app.core.llm_provider import LLMProvider
from app.core.settings import get_settings


def extract_preferences_from_text(
    text: str, context: dict[str, any] | None = None
) -> dict[str, any]:
    """
    Extract structured search queries and preference signals from free text.

    Args:
        text: Free text input (other_interests or vibe_notes)
        context: Optional context (destination, trip_type, etc.)

    Returns:
        {
            "search_queries": List[str],  # Google Places search queries
            "place_types": List[str],     # Google Places API types
            "keywords": List[str],         # Keywords for scoring boost
            "preference_signals": Dict[str, any]  # Additional signals
        }
    """
    if not text or not text.strip():
        return {
            "search_queries": [],
            "place_types": [],
            "keywords": [],
            "preference_signals": {},
        }

    settings = get_settings()
    provider = LLMProvider(model=settings.aisuite_model)

    # Build context string
    context_str = ""
    if context:
        if context.get("destination"):
            context_str += f"Destination: {context['destination']}\n"
        if context.get("trip_type"):
            context_str += f"Trip Type: {context['trip_type']}\n"
        if context.get("selected_interests"):
            context_str += (
                f"User's selected interests: {', '.join(context['selected_interests'][:5])}\n"
            )

    system_prompt = {
        "role": "system",
        "content": (
            "You are a travel preference extraction system. Extract structured information "
            "from user's free-text travel preferences.\n\n"
            "Analyze the text and extract:\n"
            "1. SEARCH QUERIES: Specific things to search for in Google Places (e.g., 'rooftop bars', "
            "'street art tours', 'farmers markets'). Return 3-8 specific search queries.\n"
            "2. PLACE TYPES: Google Places API types (e.g., 'museum', 'restaurant', 'park', 'art_gallery'). "
            "Return matching types from: tourist_attraction, museum, art_gallery, restaurant, cafe, "
            "bar, night_club, park, beach, spa, shopping_mall, theater, stadium, zoo, aquarium, "
            "amusement_park, church, temple, mosque, landmark, point_of_interest, natural_feature.\n"
            "3. KEYWORDS: Important keywords/phrases for scoring (e.g., 'vintage', 'romantic', 'hidden gems'). "
            "Return 5-15 keywords.\n"
            "4. PREFERENCE SIGNALS: Additional preferences like atmosphere (romantic, casual, adventurous), "
            "style (budget, luxury, mid-range), timing (morning, evening, night), group size preferences.\n\n"
            "Return ONLY valid JSON in this exact format:\n"
            "{\n"
            '  "search_queries": ["query1", "query2", ...],\n'
            '  "place_types": ["type1", "type2", ...],\n'
            '  "keywords": ["keyword1", "keyword2", ...],\n'
            '  "preference_signals": {\n'
            '    "atmosphere": ["romantic", "casual"],\n'
            '    "style": "mid-range",\n'
            '    "timing": ["evening", "night"],\n'
            '    "group_size": "small"\n'
            "  }\n"
            "}\n\n"
            "If no relevant information found, return empty arrays/lists but keep the structure."
        ),
    }

    user_prompt = {
        "role": "user",
        "content": (f"{context_str}\n" if context_str else "")
        + f"User's preferences text:\n{text}",
    }

    try:
        response = provider.chat(
            messages=[system_prompt, user_prompt],
            temperature=0.3,  # Lower temperature for more consistent extraction
        )

        # Parse JSON response
        response_text = response.strip()

        # Remove markdown code fences if present
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            response_text = "\n".join([l for l in lines if not l.startswith("```")])

        # Extract JSON object
        json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if json_match:
            response_text = json_match.group(0)

        # Convert single quotes to double quotes for JSON
        response_text = response_text.replace("'", '"')

        extracted = json.loads(response_text)

        # Validate structure
        return {
            "search_queries": extracted.get("search_queries", [])[:10],  # Limit to 10
            "place_types": extracted.get("place_types", [])[:15],  # Limit to 15
            "keywords": extracted.get("keywords", [])[:20],  # Limit to 20
            "preference_signals": extracted.get("preference_signals", {}),
        }

    except Exception as e:
        print(f"[PreferenceExtractor] Error extracting from text: {e}")
        print(
            f"[PreferenceExtractor] Raw response: {response[:200] if 'response' in locals() else 'N/A'}"
        )

        # Fallback: simple keyword extraction
        keywords = [w.strip().lower() for w in text.split() if len(w.strip()) > 3]
        return {
            "search_queries": keywords[:5],
            "place_types": [],
            "keywords": keywords[:10],
            "preference_signals": {},
        }
