from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from app.core.llm_provider import LLMProvider
from app.core.settings import get_settings
from pydantic import BaseModel


class ConversationState(BaseModel):
    """Tracks the state of an itinerary planning conversation."""

    # Collected information
    traveler_name: Optional[str] = None
    destination: Optional[str] = None
    dates: Optional[str] = None
    duration: Optional[str] = None
    trip_for_self: Optional[bool] = None  # True if trip is for the user, False if for someone else

    # Conversation metadata
    itinerary_id: Optional[str] = None
    last_question: Optional[str] = None

    def is_complete(self) -> bool:
        """Check if we have all required information to generate itinerary."""
        return bool(self.traveler_name and self.destination and self.dates)

    def get_missing_fields(self) -> List[str]:
        """Get list of required fields that are still missing."""
        missing = []
        if not self.destination:
            missing.append("destination")
        if not self.dates:
            missing.append("dates")
        # Only need traveler_name if we don't know who it's for yet
        if not self.traveler_name:
            if self.trip_for_self is None:
                missing.append("trip_for_self")  # Ask who the trip is for first
            elif self.trip_for_self is False:
                missing.append("traveler_name")  # It's for someone else, need their name
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
                "- traveler_name (string|null): the traveler's name (only if explicitly mentioned)\n"
                "- destination (string|null): where they want to go\n"
                "- dates (string|null): full date range if provided (e.g., 'August 15-20, 2025' or 'October 13-15, 2025')\n"
                "  * IMPORTANT: Always include the year if the user mentions it\n"
                "  * If no year is mentioned, extract without year (e.g., 'October 13-15')\n"
                "- start_date (string|null): starting date if only start is mentioned (e.g., 'August 15th 2025')\n"
                "- duration_days (integer|null): number of days if mentioned\n"
                "- duration (string|null): duration as text (e.g., '5 days', 'one week')\n"
                "- trip_for_self (boolean|null): detect if trip is for the user themselves\n"
                "  * true: phrases like 'for me', 'just me', 'myself', 'it's for me', 'I'm going', 'my trip'\n"
                "  * false: phrases like 'for [someone]', 'planning for my friend', 'it's for someone else', 'booking for'\n"
                "  * null: if unclear or not mentioned\n"
                "\n"
                "Important for dates:\n"
                "- If user provides a full date range, extract as 'dates'\n"
                "- If user provides only a start date, extract as 'start_date'\n"
                "- If user mentions duration, extract both 'duration_days' (number) and 'duration' (text)\n"
                "\n"
                "Context helps: If the assistant just asked whose trip it is and user says 'me' or 'just me', set trip_for_self=true.\n"
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
        user_first_name: Optional[str] = None,
        current_date: Optional[str] = None,
        current_day: Optional[str] = None,
    ) -> tuple[str, ConversationState, bool]:
        """
        Generate an appropriate response based on user message and current state.

        Args:
            user_message: The user's message
            state: Current conversation state
            conversation_history: Previous messages
            user_first_name: User's first name for personalization
            current_date: Current date in YYYY-MM-DD format
            current_day: Current day of week (e.g., "Monday")

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

        # Handle trip_for_self
        if extracted.get("trip_for_self") is not None:
            updated_state.trip_for_self = extracted["trip_for_self"]
            # If trip is for user, auto-fill their name
            if extracted["trip_for_self"] is True and user_first_name:
                updated_state.traveler_name = user_first_name

        # Handle explicit traveler_name (for someone else)
        if extracted.get("traveler_name"):
            updated_state.traveler_name = extracted["traveler_name"]
            # If they provided a name, assume it's not for themselves
            if not updated_state.trip_for_self:
                updated_state.trip_for_self = False

        if extracted.get("destination"):
            updated_state.destination = extracted["destination"]

        # Handle dates - either direct dates or start_date
        if extracted.get("dates"):
            dates_value = extracted["dates"]
            updated_state.dates = dates_value

            # Check if dates are missing year (for LLM to ask clarification)
            # This is just for state tracking - the LLM will handle asking
            import re

            has_year = bool(re.search(r"\b(19|20)\d{2}\b", dates_value))
            if not has_year:
                # Store a flag that dates need year clarification
                # The LLM will see this in the context and ask for clarification
                updated_state.dates = dates_value  # Keep as-is, LLM will handle
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
            response = "Perfect! I have all the information I need. Generating your itinerary now..."
            return response, updated_state, should_generate

        # Build a context-aware prompt for the assistant
        system_context = self._build_system_context(
            updated_state, user_first_name, current_date, current_day
        )

        # Check if this is the first message (no history except current message)
        is_first_message = len(conversation_history) <= 1

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

    def _build_system_context(
        self,
        state: ConversationState,
        user_first_name: Optional[str] = None,
        current_date: Optional[str] = None,
        current_day: Optional[str] = None,
    ) -> str:
        """Build system context based on current conversation state."""
        # User context section
        user_context_parts = []
        if user_first_name:
            user_context_parts.append(f"User's name: {user_first_name}")
        if current_date and current_day:
            user_context_parts.append(
                f"Today is: {current_day}, {current_date} (use this to understand relative dates like 'next weekend', 'this Friday', etc.)"
            )

        user_context = "\n".join(user_context_parts) if user_context_parts else ""

        collected = []
        if state.traveler_name:
            collected.append(f"Traveler name: {state.traveler_name}")
        if state.trip_for_self is not None:
            collected.append(f"Trip for: {'self' if state.trip_for_self else 'someone else'}")
        if state.destination:
            collected.append(f"Destination: {state.destination}")
        if state.dates:
            # Check if dates have a year
            import re

            has_year = bool(re.search(r"\b(19|20)\d{2}\b", state.dates))
            if has_year:
                collected.append(f"Dates: {state.dates}")
            else:
                collected.append(
                    f"Dates: {state.dates} (⚠️ YEAR NOT SPECIFIED - ask for clarification)"
                )
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

        user_context_section = f"User Context:\n{user_context}\n\n" if user_context else ""

        # Add greeting instruction for first message
        greeting_instruction = ""
        if len(collected) == 0:  # No information collected yet = first interaction
            if user_first_name:
                greeting_instruction = f"- Start by greeting {user_first_name} warmly by name\n"

        context = f"""You are a helpful travel itinerary planning assistant. Your job is to collect information to create a travel itinerary.

{user_context_section}Current information collected:
{collected_text}

Still needed: {missing_text}

Guidelines:
{greeting_instruction}- Be friendly, conversational, and concise
- Acknowledge any information the user just provided
- When acknowledging dates and duration together, naturally state them both (e.g., "Lisbon from August 15-20, 2025 for 5 days")
- This helps the user confirm the dates are correct without explicitly asking
- If dates are provided without a year, ask for clarification (e.g., "Just to confirm, is that October 2025 or 2026?")
- If dates are ambiguous or incomplete, ask follow-up questions to clarify
- If information is still missing, naturally ask for the next required field
- {next_question}
- Don't repeat information the user already provided unless it's for natural confirmation
- If all required information is collected, let them know and ask if they want to generate the itinerary
- Keep responses under 2-3 sentences

Required fields: traveler_name, destination, dates
Optional fields: duration"""

        return context

    def _get_next_question_for_field(self, field: str) -> str:
        """Get a natural question to ask for a specific field."""
        questions = {
            "trip_for_self": "Ask if this trip is for them or if they're planning for someone else.",
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
