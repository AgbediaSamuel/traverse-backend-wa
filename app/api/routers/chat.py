from __future__ import annotations

import time
import uuid
from datetime import datetime
from typing import Dict, List, Optional

import httpx
from app.core.conversation_manager import ConversationManager, ConversationState
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(system|user|assistant)$")
    content: str
    ts: float = Field(default_factory=lambda: time.time())


class ChatSession(BaseModel):
    id: str
    user_id: Optional[str] = None
    trip_type: Optional[str] = Field(None, pattern="^(solo|group)$")
    messages: List[ChatMessage] = Field(default_factory=list)
    conversation_state: ConversationState = Field(default_factory=ConversationState)


class MessageRequest(BaseModel):
    content: str


router = APIRouter(prefix="/chat", tags=["chat"])

_SESSIONS: Dict[str, ChatSession] = {}
_conversation_manager = ConversationManager()


@router.get("/sessions/active")
def get_active_session(
    clerk_user_id: str, trip_type: Optional[str] = None, request: Request = None
) -> Dict[str, object]:
    """
    Get or create the active chat session for a user.
    This ensures each user only has one active session at a time.
    """
    # Get from database
    db_session = request.app.state.repo.get_active_session(clerk_user_id, trip_type=trip_type)

    # Initialize in-memory session if not already loaded
    if db_session["id"] not in _SESSIONS:
        # Reconstruct conversation state from database
        state_dict = db_session.get("conversation_state", {})
        conversation_state = ConversationState(**state_dict) if state_dict else ConversationState()

        # Reconstruct messages
        messages = [ChatMessage(**msg) for msg in db_session.get("messages", [])]

        session = ChatSession(
            id=db_session["id"],
            user_id=clerk_user_id,
            trip_type=db_session.get("trip_type"),
            messages=messages,
            conversation_state=conversation_state,
        )
        _SESSIONS[db_session["id"]] = session

    return {"session": _SESSIONS[db_session["id"]]}


@router.post("/sessions")
def create_session(user_id: Optional[str] = None, request: Request = None) -> Dict[str, str]:
    """Legacy endpoint - deprecated in favor of /sessions/active"""
    sid = f"sess_{uuid.uuid4().hex[:12]}"
    session = ChatSession(id=sid, user_id=user_id)
    _SESSIONS[sid] = session
    request.app.state.repo.create_session({"id": sid, "user_id": user_id})
    return {"sessionId": sid}


@router.get("/sessions/{session_id}")
def get_session(session_id: str, request: Request) -> Dict[str, object]:
    session = _SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    return {"session": session}


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, request: Request) -> Dict[str, str]:
    """Delete a session from memory and database."""
    # Remove from memory
    if session_id in _SESSIONS:
        del _SESSIONS[session_id]

    # Delete from database
    try:
        request.app.state.repo.sessions_collection.delete_one({"id": session_id})
        return {"message": "Session deleted successfully"}
    except Exception as e:
        print(f"Error deleting session: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete session")


