from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import aisuite as ai  # type: ignore

try:
    import google.generativeai as genai  # type: ignore
except Exception:
    genai = None  # optional


class LLMProvider:
    def __init__(self, model: str) -> None:
        self.model = model
        self._client = None
        self._genai_model: Optional[Any] = None

        # Route to google-generativeai if model starts with google-genai:
        if self.model.startswith("google-genai:"):
            if genai is None:
                raise RuntimeError("google-generativeai is not installed")
            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                raise RuntimeError("GOOGLE_API_KEY is not set")
            genai.configure(api_key=api_key)
            model_id = self.model.split(":", 1)[1]
            self._genai_model = genai.GenerativeModel(model_id)
        else:
            try:
                self._client = ai.Client()
            except Exception as exc:  # fail fast if aisuite cannot initialize
                raise RuntimeError("Failed to initialize aisuite client") from exc

    def chat(self, messages: List[Dict[str, Any]], temperature: float = 1.0) -> str:
        """Send a chat completion request. messages: list of dicts with keys: role (system|user|assistant), content (str)"""
        if self._genai_model is not None:
            # Map OpenAI-style messages to a single prompt for simplicity
            # Concatenate roles for context
            prompt = "\n".join(
                f"{m.get('role','user')}: {m.get('content','')}" for m in messages
            )
            response = self._genai_model.generate_content(prompt)
            return response.text or ""
        else:
            resp = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
            )
            return resp.choices[0].message.content
