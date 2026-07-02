"""DeepSeek chat client (OpenAI-compatible chat completions API)."""

from __future__ import annotations

import os

import httpx

_DEFAULT_BASE_URL = "https://api.deepseek.com"
_DEFAULT_MODEL = "deepseek-chat"


class DeepSeekClient:
    """Minimal DeepSeek chat client returning the assistant message text."""

    provider = "deepseek"

    def __init__(
        self,
        api_key: str,
        base_url: str = _DEFAULT_BASE_URL,
        model: str = _DEFAULT_MODEL,
        timeout: float = 30.0,
        max_tokens: int = 400,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self._transport = transport

    def chat(self, system: str, user: str) -> str:
        """Send a system+user prompt and return the assistant reply text."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.3,
            "max_tokens": self.max_tokens,
            "stream": False,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        with httpx.Client(timeout=self.timeout, transport=self._transport) as client:
            response = client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        return data["choices"][0]["message"]["content"].strip()

    @classmethod
    def from_env(cls, transport: httpx.BaseTransport | None = None) -> "DeepSeekClient | None":
        """Build from DEEPSEEK_* env vars, or None when no API key is set."""
        api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        if not api_key:
            return None
        return cls(
            api_key=api_key,
            base_url=os.getenv("DEEPSEEK_BASE_URL", _DEFAULT_BASE_URL).strip() or _DEFAULT_BASE_URL,
            model=os.getenv("DEEPSEEK_MODEL", _DEFAULT_MODEL).strip() or _DEFAULT_MODEL,
            transport=transport,
        )
