from __future__ import annotations

import json
import time
import uuid
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.schemas import ItineraryDocument


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(system|user|assistant)$")
    content: str
    ts: float = Field(default_factory=lambda: time.time())


class ChatSession(BaseModel):
    id: str
    user_id: Optional[str] = None
    messages: List[ChatMessage] = Field(default_factory=list)
    status: str = Field(default="collecting")


class Checklist(BaseModel):
    missing: List[str] = Field(default_factory=list)
    ready: bool = False


class MessageRequest(BaseModel):
    content: str


router = APIRouter(prefix="/chat", tags=["chat"])

_SESSIONS: Dict[str, ChatSession] = {}
_PROVIDER = None  # deprecated; use request.app.state.llm_provider


def _compute_checklist(messages: List[ChatMessage]) -> Checklist:
    # Simplified placeholder: look for obvious keys in the transcript
    transcript = "\n".join(m.content.lower() for m in messages if m.role != "system")
    required = ["destination", "dates", "duration"]
    missing = [k for k in required if k not in transcript]
    return Checklist(missing=missing, ready=len(missing) == 0)


def _provider_chat_or_http_error(messages: List[dict], temperature: float, request: Request) -> str:
    try:
        provider = request.app.state.llm_provider
        return provider.chat(messages=messages, temperature=temperature)
    except Exception as exc:  # surface provider errors for easier debugging
        raise HTTPException(status_code=502, detail={"provider_error": str(exc)})


def _parse_itinerary_json_or_502(raw_text: str) -> ItineraryDocument:
    """Parse model output into ItineraryDocument; tolerate common wrappers like code fences."""
    text = raw_text.strip()
    # Try direct parse first
    try:
        return ItineraryDocument.model_validate_json(text)
    except Exception:
        pass

    # Strip markdown code fences ```json ... ``` or ``` ... ```
    if text.startswith("```"):
        # Drop leading backticks and optional language tag
        body = text.lstrip("`")
        if body.lower().startswith("json"):
            body = body[4:]
        body = body.lstrip("\n ")
        if body.endswith("```"):
            body = body[:-3]
        text = body.strip()

    # Try direct parse again
    try:
        return ItineraryDocument.model_validate_json(text)
    except Exception:
        pass

    # Try loading as JSON and normalizing fields
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            # Normalize dates: support { start, end } → "start - end"
            dates_value = data.get("dates")
            if isinstance(dates_value, dict):
                start = dates_value.get("start") or ""
                end = dates_value.get("end") or ""
                if start or end:
                    data["dates"] = f"{start} - {end}".strip()
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
                dates_value = data.get("dates")
                if isinstance(dates_value, dict):
                    start = dates_value.get("start") or ""
                    end = dates_value.get("end") or ""
                    if start or end:
                        data["dates"] = f"{start} - {end}".strip()
                return ItineraryDocument.model_validate(data)
        except Exception:
            pass

    raise HTTPException(
        status_code=502, detail={"provider_error": "Schema validation failed", "raw": raw_text}
    )


@router.post("/sessions")
def create_session(user_id: Optional[str] = None, request: Request = None) -> Dict[str, str]:
    sid = f"sess_{uuid.uuid4().hex[:12]}"
    session = ChatSession(
        id=sid,
        user_id=user_id,
        messages=[
            ChatMessage(
                role="system",
                content=(
                    """You are a travel planner. Collect only fields required for an ItineraryDocument:
                    - traveler_name (string)
                    - destination (string)
                    - dates (string, e.g., "YYYY-MM-DD - YYYY-MM-DD")
                    - duration (string, e.g., "3 days")
                    - cover_image (string URL or null)
                    - days (array of { date: string, activities: array of { time, title, location, description, image } })
                    - notes (array of strings)

                    Rules:
                    - Ask concise, targeted questions to fill missing fields.
                    - Do NOT output any JSON or the final itinerary in the chat.
                    - When all required fields are present, acknowledge readiness briefly and wait.
                    """
                ),
            )
        ],
    )
    _SESSIONS[sid] = session
    request.app.state.repo.create_session(session.model_dump())
    return {"sessionId": sid}


@router.get("/sessions/{session_id}")
def get_session(session_id: str, request: Request) -> Dict[str, object]:
    session = _SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    checklist = _compute_checklist(session.messages)
    return {"session": session, "checklist": checklist}


