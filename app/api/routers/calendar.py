import logging
from datetime import datetime

from app.core.clerk_security import get_current_user_from_clerk
from app.core.repository import repo
from app.core.schemas import (
    CalendarResponseSubmit,
    FinalizeDatesRequest,
    InviteParticipantCreate,
    InviteParticipantUpdate,
    RejectInviteRequest,
    ResendInvitesRequest,
    SendInvitesRequest,
    TripInviteCreate,
    TripInviteResponse,
    UpdateParticipantPreferencesRequest,
    User,
)
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.post("/invites", response_model=TripInviteResponse)
async def create_trip_invite(
    invite_data: TripInviteCreate,
    current_user: User = Depends(get_current_user_from_clerk),
    request: Request = None,
):
    """Create a new trip invite."""
    from app.core.places_service import places_service

    clerk_user_id = current_user.clerk_user_id

    # Get user info from database
    user = await repo.get_user_by_clerk_id(clerk_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    organizer_email = user.email
    organizer_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or None

    # Fetch cover image if destination is provided
    cover_image_url = None
    if invite_data.destination:
        try:
            # Use empty string to get relative paths that work through nginx proxy
            base_url = ""
            cover_qs = [
                f"{invite_data.destination} skyline",
                f"{invite_data.destination} cityscape",
                f"{invite_data.destination} landmark",
            ]
            for q in cover_qs:
                res = places_service.search_places(
                    location=invite_data.destination, query=q
                )
                if res and res[0].get("photo_reference"):
                    url = places_service.get_proxy_photo_url(
                        res[0]["photo_reference"], base_url
                    )
                    if url:
                        cover_image_url = str(url)
                        break
        except Exception as e:
            logger.debug(f"Failed to fetch cover image for invite: {e}")
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


@router.get("/invites", response_model=list[TripInviteResponse])
async def get_my_invites(
    current_user: User = Depends(get_current_user_from_clerk),
):
    """Get all trip invites created by the authenticated user."""
    clerk_user_id = current_user.clerk_user_id
    invites = repo.get_user_trip_invites(clerk_user_id)
    return [TripInviteResponse(**invite) for invite in invites]


@router.get("/invites/received", response_model=list[TripInviteResponse])
async def get_received_invites(
    current_user: User = Depends(get_current_user_from_clerk),
):
    """Get all trip invites where the authenticated user is a participant."""
    clerk_user_id = current_user.clerk_user_id

    # Get user email
    user = await repo.get_user_by_clerk_id(clerk_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    invites = repo.get_received_invites(user.email)
    return [TripInviteResponse(**invite) for invite in invites]


@router.get("/invites/{invite_id}", response_model=TripInviteResponse)
async def get_trip_invite(
    invite_id: str = Path(
        ...,
        min_length=1,
        max_length=50,
        pattern="^[a-zA-Z0-9_-]+$",
        description="Invite ID",
    ),
    current_user: User = Depends(get_current_user_from_clerk),
):
    """Get a specific trip invite by ID."""
    invite = repo.get_trip_invite(invite_id)
    if not invite:
        raise HTTPException(status_code=404, detail="Trip invite not found")

    # Verify user has access (either organizer or participant)
    clerk_user_id = current_user.clerk_user_id
    user = await repo.get_user_by_clerk_id(clerk_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    is_organizer = invite["organizer_clerk_id"] == clerk_user_id
    is_participant = any(
        p["email"] == user.email for p in invite.get("participants", [])
    )

    if not (is_organizer or is_participant):
        raise HTTPException(status_code=403, detail="Access denied")

    return TripInviteResponse(**invite)


@router.delete("/invites/{invite_id}")
async def delete_trip_invite(
    invite_id: str = Path(
        ...,
        min_length=1,
        max_length=50,
        pattern="^[a-zA-Z0-9_-]+$",
        description="Invite ID",
    ),
    current_user: User = Depends(get_current_user_from_clerk),
):
    """Delete a trip invite."""
    clerk_user_id = current_user.clerk_user_id

    # Get invite and verify ownership
    invite = repo.get_trip_invite(invite_id)
    if not invite:
        raise HTTPException(status_code=404, detail="Trip invite not found")

    if invite["organizer_clerk_id"] != clerk_user_id:
        raise HTTPException(
            status_code=403, detail="Only the organizer can delete this invite"
        )

    success = repo.delete_trip_invite(invite_id)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete invite")

    return {"message": "Invite deleted successfully", "invite_id": invite_id}


@router.post("/invites/{invite_id}/participants", response_model=TripInviteResponse)
async def add_participant(
    invite_id: str = Path(
        ...,
        min_length=1,
        max_length=50,
        pattern="^[a-zA-Z0-9_-]+$",
        description="Invite ID",
    ),
    current_user: User = Depends(get_current_user_from_clerk),
    participant_data: InviteParticipantCreate = Body(...),
):
    """Add a participant to a trip invite."""
    clerk_user_id = current_user.clerk_user_id

    # Get invite and verify ownership
    invite = repo.get_trip_invite(invite_id)
    if not invite:
        raise HTTPException(status_code=404, detail="Trip invite not found")

    if invite["organizer_clerk_id"] != clerk_user_id:
        raise HTTPException(
            status_code=403, detail="Only the organizer can add participants"
        )

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
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to add participant")

    # Return updated invite
    updated_invite = repo.get_trip_invite(invite_id)
    return TripInviteResponse(**updated_invite)


@router.put(
    "/invites/{invite_id}/participants/{email}", response_model=TripInviteResponse
)
async def update_participant(
    invite_id: str = Path(
        ...,
        min_length=1,
        max_length=50,
        pattern="^[a-zA-Z0-9_-]+$",
        description="Invite ID",
    ),
    email: str = Path(..., pattern="^[^@]+@[^@]+\\.[^@]+$", description="Email"),
    participant_data: InviteParticipantUpdate = Body(...),
    current_user: User = Depends(get_current_user_from_clerk),
):
    """Update a participant's information."""
    clerk_user_id = current_user.clerk_user_id

    # Get invite and verify ownership
    invite = repo.get_trip_invite(invite_id)
    if not invite:
        raise HTTPException(status_code=404, detail="Trip invite not found")

    if invite["organizer_clerk_id"] != clerk_user_id:
        raise HTTPException(
            status_code=403, detail="Only the organizer can update participants"
        )

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


@router.delete(
    "/invites/{invite_id}/participants/{email}", response_model=TripInviteResponse
)
async def remove_participant(
    invite_id: str = Path(
        ...,
        min_length=1,
        max_length=50,
        pattern="^[a-zA-Z0-9_-]+$",
        description="Invite ID",
    ),
    email: str = Path(..., pattern="^[^@]+@[^@]+\\.[^@]+$", description="Email"),
    current_user: User = Depends(get_current_user_from_clerk),
):
    """Remove a participant from a trip invite."""
    clerk_user_id = current_user.clerk_user_id

    # Get invite and verify ownership
    invite = repo.get_trip_invite(invite_id)
    if not invite:
        raise HTTPException(status_code=404, detail="Trip invite not found")

    if invite["organizer_clerk_id"] != clerk_user_id:
        raise HTTPException(
            status_code=403, detail="Only the organizer can remove participants"
        )

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
    invite_id: str = Path(
        ...,
        min_length=1,
        max_length=50,
        pattern="^[a-zA-Z0-9_-]+$",
        description="Invite ID",
    ),
    request_data: SendInvitesRequest = Body(...),
    current_user: User = Depends(get_current_user_from_clerk),
):
    """Send invites to all participants."""
    clerk_user_id = current_user.clerk_user_id

    # Get invite and verify ownership
    invite = repo.get_trip_invite(invite_id)
    if not invite:
        raise HTTPException(status_code=404, detail="Trip invite not found")

    if invite["organizer_clerk_id"] != clerk_user_id:
        raise HTTPException(
            status_code=403, detail="Only the organizer can send invites"
        )

    # Check if already sent
    if invite["status"] != "draft":
        raise HTTPException(status_code=400, detail="Invites have already been sent")

    # Check if there are participants
    if not invite.get("participants"):
        raise HTTPException(
            status_code=400, detail="No participants to send invites to"
        )

    # Mark invites as sent
    success = repo.mark_invites_sent(invite_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send invites")

    # Send actual emails to all participants
    from app.core.email_service import send_trip_invite_email

    organizer_name = invite.get("organizer_name", "Trip Organizer")
    trip_name = invite.get("trip_name", "Group Trip")
    destination = invite.get("destination")
    date_range_start = invite.get("date_range_start")
    date_range_end = invite.get("date_range_end")

    sent_count = 0
    failed_emails = []

    for participant in invite.get("participants", []):
        if participant.get("is_organizer"):
            continue  # Skip organizer

        email = participant.get("email")
        if not email:
            continue

        try:
            # Extract first_name from participant
            recipient_first_name = participant.get("first_name", "").strip()

            send_trip_invite_email(
                to_email=email,
                invite_id=invite_id,
                organizer_name=organizer_name,
                trip_name=trip_name,
                destination=destination,
                date_range_start=date_range_start,
                date_range_end=date_range_end,
                recipient_first_name=(
                    recipient_first_name if recipient_first_name else None
                ),
            )
            sent_count += 1
        except Exception as e:
            logger.error(f"Failed to send email to {email}: {e}")
            failed_emails.append(email)

    return {
        "message": "Invites sent successfully",
        "invite_id": invite_id,
        "participants_count": len(invite.get("participants", [])),
        "sent_count": sent_count,
        "failed_count": len(failed_emails),
        "failed_emails": failed_emails,
    }


@router.post("/invites/{invite_id}/respond")
async def respond_to_invite(
    invite_id: str = Path(
        ...,
        min_length=1,
        max_length=50,
        pattern="^[a-zA-Z0-9_-]+$",
        description="Invite ID",
    ),
    response_data: CalendarResponseSubmit = Body(...),
    current_user: User = Depends(get_current_user_from_clerk),
):
    """Submit availability response to a trip invite."""
    from app.core.invite_utils import analyze_common_dates

    clerk_user_id = current_user.clerk_user_id

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
        raise HTTPException(
            status_code=403, detail="You are not a participant in this trip"
        )

    # Submit response
    success = repo.submit_participant_response(
        invite_id=invite_id,
        participant_email=user.email,
        available_dates=response_data.available_dates,
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to submit response")

    # Trigger date analysis
    updated_invite = repo.get_trip_invite(invite_id)
    if updated_invite:
        participants = updated_invite.get("participants", [])
        analysis_results = analyze_common_dates(participants)

        # Update invite with analysis results
        repo.update_invite_date_analysis(
            invite_id=invite_id,
            calculated_start_date=analysis_results.get("calculated_start_date"),
            calculated_end_date=analysis_results.get("calculated_end_date"),
            no_common_dates=analysis_results.get("no_common_dates", False),
            common_dates_percentage=analysis_results.get("common_dates_percentage"),
        )

    return {
        "message": "Response submitted successfully",
        "invite_id": invite_id,
    }


@router.post("/invites/{invite_id}/preferences-completed")
async def mark_preferences_completed(
    invite_id: str = Path(
        ...,
        min_length=1,
        max_length=50,
        pattern="^[a-zA-Z0-9_-]+$",
        description="Invite ID",
    ),
    current_user: User = Depends(get_current_user_from_clerk),
):
    """Mark that the participant has completed their preferences."""
    clerk_user_id = current_user.clerk_user_id

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
        raise HTTPException(
            status_code=403, detail="You are not a participant in this trip"
        )

    # Mark preferences as completed
    success = repo.mark_participant_preferences_completed(
        invite_id=invite_id,
        participant_email=user.email,
    )

    if not success:
        raise HTTPException(
            status_code=500, detail="Failed to mark preferences as completed"
        )

    return {
        "message": "Preferences marked as completed",
        "invite_id": invite_id,
    }


@router.post("/invites/{invite_id}/finalize-dates")
async def finalize_invite_dates(
    invite_id: str = Path(
        ...,
        min_length=1,
        max_length=50,
        pattern="^[a-zA-Z0-9_-]+$",
        description="Invite ID",
    ),
    request_data: FinalizeDatesRequest = Body(...),
    current_user: User = Depends(get_current_user_from_clerk),
):
    """Finalize dates for a trip invite (organizer only)."""
    clerk_user_id = current_user.clerk_user_id

    # Get invite
    invite = repo.get_trip_invite(invite_id)
    if not invite:
        raise HTTPException(status_code=404, detail="Trip invite not found")

    # Verify user is the organizer
    if invite.get("organizer_clerk_id") != clerk_user_id:
        raise HTTPException(
            status_code=403, detail="Only the organizer can finalize dates"
        )

    participants = invite.get("participants", [])
    organizer_participant = next(
        (p for p in participants if p.get("is_organizer")),
        None,
    )
    non_organizer_participants = [p for p in participants if not p.get("is_organizer")]

    # Organizer must submit availability
    if not organizer_participant or organizer_participant.get("status") != "responded":
        raise HTTPException(
            status_code=400,
            detail="Organizer must submit availability before finalizing dates",
        )

    if non_organizer_participants:
        if any(p.get("status") != "responded" for p in non_organizer_participants):
            raise HTTPException(
                status_code=400,
                detail="All participants must respond before finalizing dates",
            )

        if invite.get("collect_preferences") and any(
            not p.get("has_completed_preferences") for p in non_organizer_participants
        ):
            raise HTTPException(
                status_code=400,
                detail="All participants must complete preferences before finalizing dates",
            )

    # Determine which dates to use
    if request_data.use_common:
        # Use calculated common dates
        start_date = invite.get("calculated_start_date")
        end_date = invite.get("calculated_end_date")

        if not start_date or not end_date:
            raise HTTPException(
                status_code=400,
                detail="No common dates available. Please use your own dates instead.",
            )

        finalized_by = "common"
    else:
        # Use organizer's dates (from their participant record)
        organizer_email = invite.get("organizer_email")
        organizer_record = next(
            (
                p
                for p in participants
                if p.get("email") == organizer_email and p.get("is_organizer")
            ),
            None,
        )

        if not organizer_record or not organizer_record.get("available_dates"):
            raise HTTPException(
                status_code=400, detail="Organizer must submit their availability first"
            )

        # Use first and last date from organizer's availability
        organizer_dates = sorted(organizer_record["available_dates"])
        start_date = organizer_dates[0]
        end_date = organizer_dates[-1]
        finalized_by = "organizer"

    # Finalize the dates
    success = repo.finalize_invite_dates(
        invite_id=invite_id,
        finalized_start_date=start_date,
        finalized_end_date=end_date,
        dates_finalized_by=finalized_by,
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to finalize dates")

    return {
        "message": "Dates finalized successfully",
        "invite_id": invite_id,
        "finalized_start_date": start_date,
        "finalized_end_date": end_date,
        "dates_finalized_by": finalized_by,
    }


@router.post("/invites/{invite_id}/resend")
async def resend_invites(
    invite_id: str = Path(
        ...,
        min_length=1,
        max_length=50,
        pattern="^[a-zA-Z0-9_-]+$",
        description="Invite ID",
    ),
    request_data: ResendInvitesRequest = Body(...),
    current_user: User = Depends(get_current_user_from_clerk),
):
    """Resend invites to selected participants (organizer only)."""
    from app.core.email_service import send_trip_invite_email

    clerk_user_id = current_user.clerk_user_id

    # Get invite
    invite = repo.get_trip_invite(invite_id)
    if not invite:
        raise HTTPException(status_code=404, detail="Trip invite not found")

    # Verify user is the organizer
    if invite.get("organizer_clerk_id") != clerk_user_id:
        raise HTTPException(
            status_code=403, detail="Only the organizer can resend invites"
        )

    # Verify all emails are participants (not organizer)
    participant_emails = [
        p["email"] for p in invite.get("participants", []) if not p.get("is_organizer")
    ]

    if not request_data.participant_emails:
        raise HTTPException(status_code=400, detail="No participant emails provided")

    for email in request_data.participant_emails:
        if email not in participant_emails:
            raise HTTPException(
                status_code=400, detail=f"Email {email} is not a valid participant"
            )

    # Reset participants
    success = repo.reset_participants_for_resend(
        invite_id=invite_id,
        participant_emails=request_data.participant_emails,
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to reset participants")

    # Send new invite emails
    organizer_name = invite.get("organizer_name", "Trip Organizer")
    trip_name = invite.get("trip_name", "Group Trip")

    sent_count = 0
    failed_emails = []

    for email in request_data.participant_emails:
        try:
            # Find participant to get first_name
            participant = next(
                (p for p in invite.get("participants", []) if p.get("email") == email),
                None,
            )
            recipient_first_name = (
                participant.get("first_name", "").strip() if participant else None
            )

            send_trip_invite_email(
                to_email=email,
                invite_id=invite_id,
                organizer_name=organizer_name,
                trip_name=trip_name,
                recipient_first_name=(
                    recipient_first_name if recipient_first_name else None
                ),
            )
            sent_count += 1
        except Exception as e:
            logger.error(f"Failed to send email to {email}: {e}", exc_info=True)
            failed_emails.append(email)

    # Recalculate date analysis after resend
    from app.core.invite_utils import analyze_common_dates

    updated_invite = repo.get_trip_invite(invite_id)
    if updated_invite:
        participants = updated_invite.get("participants", [])
        analysis_results = analyze_common_dates(participants)

        repo.update_invite_date_analysis(
            invite_id=invite_id,
            calculated_start_date=analysis_results.get("calculated_start_date"),
            calculated_end_date=analysis_results.get("calculated_end_date"),
            no_common_dates=analysis_results.get("no_common_dates", False),
            common_dates_percentage=analysis_results.get("common_dates_percentage"),
        )

    return {
        "message": f"Invites resent to {sent_count} participant(s)",
        "invite_id": invite_id,
        "sent_count": sent_count,
        "failed_count": len(failed_emails),
        "failed_emails": failed_emails,
    }


@router.post("/invites/{invite_id}/reject")
async def reject_invite(
    invite_id: str = Path(
        ...,
        min_length=1,
        max_length=50,
        pattern="^[a-zA-Z0-9_-]+$",
        description="Invite ID",
    ),
    reject_data: RejectInviteRequest = Body(...),
    current_user: User = Depends(get_current_user_from_clerk),
):
    """Reject/decline a trip invite (participant only)."""
    clerk_user_id = current_user.clerk_user_id

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
    user_email = reject_data.email or user.email

    if user_email not in participant_emails:
        raise HTTPException(
            status_code=403, detail="You are not a participant in this trip"
        )

    # Update participant status to declined
    participants = invite.get("participants", [])
    for participant in participants:
        if participant["email"] == user_email:
            participant["status"] = "declined"
            break

    # Update invite
    result = repo.trip_invites_collection.update_one(
        {"id": invite_id},
        {
            "$set": {
                "participants": participants,
                "updated_at": datetime.utcnow(),
            }
        },
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=500, detail="Failed to reject invite")

    return {
        "message": "Invite declined successfully",
        "invite_id": invite_id,
    }


@router.patch("/invites/{invite_id}/participants/{email}/preferences")
async def update_participant_preferences_setting(
    invite_id: str = Path(
        ...,
        min_length=1,
        max_length=50,
        pattern="^[a-zA-Z0-9_-]+$",
        description="Invite ID",
    ),
    email: str = Path(..., pattern="^[^@]+@[^@]+\\.[^@]+$", description="Email"),
    preference_data: UpdateParticipantPreferencesRequest = Body(...),
    current_user: User = Depends(get_current_user_from_clerk),
):
    """Update whether to collect preferences from a specific participant."""
    clerk_user_id = current_user.clerk_user_id

    # Get invite and verify ownership
    invite = repo.get_trip_invite(invite_id)
    if not invite:
        raise HTTPException(status_code=404, detail="Trip invite not found")

    if invite["organizer_clerk_id"] != clerk_user_id:
        raise HTTPException(
            status_code=403, detail="Only the organizer can update preference settings"
        )

    # Update participant's collect_preferences flag
    participants = invite.get("participants", [])
    participant_found = False

    for participant in participants:
        if participant["email"] == email:
            participant["collect_preferences"] = preference_data.collect_preferences
            participant_found = True
            break

    if not participant_found:
        raise HTTPException(status_code=404, detail="Participant not found")

    # Update invite
    result = repo.trip_invites_collection.update_one(
        {"id": invite_id},
        {
            "$set": {
                "participants": participants,
                "updated_at": datetime.utcnow(),
            }
        },
    )

    if result.modified_count == 0:
        raise HTTPException(
            status_code=500, detail="Failed to update preference setting"
        )

    updated_invite = repo.get_trip_invite(invite_id)
    return TripInviteResponse(**updated_invite)
