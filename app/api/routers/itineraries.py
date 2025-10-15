import json
from typing import Any, Dict

from app.core.llm_provider import LLMProvider
from app.core.repository import repo
from app.core.schemas import Activity, Day, ItineraryDocument
from app.core.settings import get_settings
from fastapi import APIRouter, HTTPException

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


@router.post("/generate", response_model=Dict[str, Any])
def generate_itinerary(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Generate an itinerary using LLM based on user-provided information."""
    traveler_name = payload.get("traveler_name") or "Traveler"
    destination = payload.get("destination") or ""
    dates = payload.get("dates") or ""
    duration = payload.get("duration") or ""

    if not traveler_name or not destination or not dates:
        raise HTTPException(
            status_code=400, detail="traveler_name, destination and dates are required"
        )

    settings = get_settings()
    provider = LLMProvider(model=settings.aisuite_model)

    system = {
        "role": "system",
        "content": (
            "Output ONLY a valid JSON object matching the ItineraryDocument schema. "
            "Important date handling:\n"
            "- If 'dates' contains a full range (e.g., 'August 15-20, 2025'), normalize it to 'YYYY-MM-DD - YYYY-MM-DD' format\n"
            "- If 'dates' contains only a start date and 'duration' is provided (e.g., dates='August 15 2025', duration='5 days'), "
            "calculate the end date by adding the duration to the start date, then format as 'YYYY-MM-DD - YYYY-MM-DD'\n"
            "- Use the provided 'duration' value if given, otherwise derive it from the date range\n"
            "- Set cover_image to null\n"
            "- Generate a realistic 'days' array with 2-3 activities per day, one day for each day of the trip\n"
            "- Generate a 'notes' array with 3-5 helpful travel tips specific to the destination "
            "(e.g., currency, weather, cultural etiquette, safety tips, transportation, what to pack, local customs, etc.)\n"
            "Required shape: {traveler_name, destination, dates, duration, cover_image, days:[{date, "
            "activities:[{time,title,location,description,image}]}], notes:[]}. No prose, just JSON."
        ),
    }
    user = {
        "role": "user",
        "content": json.dumps(
            {
                "traveler_name": traveler_name,
                "destination": destination,
                "dates": dates,
                "duration": duration,
            }
        ),
    }
    try:
        raw = provider.chat(messages=[system, user], temperature=0.1)
        doc: ItineraryDocument = _parse_itinerary_json_or_502(raw)
        itn_id = repo.save_itinerary(doc)
        return repo.get_itinerary(itn_id) or {"id": itn_id}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail={"provider_error": str(exc)})


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
    return {"itineraries": list(repo.itineraries.values())}


@router.post("")
def create_itinerary(doc: ItineraryDocument):
    itn_id = repo.save_itinerary(doc)
    data = repo.get_itinerary(itn_id)
    if not data:
        raise HTTPException(status_code=500, detail="failed to persist itinerary")
    return data


@router.delete("/{itinerary_id}")
def delete_itinerary(itinerary_id: str):
    """Delete an itinerary by ID."""
    success = repo.delete_itinerary(itinerary_id)
    if not success:
        raise HTTPException(status_code=404, detail="Itinerary not found")
    return {"message": "Itinerary deleted successfully"}
