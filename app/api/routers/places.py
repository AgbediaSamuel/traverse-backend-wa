from urllib.parse import unquote

import requests
from app.core.places_service import places_service
from fastapi import APIRouter, HTTPException, Query, Response

router = APIRouter(prefix="/places", tags=["places"])


@router.get("/autocomplete")
def autocomplete(query: str = Query(..., min_length=2, max_length=120)) -> list[dict]:
    """Return destination suggestions for a free-text query."""
    return places_service.autocomplete_places(query)


@router.get("/photo")
async def get_place_photo(
    ref: str = Query(..., description="Google Places photo reference"),
    w: int = Query(1080, ge=1, le=1600, description="Maximum width in pixels"),
) -> Response:
    """
    Proxy endpoint for Google Places photos.
    Fetches photo from Google Places API and streams it to the client.
    """
    try:
        # Decode the photo reference
        photo_reference = unquote(ref)

        # Fetch photo from Google Places API
        photo_url = places_service.get_place_photo_url(photo_reference, max_width=w)
        if not photo_url:
            raise HTTPException(status_code=400, detail="Invalid photo reference")

        # Fetch the image from Google
        response = requests.get(photo_url, timeout=10, stream=True)
        response.raise_for_status()

        # Determine content type
        content_type = response.headers.get("Content-Type", "image/jpeg")

        # Stream the image back to the client
        return Response(
            content=response.content,
            media_type=content_type,
            headers={
                "Cache-Control": "public, max-age=31536000",  # Cache for 1 year
            },
        )
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch photo: {str(e)}")
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error processing photo request: {str(e)}"
        )
