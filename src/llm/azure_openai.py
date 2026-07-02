"""Azure OpenAI chat client (chat completions API)."""

from __future__ import annotations

import os

import httpx

_DEFAULT_API_VERSION = "2024-10-21"


class AzureOpenAIChatClient:
    """Minimal Azure OpenAI chat-completions client returning the reply text."""

    provider = "azure"

    def __init__(
        self,
        endpoint: str,
        api_key: str,
        deployment: str,
        api_version: str = _DEFAULT_API_VERSION,
        timeout: float = 30.0,
        max_tokens: int = 400,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.deployment = deployment
        self.api_version = api_version
        self.timeout = timeout
        self.max_tokens = max_tokens
        self._transport = transport

    def chat(self, system: str, user: str) -> str:
        """Send a system+user prompt and return the assistant reply text."""
        url = (
            f"{self.endpoint}/openai/deployments/{self.deployment}"
            f"/chat/completions?api-version={self.api_version}"
        )
        payload = {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.3,
            "max_tokens": self.max_tokens,
        }
        headers = {"api-key": self.api_key, "Content-Type": "application/json"}
        with httpx.Client(timeout=self.timeout, transport=self._transport) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        return data["choices"][0]["message"]["content"].strip()

    @classmethod
    def from_env(cls, transport: httpx.BaseTransport | None = None) -> "AzureOpenAIChatClient | None":
        """Build from AZURE_OPENAI_* env vars, or None when required vars are missing."""
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
        api_key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
        deployment = (
            os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT")
            or os.getenv("AZURE_OPENAI_DEPLOYMENT")
            or ""
        ).strip()
        if not (endpoint and api_key and deployment):
            return None
        return cls(
            endpoint=endpoint,
            api_key=api_key,
            deployment=deployment,
            api_version=os.getenv("AZURE_OPENAI_CHAT_API_VERSION", _DEFAULT_API_VERSION).strip()
            or _DEFAULT_API_VERSION,
            transport=transport,
        )
