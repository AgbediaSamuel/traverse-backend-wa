from __future__ import annotations

from typing import Any, Dict, List

import aisuite as ai  # type: ignore


class LLMProvider:
    def __init__(self, model: str) -> None:
        self.model = model
        try:
            self._client = ai.Client()
        except Exception as exc:  # fail fast if aisuite cannot initialize
            raise RuntimeError("Failed to initialize aisuite client") from exc

    def chat(self, messages: List[Dict[str, Any]], temperature: float = 0.3) -> str:
        """Send a chat completion request. messages: list of dicts with keys: role (system|user|assistant), content (str)"""
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
        )
        return resp.choices[0].message.content