@router.post("/sessions/{session_id}/messages")
def post_message(session_id: str, req: MessageRequest, request: Request) -> Dict[str, object]:
    session = _SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    user_msg = ChatMessage(role="user", content=req.content)
    session.messages.append(user_msg)

    # Check readiness BEFORE generating the assistant reply
    checklist = _compute_checklist(session.messages)

    # If ready and not yet finalized, have the model say the closing line, then finalize
    if checklist.ready and session.status != "finalized":
        closing_system = ChatMessage(
            role="system",
            content=(
                "All required fields have been collected. Respond with a single short line "
                "acknowledging readiness (e.g., 'I've got everything I need—generating your "
                "itinerary now.') and do not ask further questions."
            ),
        )
        session.messages.append(closing_system)
        provider_messages = [m.model_dump() for m in session.messages]
        closing_text = _provider_chat_or_http_error(
            provider_messages, temperature=0, request=request
        )
        closing_msg = ChatMessage(role="assistant", content=closing_text)
        session.messages.append(closing_msg)

        # Finalize: ask model for strict JSON, validate, store
        session.status = "finalized"
        json_system = ChatMessage(
            role="system",
            content=(
                "Now output ONLY a valid JSON object matching the ItineraryDocument schema: "
                "{traveler_name, destination, dates, duration, cover_image, days:[{date,"
                " activities:[{time,title,location,description,image}]}], notes:[string]}."
                " No prose, no backticks."
            ),
        )
        session.messages.append(json_system)
        provider_messages = [m.model_dump() for m in session.messages]
        json_text = _provider_chat_or_http_error(provider_messages, temperature=0, request=request)

        doc = _parse_itinerary_json_or_502(json_text)

        itinerary_id = request.app.state.repo.save_itinerary(doc, session_id=session.id)
        request.app.state.repo.update_session(
            session.id, {"status": session.status, "itinerary_id": itinerary_id}
        )
        return {
            "message": closing_msg,
            "checklist": checklist,
            "finalized": True,
            "itineraryId": itinerary_id,
            "document": doc,
            "raw": json_text,
        }

    # Otherwise, proceed with normal assistant turn
    provider_messages = [m.model_dump() for m in session.messages]
    answer = _provider_chat_or_http_error(provider_messages, temperature=0, request=request)
    assistant_msg = ChatMessage(role="assistant", content=answer)
    session.messages.append(assistant_msg)

    checklist = _compute_checklist(session.messages)
    return {"message": assistant_msg, "checklist": checklist, "finalized": False}


@router.post("/sessions/{session_id}/finalize")
def finalize(session_id: str, request: Request) -> Dict[str, object]:
    session = _SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    checklist = _compute_checklist(session.messages)
    if not checklist.ready:
        raise HTTPException(status_code=400, detail={"missing": checklist.missing})
    # Ask model for strict JSON itinerary, validate, and persist
    session.status = "finalized"
    json_system = ChatMessage(
        role="system",
        content=(
            "Now output ONLY a valid JSON object matching the ItineraryDocument schema: "
            "{traveler_name, destination, dates, duration, cover_image, days:[{date,"
            " activities:[{time,title,location,description,image}]}], notes:[string]}."
            " No prose, no backticks."
        ),
    )
    session.messages.append(json_system)
    provider_messages = [m.model_dump() for m in session.messages]
    json_text = _provider_chat_or_http_error(provider_messages, temperature=0, request=request)

    doc = _parse_itinerary_json_or_502(json_text)

    itinerary_id = request.app.state.repo.save_itinerary(doc, session_id=session.id)
    request.app.state.repo.update_session(
        session.id, {"status": session.status, "itinerary_id": itinerary_id}
    )
    return {"finalized": True, "itineraryId": itinerary_id, "document": doc, "raw": json_text}


@router.get("/sessions")
def list_sessions(request: Request) -> Dict[str, object]:
    return {"sessions": list(request.app.state.repo.sessions.values())}


@router.get("/sessions/{session_id}/itinerary")
def get_session_itinerary(session_id: str, request: Request) -> Dict[str, object]:
    data = request.app.state.repo.get_session(session_id)
    if not data:
        raise HTTPException(status_code=404, detail="session not found")
    return {"itineraryId": data.get("itinerary_id")}
