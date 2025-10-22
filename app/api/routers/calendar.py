from typing import List

from fastapi import APIRouter, Header, HTTPException

from app.core.repository import repo
from app.core.schemas import (
    CalendarResponseSubmit,
    InviteParticipantCreate,
    InviteParticipantUpdate,
    SendInvitesRequest,
    TripInviteCreate,
    TripInviteResponse,
)

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.post("/invites", response_model=TripInviteResponse)
async def create_trip_invite(
    invite_data: TripInviteCreate,
    x_clerk_user_id: str = Header(..., alias="X-Clerk-User-Id"),
):
    """Create a new trip invite."""
    clerk_user_id = x_clerk_user_id

    # Get user info from database
    user = await repo.get_user_by_clerk_id(clerk_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    organizer_email = user.email
    organizer_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or None

    # Fetch cover image for destination if provided
    cover_image_url = None
    if invite_data.destination:
        try:
            from app.core.places_service import places_service
            from app.core.settings import get_settings

            settings = get_settings()
            backend_base = settings.frontend_url.replace("3456", "8765")  # Use backend port

            # Search for destination landmarks/cityscape
            places = places_service.search_places(
                location=invite_data.destination,
                query=f"{invite_data.destination} landmark cityscape",
                radius=20000,
                allowed_types=["tourist_attraction", "point_of_interest", "landmark"],
                max_pages=1,
            )

            if places and places[0].get("photo_reference"):
                photo_ref = places[0]["photo_reference"]
                cover_image_url = places_service.get_proxy_photo_url(photo_ref, backend_base, 1080)
        except Exception as e:
            print(f"Error fetching cover image for invite: {e}")
            # Non-fatal: continue without cover image

    invite_doc = repo.create_trip_invite(
        organizer_clerk_id=clerk_user_id,
        organizer_email=organizer_email,
        organizer_name=organizer_name,
        trip_name=invite_data.trip_name,
        destination=invite_data.destination,
        date_range_start=invite_data.date_range_start,
        date_range_end=invite_data.date_range_end,
        collect_preferences=invite_data.collect_preferences,
        trip_type=invite_data.trip_type,
        cover_image=cover_image_url,
    )

    return TripInviteResponse(**invite_doc)


@router.get("/invites", response_model=List[TripInviteResponse])
async def get_my_invites(x_clerk_user_id: str = Header(..., alias="X-Clerk-User-Id")):
    """Get all trip invites created by the authenticated user."""
    clerk_user_id = x_clerk_user_id
    invites = repo.get_user_trip_invites(clerk_user_id)
    return [TripInviteResponse(**invite) for invite in invites]


@router.get("/invites/received", response_model=List[TripInviteResponse])
async def get_received_invites(x_clerk_user_id: str = Header(..., alias="X-Clerk-User-Id")):
    """Get all trip invites where the authenticated user is a participant."""
    clerk_user_id = x_clerk_user_id

    # Get user email
    user = await repo.get_user_by_clerk_id(clerk_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    invites = repo.get_received_invites(user.email)
    return [TripInviteResponse(**invite) for invite in invites]


@router.get("/invites/{invite_id}", response_model=TripInviteResponse)
async def get_trip_invite(
    invite_id: str, x_clerk_user_id: str = Header(None, alias="X-Clerk-User-Id")  # Optional header
):
    """Get a specific trip invite by ID. No auth required for invite links."""
    invite = repo.get_trip_invite(invite_id)
    if not invite:
        raise HTTPException(status_code=404, detail="Trip invite not found")

    # Optional: Verify user has access if authenticated (either organizer or participant)
    if x_clerk_user_id:
        clerk_user_id = x_clerk_user_id
        user = await repo.get_user_by_clerk_id(clerk_user_id)
        if user:
            is_organizer = invite["organizer_clerk_id"] == clerk_user_id
            is_participant = any(p["email"] == user.email for p in invite.get("participants", []))

            if not (is_organizer or is_participant):
                raise HTTPException(status_code=403, detail="Access denied")

    return TripInviteResponse(**invite)


@router.patch("/invites/{invite_id}", response_model=TripInviteResponse)
async def update_trip_invite(
    invite_id: str,
    update_data: dict,
    x_clerk_user_id: str = Header(..., alias="X-Clerk-User-Id"),
):
    """Update a trip invite (e.g., collect_preferences setting)."""
    clerk_user_id = x_clerk_user_id

    # Get invite and verify ownership
    invite = repo.get_trip_invite(invite_id)
    if not invite:
        raise HTTPException(status_code=404, detail="Trip invite not found")

    if invite["organizer_clerk_id"] != clerk_user_id:
        raise HTTPException(status_code=403, detail="Only the organizer can update this invite")

    # Update collect_preferences if provided
    if "collect_preferences" in update_data:
        success = repo.update_invite_preferences(invite_id, update_data["collect_preferences"])
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update invite")

    # Fetch updated invite
    updated_invite = repo.get_trip_invite(invite_id)
    return TripInviteResponse(**updated_invite)


@router.delete("/invites/{invite_id}")
async def delete_trip_invite(
    invite_id: str,
    x_clerk_user_id: str = Header(..., alias="X-Clerk-User-Id"),
):
    """Delete a trip invite."""
    clerk_user_id = x_clerk_user_id

    # Get invite and verify ownership
    invite = repo.get_trip_invite(invite_id)
    if not invite:
        raise HTTPException(status_code=404, detail="Trip invite not found")

    if invite["organizer_clerk_id"] != clerk_user_id:
        raise HTTPException(status_code=403, detail="Only the organizer can delete this invite")

    success = repo.delete_trip_invite(invite_id)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete invite")

    return {"message": "Invite deleted successfully", "invite_id": invite_id}


@router.post("/invites/{invite_id}/reject")
async def reject_trip_invite(
    invite_id: str,
    request_body: dict,
    x_clerk_user_id: str = Header(..., alias="X-Clerk-User-Id"),
):
    """
    Allow a participant to reject/decline a trip invite.
    This marks the participant's status as "declined".
    """
    participant_email = request_body.get("email")

    if not participant_email:
        raise HTTPException(status_code=400, detail="Email is required")

    # Get invite
    invite = repo.get_trip_invite(invite_id)
    if not invite:
        raise HTTPException(status_code=404, detail="Trip invite not found")

    # Verify that the participant exists in this invite
    participant_exists = any(
        p.get("email") == participant_email for p in invite.get("participants", [])
    )
    if not participant_exists:
        raise HTTPException(status_code=404, detail="You are not a participant of this invite")

    # Update participant status to "declined"
    success = repo.update_participant_status(invite_id, participant_email, "declined")
    if not success:
        raise HTTPException(status_code=500, detail="Failed to decline invite")

    return {"message": "Invite declined successfully", "invite_id": invite_id}


@router.post("/invites/{invite_id}/participants", response_model=TripInviteResponse)
async def add_participant(
    invite_id: str,
    participant_data: InviteParticipantCreate,
    x_clerk_user_id: str = Header(..., alias="X-Clerk-User-Id"),
):
    """Add a participant to a trip invite."""
    clerk_user_id = x_clerk_user_id

    # Get invite and verify ownership
    invite = repo.get_trip_invite(invite_id)
    if not invite:
        raise HTTPException(status_code=404, detail="Trip invite not found")

    if invite["organizer_clerk_id"] != clerk_user_id:
        raise HTTPException(status_code=403, detail="Only the organizer can add participants")

    # Check if invites have been sent
    if invite["status"] != "draft":
        raise HTTPException(
            status_code=400,
            detail="Cannot add participants after invites have been sent",
        )

    # Check participant limit (5 max)
    if len(invite.get("participants", [])) >= 5:
        raise HTTPException(status_code=400, detail="Maximum 5 participants allowed")

    # Check if participant already exists
    existing_emails = [p["email"] for p in invite.get("participants", [])]
    if participant_data.email in existing_emails:
        raise HTTPException(status_code=400, detail="Participant already added")

    success = repo.add_participant(
        invite_id=invite_id,
        email=participant_data.email,
        first_name=participant_data.first_name,
        last_name=participant_data.last_name,
        collect_preferences=participant_data.collect_preferences,
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to add participant")

    # Return updated invite
    updated_invite = repo.get_trip_invite(invite_id)
    return TripInviteResponse(**updated_invite)


@router.put("/invites/{invite_id}/participants/{email}", response_model=TripInviteResponse)
async def update_participant(
    invite_id: str,
    email: str,
    participant_data: InviteParticipantUpdate,
    x_clerk_user_id: str = Header(..., alias="X-Clerk-User-Id"),
):
    """Update a participant's information."""
    clerk_user_id = x_clerk_user_id

    # Get invite and verify ownership
    invite = repo.get_trip_invite(invite_id)
    if not invite:
        raise HTTPException(status_code=404, detail="Trip invite not found")

    if invite["organizer_clerk_id"] != clerk_user_id:
        raise HTTPException(status_code=403, detail="Only the organizer can update participants")

    # Check if invites have been sent
    if invite["status"] != "draft":
        raise HTTPException(
            status_code=400,
            detail="Cannot update participants after invites have been sent",
        )

    success = repo.update_participant(
        invite_id=invite_id,
        old_email=email,
        new_email=participant_data.email,
        first_name=participant_data.first_name,
        last_name=participant_data.last_name,
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to update participant")

    # Return updated invite
    updated_invite = repo.get_trip_invite(invite_id)
    return TripInviteResponse(**updated_invite)


@router.patch("/invites/{invite_id}/participants/{email}/preferences")
async def update_participant_preferences(
    invite_id: str,
    email: str,
    request_body: dict,
    x_clerk_user_id: str = Header(..., alias="X-Clerk-User-Id"),
):
    """Update a participant's collect_preferences setting."""
    clerk_user_id = x_clerk_user_id

    # Get invite and verify ownership
    invite = repo.get_trip_invite(invite_id)
    if not invite:
        raise HTTPException(status_code=404, detail="Trip invite not found")

    if invite["organizer_clerk_id"] != clerk_user_id:
        raise HTTPException(
            status_code=403,
            detail="Only the organizer can update participant settings",
        )

    # Check if invites have been sent
    if invite["status"] != "draft":
        raise HTTPException(
            status_code=400,
            detail="Cannot update settings after invites have been sent",
        )

    collect_preferences = request_body.get("collect_preferences", False)

    # Update participant's collect_preferences
    success = repo.update_participant_collect_preferences(
        invite_id,
        email,
        collect_preferences,
    )

    if not success:
        raise HTTPException(status_code=404, detail="Participant not found")

    return {"message": "Participant preferences setting updated successfully"}


@router.delete("/invites/{invite_id}/participants/{email}", response_model=TripInviteResponse)
async def remove_participant(
    invite_id: str,
    email: str,
    x_clerk_user_id: str = Header(..., alias="X-Clerk-User-Id"),
):
    """Remove a participant from a trip invite."""
    clerk_user_id = x_clerk_user_id

    # Get invite and verify ownership
    invite = repo.get_trip_invite(invite_id)
    if not invite:
        raise HTTPException(status_code=404, detail="Trip invite not found")

    if invite["organizer_clerk_id"] != clerk_user_id:
        raise HTTPException(status_code=403, detail="Only the organizer can remove participants")

    # Check if invites have been sent
    if invite["status"] != "draft":
        raise HTTPException(
            status_code=400,
            detail="Cannot remove participants after invites have been sent",
        )

    success = repo.remove_participant(invite_id=invite_id, email=email)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to remove participant")

    # Return updated invite
    updated_invite = repo.get_trip_invite(invite_id)
    return TripInviteResponse(**updated_invite)


@router.post("/invites/{invite_id}/send")
async def send_invites(
    invite_id: str,
    request_data: SendInvitesRequest,
    x_clerk_user_id: str = Header(..., alias="X-Clerk-User-Id"),
):
    """Send invites to all participants via email."""
    from app.core.email_service import email_service

    clerk_user_id = x_clerk_user_id

    # Get invite and verify ownership
    invite = repo.get_trip_invite(invite_id)
    if not invite:
        raise HTTPException(status_code=404, detail="Trip invite not found")

    if invite["organizer_clerk_id"] != clerk_user_id:
        raise HTTPException(status_code=403, detail="Only the organizer can send invites")

    # Check if already sent
    if invite["status"] != "draft":
        raise HTTPException(status_code=400, detail="Invites have already been sent")

    # Check if there are participants
    if not invite.get("participants"):
        raise HTTPException(status_code=400, detail="No participants to send invites to")

    # Mark invites as sent first
    success = repo.mark_invites_sent(invite_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send invites")

    # Send emails to all participants
    from app.core.settings import get_settings

    settings = get_settings()
    organizer_name = invite.get("organizer_name") or "The trip organizer"
    trip_name = invite.get("trip_name", "Untitled Trip")
    destination = invite.get("destination")
    date_range_start = invite.get("date_range_start")
    date_range_end = invite.get("date_range_end")
    custom_message = request_data.message

    # Get frontend base URL from environment
    frontend_url = settings.frontend_url

    sent_count = 0
    failed_emails = []

    for participant in invite.get("participants", []):
        # Skip the organizer
        if participant.get("is_organizer"):
            continue

        recipient_email = participant.get("email")
        recipient_name = (
            f"{participant.get('first_name', '')} {participant.get('last_name', '')}".strip()
        )

        # Build invite link - participants can view and respond via the invite page
        invite_link = f"{frontend_url}/invite/{invite_id}"

        # Send the email
        email_sent = email_service.send_trip_invite(
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            organizer_name=organizer_name,
            trip_name=trip_name,
            destination=destination,
            date_range_start=date_range_start,
            date_range_end=date_range_end,
            custom_message=custom_message,
            invite_link=invite_link,
        )

        if email_sent:
            sent_count += 1
            # Update participant status to "invited"
            repo.update_participant_status(invite_id, recipient_email, "invited")
        else:
            failed_emails.append(recipient_email)

    # Build response message
    if failed_emails:
        message = f"Invites sent to {sent_count} participants. Failed to send to: {', '.join(failed_emails)}"
    else:
        message = f"Invites sent successfully to all {sent_count} participants"

    return {
        "message": message,
        "invite_id": invite_id,
        "participants_count": len(invite.get("participants", [])),
        "sent_count": sent_count,
        "failed_count": len(failed_emails),
        "failed_emails": failed_emails,
    }


@router.post("/invites/{invite_id}/respond")
async def respond_to_invite(
    invite_id: str,
    response_data: CalendarResponseSubmit,
    x_clerk_user_id: str = Header(..., alias="X-Clerk-User-Id"),
):
    """Submit availability response to a trip invite."""
    clerk_user_id = x_clerk_user_id

    # Get user email
    user = await repo.get_user_by_clerk_id(clerk_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Get invite
    invite = repo.get_trip_invite(invite_id)
    if not invite:
        raise HTTPException(status_code=404, detail="Trip invite not found")

    # Verify user is a participant
    participant_emails = [p["email"] for p in invite.get("participants", [])]
    if user.email not in participant_emails:
        raise HTTPException(status_code=403, detail="You are not a participant in this trip")

    # Submit response
    success = repo.submit_participant_response(
        invite_id=invite_id,
        participant_email=user.email,
        available_dates=response_data.available_dates,
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to submit response")

    return {
        "message": "Response submitted successfully",
        "invite_id": invite_id,
    }


@router.post("/invites/{invite_id}/preferences-completed")
async def mark_preferences_completed(
    invite_id: str,
    x_clerk_user_id: str = Header(..., alias="X-Clerk-User-Id"),
):
    """Mark that the participant has completed their preferences."""
    clerk_user_id = x_clerk_user_id

    # Get user email
    user = await repo.get_user_by_clerk_id(clerk_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Get invite
    invite = repo.get_trip_invite(invite_id)
    if not invite:
        raise HTTPException(status_code=404, detail="Trip invite not found")

    # Verify user is a participant
    participant_emails = [p["email"] for p in invite.get("participants", [])]
    if user.email not in participant_emails:
        raise HTTPException(status_code=403, detail="You are not a participant in this trip")

    # Mark preferences as completed
    success = repo.mark_participant_preferences_completed(
        invite_id=invite_id,
        participant_email=user.email,
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to mark preferences as completed")

    return {
        "message": "Preferences marked as completed",
        "invite_id": invite_id,
    }
