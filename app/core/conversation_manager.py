from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from app.core.llm_provider import LLMProvider
from app.core.settings import get_settings


class ConversationState(BaseModel):
    """Tracks the state of an itinerary planning conversation."""

    # Collected information
    traveler_name: Optional[str] = None
    destination: Optional[str] = None
    dates: Optional[str] = None
    duration: Optional[str] = None

    # Conversation metadata
    itinerary_id: Optional[str] = None
    last_question: Optional[str] = None

    def is_complete(self) -> bool:
        """Check if we have all required information to generate itinerary."""
        return bool(self.traveler_name and self.destination and self.dates)

    def get_missing_fields(self) -> List[str]:
        """Get list of required fields that are still missing."""
        missing = []
        if not self.traveler_name:
            missing.append("traveler_name")
        if not self.destination:
            missing.append("destination")
        if not self.dates:
            missing.append("dates")
        return missing


class ConversationManager:
    """Manages itinerary planning conversations using LLM for NLU and dialogue management."""

    def __init__(self, model: Optional[str] = None):
        settings = get_settings()
        self.model = model or settings.aisuite_model
        self.provider = LLMProvider(model=self.model)

    def extract_fields(
        self, text: str, last_assistant_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """Extract itinerary-related fields from user input using LLM."""
        system_prompt = {
            "role": "system",
            "content": (
                "You are extracting travel planning information from user messages.\n\n"
                "FIRST, classify the message intent:\n"
                "- 'conversational': greetings, acknowledgments, thanks, yes/no without info (e.g., 'hello', 'thanks', 'sounds good', 'yup', 'ok')\n"
                "- 'informational': contains actual trip planning details (name, destination, dates, duration)\n"
                "\n"
                "IF the message is 'conversational', return: {}\n"
                "IF the message is 'informational', extract these fields if present:\n"
                "- traveler_name (string|null): the traveler's name\n"
                "- destination (string|null): where they want to go\n"
                "- dates (string|null): full date range if provided (e.g., 'August 15-20, 2025')\n"
                "- start_date (string|null): starting date if only start is mentioned (e.g., 'August 15th 2025')\n"
                "- duration_days (integer|null): number of days if mentioned\n"
                "- duration (string|null): duration as text (e.g., '5 days', 'one week')\n"
                "\n"
                "Important for dates:\n"
                "- If user provides a full date range, extract as 'dates'\n"
                "- If user provides only a start date, extract as 'start_date'\n"
                "- If user mentions duration, extract both 'duration_days' (number) and 'duration' (text)\n"
                "\n"
                "Context helps: If the assistant just asked for the traveler's name and user responds with a single word, that's likely the name.\n"
                "If assistant asked for destination and user says a place name, that's the destination, etc.\n"
                "\n"
                "Return ONLY a JSON object. No prose, no markdown, no backticks."
            ),
        }

        messages = [system_prompt]

        # Add last assistant message for context if available
        if last_assistant_message:
            messages.append({"role": "assistant", "content": last_assistant_message})

        messages.append({"role": "user", "content": text})

        try:
            raw = self.provider.chat(messages=messages, temperature=0.1)
            raw = self._strip_code_fences(raw)

            # Try to parse JSON
            try:
                data = json.loads(raw)
            except Exception:
                # Try to extract JSON from response
                start = raw.find("{")
                end = raw.rfind("}")
                if start != -1 and end != -1 and end > start:
                    data = json.loads(raw[start : end + 1])
                else:
                    data = {}

            if not isinstance(data, dict):
                data = {}

            return data
        except Exception as e:
            print(f"Error extracting fields: {e}")
            return {}

    def generate_response(
        self,
        user_message: str,
        state: ConversationState,
        conversation_history: List[Dict[str, str]],
    ) -> tuple[str, ConversationState, bool]:
        """
        Generate an appropriate response based on user message and current state.

        Returns:
            tuple of (response_text, updated_state, should_generate_itinerary)
        """
        # Get last assistant message for context
        last_assistant_msg = None
        if conversation_history:
            for msg in reversed(conversation_history):
                if msg.get("role") == "assistant":
                    last_assistant_msg = msg.get("content")
                    break

        # Extract any new information from user message
        extracted = self.extract_fields(user_message, last_assistant_msg)

        # Update state with extracted information
        updated_state = state.model_copy(deep=True)
        if extracted.get("traveler_name"):
            updated_state.traveler_name = extracted["traveler_name"]
        if extracted.get("destination"):
            updated_state.destination = extracted["destination"]

        # Handle dates - either direct dates or start_date
        if extracted.get("dates"):
            updated_state.dates = extracted["dates"]
        elif extracted.get("start_date"):
            # If we have start_date but not full dates, store it
            updated_state.dates = extracted["start_date"]

        # Handle duration
        if extracted.get("duration_days"):
            updated_state.duration = f"{extracted.get('duration_days')} days"
        elif extracted.get("duration"):
            updated_state.duration = extracted["duration"]

        # Check if user is explicitly asking to finalize/generate
        lower_msg = user_message.lower().strip()
        is_finalize_request = any(
            keyword in lower_msg
            for keyword in [
                "finalize",
                "generate",
                "create itinerary",
                "make itinerary",
                "done",
                "that's all",
                "ready",
            ]
        )

        # Determine if we should generate the itinerary
        should_generate = False
        if is_finalize_request and updated_state.is_complete():
            should_generate = True
            response = (
                "Perfect! I have all the information I need. Generating your itinerary now..."
            )
            return response, updated_state, should_generate

        # Build a context-aware prompt for the assistant
        system_context = self._build_system_context(updated_state)

        # Build conversation history for context
        history_messages = [{"role": "system", "content": system_context}]

        # Add recent conversation history (last 4 messages)
        for msg in conversation_history[-4:]:
            history_messages.append(msg)

        # Add current user message
        history_messages.append({"role": "user", "content": user_message})

        # Generate response
        try:
            response = self.provider.chat(messages=history_messages, temperature=0.1)

            # Update last question if we asked something
            if "?" in response:
                updated_state.last_question = response

            return response, updated_state, should_generate
        except Exception as e:
            print(f"Error generating response: {e}")
            # Fallback response
            missing = updated_state.get_missing_fields()
            if missing:
                prompts = {
                    "traveler_name": "What's the traveler name (or your name) for the itinerary?",
                    "destination": "Where are you traveling to?",
                    "dates": "What are your travel dates?",
                }
                response = prompts.get(
                    missing[0], "Could you provide more details about your trip?"
                )
            else:
                response = "I have all the information. Type 'finalize' when you're ready to generate your itinerary."

            return response, updated_state, should_generate

    def _build_system_context(self, state: ConversationState) -> str:
        """Build system context based on current conversation state."""
        collected = []
        if state.traveler_name:
            collected.append(f"Traveler name: {state.traveler_name}")
        if state.destination:
            collected.append(f"Destination: {state.destination}")
        if state.dates:
            collected.append(f"Dates: {state.dates}")
        if state.duration:
            collected.append(f"Duration: {state.duration}")

        collected_text = "\n".join(collected) if collected else "None yet"

        missing = state.get_missing_fields()
        if missing:
            missing_text = ", ".join(missing)
            next_question = self._get_next_question_for_field(missing[0])
        else:
            missing_text = "None - all required information collected"
            next_question = "Ask the user to type 'finalize' to generate the itinerary (make it clear that 'finalize' is the magic word they should use)."

        return f"""You are a helpful travel itinerary planning assistant. Your job is to collect information to create a travel itinerary.

Current information collected:
{collected_text}

Still needed: {missing_text}

Guidelines:
- Be friendly, conversational, and concise
- Acknowledge any information the user just provided
- When acknowledging dates and duration together, naturally state them both (e.g., "Lisbon from August 15-20, 2025 for 5 days")
- This helps the user confirm the dates are correct without explicitly asking
- If information is still missing, naturally ask for the next required field
- {next_question}
- Don't repeat information the user already provided unless it's for natural confirmation
- If all required information is collected, let them know and ask if they want to generate the itinerary
- Keep responses under 2-3 sentences

Required fields: traveler_name, destination, dates
Optional fields: duration"""

    def _get_next_question_for_field(self, field: str) -> str:
        """Get a natural question to ask for a specific field."""
        questions = {
            "traveler_name": "Ask for the traveler's name in a friendly way.",
            "destination": "Ask where they're traveling to.",
            "dates": "Ask when they're traveling (what dates).",
        }
        return questions.get(field, "Ask for more details about their trip.")

    def _strip_code_fences(self, text: str) -> str:
        """Strip markdown code fences from LLM output."""
        s = text.strip()
        if s.startswith("```"):
            body = s.lstrip("`")
            if body.lower().startswith("json"):
                body = body[4:]
            body = body.lstrip("\n ")
            if body.endswith("```"):
                body = body[:-3]
            return body.strip()
        return s
