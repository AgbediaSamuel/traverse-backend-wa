from __future__ import annotations

import time
import uuid
from typing import Dict, Optional

from app.core.schemas import ItineraryDocument


class InMemoryRepo:
    def __init__(self) -> None:
        self.sessions: Dict[str, dict] = {}
        self.itineraries: Dict[str, dict] = {}

    # Sessions
    def create_session(self, session: dict) -> None:
        self.sessions[session["id"]] = {**session, "created_at": time.time()}

    def get_session(self, session_id: str) -> Optional[dict]:
        return self.sessions.get(session_id)

    def update_session(self, session_id: str, data: dict) -> None:
        if session_id in self.sessions:
            self.sessions[session_id].update(data)

    # Itineraries
    def save_itinerary(self, doc: ItineraryDocument, session_id: str | None = None) -> str:
        itn_id = f"itn_{uuid.uuid4().hex[:12]}"
        self.itineraries[itn_id] = {
            "id": itn_id,
            "document": doc.model_dump(mode="json"),
            "session_id": session_id,
            "created_at": time.time(),
        }
        return itn_id

    def get_itinerary(self, itinerary_id: str) -> Optional[dict]:
        return self.itineraries.get(itinerary_id)


repo = InMemoryRepo()
