from fastapi import APIRouter, HTTPException

from app.core.repository import repo
from app.core.schemas import Activity, Day, ItineraryDocument

router = APIRouter(prefix="/itineraries", tags=["itineraries"])


@router.get("/sample", response_model=ItineraryDocument)
def get_sample_itinerary() -> ItineraryDocument:
    return ItineraryDocument(
        traveler_name="Sheriff",
        destination="Las Vegas",
        dates="March 15-17, 2025",
        duration="Three Day Weekend",
        cover_image=(
            "https://images.unsplash.com/photo-1683645012230-"
            "e3a3c1255434?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&q=80&w=1080"
        ),
        days=[
            Day(
                date="Friday, March 15",
                activities=[
                    Activity(
                        time="12:00 PM",
                        title="Arrival & Check-in",
                        location="Bellagio Hotel & Casino",
                        description=("Check into the Bellagio suite and enjoy " "fountain views."),
                        image=(
                            "https://images.unsplash.com/"
                            "photo-1683645012230-e3a3c1255434"
                            "?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&q=80&w=1080"
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


@router.get("/{itinerary_id}")
def get_itinerary(itinerary_id: str):
    data = repo.get_itinerary(itinerary_id)
    if not data:
        raise HTTPException(status_code=404, detail="not found")
    return data


@router.get("")
def list_itineraries():
    return {"itineraries": list(repo.itineraries.values())}
