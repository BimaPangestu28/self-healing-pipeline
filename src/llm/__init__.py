"""LLM clients for generating natural-language analysis at runtime.

Two providers are supported and selectable via the ``LLM_PROVIDER`` env var:
``azure`` (Azure OpenAI) or ``deepseek``. Both expose a ``chat(system, user) -> str``
method. The client is optional: when nothing is configured, ``build_llm_client``
returns ``None`` and callers fall back to a deterministic template, so the app
always runs without external dependencies.
"""

from __future__ import annotations

import logging
import os

import httpx

from src.llm.azure_openai import AzureOpenAIChatClient
from src.llm.deepseek import DeepSeekClient

logger = logging.getLogger(__name__)

__all__ = ["AzureOpenAIChatClient", "DeepSeekClient", "build_llm_client"]

_AZURE_ALIASES = {"azure", "azure_openai", "azureopenai"}


def build_llm_client(transport: httpx.BaseTransport | None = None):
    """Select an LLM chat client from environment configuration.

    - ``LLM_PROVIDER=azure``    -> Azure OpenAI (if AZURE_OPENAI_* are set)
    - ``LLM_PROVIDER=deepseek`` -> DeepSeek (if DEEPSEEK_API_KEY is set)
    - ``LLM_PROVIDER=none``     -> disabled (returns None)
    - unset                     -> auto-detect: DeepSeek, then Azure, else None

    @param transport - optional httpx transport (used in tests)
    @returns a client exposing ``chat(system, user) -> str``, or None
    """
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()

    if provider == "none":
        return None
    if provider == "deepseek":
        return DeepSeekClient.from_env(transport)
    if provider in _AZURE_ALIASES:
        return AzureOpenAIChatClient.from_env(transport)

    # Auto-detect by whichever credentials are present.
    return DeepSeekClient.from_env(transport) or AzureOpenAIChatClient.from_env(transport)
