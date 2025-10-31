import requests
from fastapi import APIRouter, HTTPException, Query, Response

from app.core.places_service import places_service

router = APIRouter(prefix="/places", tags=["places"])


@router.get("/autocomplete")
def autocomplete(query: str = Query(..., min_length=2, max_length=120)) -> list[dict]:
    """Return destination suggestions for a free-text query."""
    return places_service.autocomplete_places(query)
