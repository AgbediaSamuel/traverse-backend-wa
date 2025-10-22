from typing import Dict, List

import requests
from fastapi import APIRouter, HTTPException, Query, Response

from app.core.places_service import PLACES_API_BASE, places_service

router = APIRouter(prefix="/places", tags=["places"])


@router.get("/autocomplete")
def autocomplete(query: str = Query(..., min_length=2, max_length=120)) -> List[Dict]:
    """Return destination suggestions for a free-text query."""
    return places_service.autocomplete_places(query)


@router.get("/photo")
def get_place_photo(ref: str = Query(..., min_length=10), w: int = 1080) -> Response:
    """Proxy Google Places Photo API to avoid referrer/key exposure.

    Args:
        ref: Google Places photo_reference string
        w: desired max width (pixels)
    """
    try:
        url = (
            f"{PLACES_API_BASE}/photo?maxwidth={w}"
            f"&photo_reference={ref}&key={places_service.api_key}"
        )
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail="Photo fetch failed")

        content_type = resp.headers.get("Content-Type", "image/jpeg")
        headers = {"Cache-Control": "public, max-age=86400"}
        return Response(content=resp.content, media_type=content_type, headers=headers)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Photo proxy error: {e}")
