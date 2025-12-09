"""
Events API Router

Serves event data from database.
"""

from pathlib import Path
from typing import Any

from app.core.clerk_security import (
    get_current_user_from_clerk,
    get_current_user_optional,
)
from app.core.repository import repo
from app.core.schemas import User
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/events", tags=["events"])


class Event(BaseModel):
    """Event schema."""

    event_name: str
    type: str
    location: str
    date: str
    time: str | None = None
    price_range: str
    primary_link: str
    image_url: str | None = None
    note: str | None = None


@router.post("/import", response_model=dict[str, Any])
async def import_events() -> dict[str, Any]:
    """
    Import events from CSV file into database.

    This endpoint reads the CSV file, parses it, and stores events in MongoDB.
    Replaces all existing events.

    Usage:
        curl -X POST http://localhost:8000/api/events/import
    """
    try:
        # Get path to CSV file
        current_dir = Path(__file__).parent.parent.parent
        csv_path = (
            current_dir / "extras" / "Traverse Events - Detty December - Sheet1.csv"
        )

        if not csv_path.exists():
            raise HTTPException(
                status_code=404, detail=f"CSV file not found at {csv_path}"
            )

        result = await repo.import_events_from_csv(csv_path)
        return {
            "success": True,
            "message": f"Successfully imported {result['imported']} events",
            **result,
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error importing events: {str(e)}")


@router.get("", response_model=list[dict[str, Any]])
async def get_events(
    current_user: User | None = Depends(get_current_user_optional),
) -> list[dict[str, Any]]:
    """
    Get all events from database with favorite status for current user.

    Returns:
        List of events from database, each with an 'is_favorite' field
    """
    try:
        events = await repo.get_all_events()

        # Get user's favorites if authenticated
        favorite_ids: set[str] = set()
        if current_user:
            favorite_ids = set(
                await repo.get_user_favorites(current_user.clerk_user_id)
            )

        # Add favorite status and create event identifier
        for event in events:
            event_identifier = f"{event['event_name']}_{event['date']}"
            event["is_favorite"] = event_identifier in favorite_ids

        return events
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading events: {str(e)}")


@router.post("/favorites/{event_identifier}", response_model=dict[str, Any])
async def add_favorite(
    event_identifier: str,
    current_user: User = Depends(get_current_user_from_clerk),
) -> dict[str, Any]:
    """
    Add an event to user's favorites.

    Args:
        event_identifier: Event identifier (event_name + date)
    """
    try:
        success = await repo.add_user_favorite(
            current_user.clerk_user_id, event_identifier
        )
        if not success:
            raise HTTPException(status_code=500, detail="Failed to add favorite")
        return {"success": True, "message": "Event added to favorites"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error adding favorite: {str(e)}")


@router.delete("/favorites/{event_identifier}", response_model=dict[str, Any])
async def remove_favorite(
    event_identifier: str,
    current_user: User = Depends(get_current_user_from_clerk),
) -> dict[str, Any]:
    """
    Remove an event from user's favorites.

    Args:
        event_identifier: Event identifier (event_name + date)
    """
    try:
        success = await repo.remove_user_favorite(
            current_user.clerk_user_id, event_identifier
        )
        if not success:
            raise HTTPException(status_code=500, detail="Failed to remove favorite")
        return {"success": True, "message": "Event removed from favorites"}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error removing favorite: {str(e)}"
        )


@router.get("/favorites", response_model=list[str])
async def get_favorites(
    current_user: User = Depends(get_current_user_from_clerk),
) -> list[str]:
    """
    Get list of favorited event identifiers for current user.

    Returns:
        List of event identifiers (event_name + date)
    """
    try:
        favorites = await repo.get_user_favorites(current_user.clerk_user_id)
        return favorites
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error loading favorites: {str(e)}"
        )
