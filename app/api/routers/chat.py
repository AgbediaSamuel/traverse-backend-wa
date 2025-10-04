from __future__ import annotations

import time
import uuid
from typing import Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.conversation_manager import ConversationManager, ConversationState


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(system|user|assistant)$")
    content: str
    ts: float = Field(default_factory=lambda: time.time())


class ChatSession(BaseModel):
    id: str
    user_id: Optional[str] = None
    messages: List[ChatMessage] = Field(default_factory=list)
    conversation_state: ConversationState = Field(default_factory=ConversationState)


class MessageRequest(BaseModel):
    content: str


router = APIRouter(prefix="/chat", tags=["chat"])

_SESSIONS: Dict[str, ChatSession] = {}
_conversation_manager = ConversationManager()


@router.post("/sessions")
def create_session(user_id: Optional[str] = None, request: Request = None) -> Dict[str, str]:
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


@router.post("/sessions/{session_id}/messages")
async def post_message(session_id: str, req: MessageRequest, request: Request) -> Dict[str, object]:
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

    # Generate response using conversation manager
    response_text, updated_state, should_generate = _conversation_manager.generate_response(
        user_message=req.content,
        state=session.conversation_state,
        conversation_history=conversation_history[:-1],  # Exclude current message
    )

    # Update session state
    session.conversation_state = updated_state

    # Add assistant response to messages
    assistant_msg = ChatMessage(role="assistant", content=response_text)
    session.messages.append(assistant_msg)

    # If we should generate itinerary, do it now
    itinerary_generated = False
    if should_generate:
        try:
            payload = {
                "traveler_name": updated_state.traveler_name,
                "destination": updated_state.destination,
                "dates": updated_state.dates,
                "duration": updated_state.duration,
            }

            async with httpx.AsyncClient(timeout=45) as client:
                resp = await client.post(
                    "http://localhost:8000/itineraries/generate",
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()

                itinerary_id = data.get("id") or data.get("itineraryId")
                if itinerary_id:
                    session.conversation_state.itinerary_id = itinerary_id
                    # Update repository session
                    request.app.state.repo.update_session(
                        session_id, {"itinerary_id": itinerary_id}
                    )
                    itinerary_generated = True

                    # Add follow-up message with itinerary link
                    follow_up = ChatMessage(
                        role="assistant",
                        content=f"✅ Your itinerary has been generated! View it at: http://localhost:8000/itineraries/{itinerary_id}",
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
            f"http://localhost:8000/itineraries/{session.conversation_state.itinerary_id}"
        )

    return result


@router.post("/sessions/{session_id}/finalize")
async def finalize(session_id: str, request: Request) -> Dict[str, object]:
    session = _SESSIONS.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")

    # Check if we have all required information
    if not session.conversation_state.is_complete():
        missing = session.conversation_state.get_missing_fields()
        return {
            "message": {
                "role": "assistant",
                "content": f"I still need the following information: {', '.join(missing)}. Please provide these details.",
            },
            "state": session.conversation_state.model_dump(),
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
                "http://localhost:8000/itineraries/generate",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

            itinerary_id = data.get("id") or data.get("itineraryId")
            if itinerary_id:
                session.conversation_state.itinerary_id = itinerary_id
                # Update repository session
                request.app.state.repo.update_session(session_id, {"itinerary_id": itinerary_id})

                response_text = f"Perfect! Your itinerary has been generated. You can view it using ID: {itinerary_id}"
            else:
                response_text = "Your itinerary has been generated successfully!"

        return {
            "message": {"role": "assistant", "content": response_text},
            "state": session.conversation_state.model_dump(),
        }
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