@router.post("/sessions/{session_id}/messages")
async def post_message(
    session_id: str, req: MessageRequest, request: Request
) -> Dict[str, object]:
    session = _SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    user_msg = ChatMessage(role="user", content=req.content)
    session.messages.append(user_msg)

    # Build conversation history for context
    conversation_history = [
        {"role": msg.role, "content": msg.content}
        for msg in session.messages[-10:]  # Last 10 messages
    ]

    # Get user context from session
    user_first_name = None
    if session.user_id:
        # Try to get user from database
        try:
            user_data = await request.app.state.repo.get_user_by_clerk_id(session.user_id)
            if user_data:
                user_first_name = user_data.first_name
        except Exception as e:
            print(f"Could not fetch user data: {e}")

    # Get current date and day
    now = datetime.now()
    current_date = now.strftime("%Y-%m-%d")
    current_day = now.strftime("%A")

    # Generate response using conversation manager
    response_text, updated_state, should_generate = _conversation_manager.generate_response(
        user_message=req.content,
        state=session.conversation_state,
        conversation_history=conversation_history[:-1],  # Exclude current message
        user_first_name=user_first_name,
        current_date=current_date,
        current_day=current_day,
    )

    # Update session state
    session.conversation_state = updated_state

    # Add assistant response to messages
    assistant_msg = ChatMessage(role="assistant", content=response_text)
    session.messages.append(assistant_msg)

    # Persist messages and state to database
    request.app.state.repo.update_session(
        session_id,
        {
            "messages": [msg.model_dump() for msg in session.messages],
            "conversation_state": updated_state.model_dump(),
            "updated_at": time.time(),
        },
    )

    # If we should generate itinerary, do it now
    itinerary_generated = False
    if should_generate:
        try:
            payload = {
                "traveler_name": updated_state.traveler_name,
                "destination": updated_state.destination,
                "dates": updated_state.dates,
                "duration": updated_state.duration,
                "clerk_user_id": session.user_id,
            }

            async with httpx.AsyncClient(timeout=45) as client:
                resp = await client.post(
                    "http://localhost:8765/itineraries/generate",
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()

                itinerary_id = data.get("id") or data.get("itineraryId")
                if itinerary_id:
                    session.conversation_state.itinerary_id = itinerary_id

                    # Finalize session and create new active one
                    request.app.state.repo.finalize_session(session_id, itinerary_id)

                    # Clear old session from memory
                    if session_id in _SESSIONS:
                        del _SESSIONS[session_id]

                    itinerary_generated = True

                    # Add follow-up message with success
                    destination = updated_state.destination or "your destination"
                    follow_up = ChatMessage(
                        role="assistant",
                        content=f"✅ Perfect! Your itinerary for {destination} has been created! Redirecting you to view your trips...",
                    )
                    session.messages.append(follow_up)
        except Exception as e:
            print(f"Error generating itinerary: {e}")
            error_msg = ChatMessage(
                role="assistant",
                content="I encountered an error generating your itinerary. Please try again.",
            )
            session.messages.append(error_msg)

    result = {
        "message": {"role": "assistant", "content": response_text},
        "state": session.conversation_state.model_dump(),
    }

    # Include itinerary_id in response if generated
    if itinerary_generated and session.conversation_state.itinerary_id:
        result["itinerary_id"] = session.conversation_state.itinerary_id
        result["itinerary_url"] = (
            f"http://localhost:5174/?itineraryId={session.conversation_state.itinerary_id}"
        )

    return result


@router.post("/sessions/{session_id}/finalize")
async def finalize(session_id: str, request: Request) -> Dict[str, object]:
    """
    Finalize the current session by:
    1. Generating the itinerary
    2. Marking the session as finalized
    3. Creating a new active session for the user
    """
    session = _SESSIONS.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")

    # Check if we have all required information
    if not session.conversation_state.is_complete():
        missing = session.conversation_state.get_missing_fields()
        return {
            "error": True,
            "message": f"I still need the following information: {', '.join(missing)}. Please provide these details.",
            "missing_fields": missing,
        }

    # Generate itinerary
    try:
        payload = {
            "traveler_name": session.conversation_state.traveler_name,
            "destination": session.conversation_state.destination,
            "dates": session.conversation_state.dates,
            "duration": session.conversation_state.duration,
        }

        async with httpx.AsyncClient(timeout=45) as client:
            resp = await client.post(
                "http://localhost:8765/itineraries/generate",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

            itinerary_id = data.get("id") or data.get("itineraryId")
            if not itinerary_id:
                raise HTTPException(
                    status_code=502,
                    detail="Itinerary generated but no ID returned",
                )

            # Finalize session and create new active one
            new_session_id = request.app.state.repo.finalize_session(session_id, itinerary_id)

            # Clear old session from memory
            if session_id in _SESSIONS:
                del _SESSIONS[session_id]

            itinerary_url = f"http://localhost:5174/?itineraryId={itinerary_id}"

            return {
                "success": True,
                "message": "Your itinerary has been created! A new chat session is ready for your next trip.",
                "itinerary_id": itinerary_id,
                "itinerary_url": itinerary_url,
                "new_session_id": new_session_id,
            }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error generating itinerary: {e}")
        raise HTTPException(
            status_code=502,
            detail="Failed to generate itinerary",
        )


@router.get("/sessions")
def list_sessions(request: Request) -> Dict[str, object]:
    return {"sessions": list(request.app.state.repo.sessions.values())}


@router.get("/sessions/{session_id}/itinerary")
def get_session_itinerary(session_id: str, request: Request) -> Dict[str, object]:
    data = request.app.state.repo.get_session(session_id)
    if not data:
        raise HTTPException(status_code=404, detail="session not found")
    return {"itineraryId": data.get("itinerary_id")}
