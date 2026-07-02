"""Prompt management with Langfuse integration and local fallback."""

import logging
from functools import lru_cache
from pathlib import Path

from langfuse import Langfuse

from src.config.settings import get_settings

logger = logging.getLogger(__name__)

# Langfuse prompt names mapping
PROMPT_NAMES = {
    "elasticsearch-agent": "elasticsearch-agent",
    "k8s-monitor-agent": "k8s-monitor-agent",
    "rag-agent": "rag-agent",
    "router-agent": "router-agent",
    "synthesizer-agent": "synthesizer-agent",
}

# Local fallback directory
PROMPTS_DIR = Path(__file__).parent / "prompts"

# Hard guardrails enforced locally even when prompt is loaded from Langfuse.
NON_NEGOTIABLE_GUARDRAILS: dict[str, str] = {
    "router-agent": """

Additional non-negotiable rules:
- This assistant is strictly read-only.
- For requests that require making changes (for example: scale, restart, rollout, apply, patch, edit, create, delete, or exec into workloads), use mode "reject".
- Do not ask follow-up questions for mutating requests. Refuse directly.
""",
}


def _get_langfuse_client() -> Langfuse | None:
    """Get Langfuse client if configured."""
    settings = get_settings()
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        return None
    return Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )


def _load_fallback_prompt(prompt_name: str) -> str:
    """Load prompt from local fallback file."""
    fallback_path = PROMPTS_DIR / f"{prompt_name}.txt"
    if not fallback_path.exists():
        raise FileNotFoundError(f"Fallback prompt not found: {fallback_path}")
    return fallback_path.read_text(encoding="utf-8")


def _apply_non_negotiable_guardrails(prompt_name: str, prompt_text: str) -> str:
    """Append mandatory policy text for selected prompts."""
    guardrail = NON_NEGOTIABLE_GUARDRAILS.get(prompt_name)
    if not guardrail:
        return prompt_text
    if guardrail.strip() in prompt_text:
        return prompt_text
    return f"{prompt_text.rstrip()}{guardrail}\n"


@lru_cache(maxsize=10)
def get_prompt(prompt_name: str) -> str:
    """Get prompt from Langfuse with local fallback.

    Args:
        prompt_name: The name of the prompt in Langfuse (e.g., "elasticsearch-agent")

    Returns:
        The prompt text content

    Raises:
        FileNotFoundError: If prompt not found in Langfuse and no local fallback exists
    """
    # Try Langfuse first
    client = _get_langfuse_client()
    if client:
        try:
            prompt = client.get_prompt(prompt_name)
            logger.info(f"Loaded prompt '{prompt_name}' from Langfuse")
            return _apply_non_negotiable_guardrails(prompt_name, prompt.compile())
        except Exception as e:
            logger.warning(f"Failed to fetch prompt '{prompt_name}' from Langfuse: {e}")
            logger.info(f"Falling back to local prompt for '{prompt_name}'")
    else:
        logger.debug(f"Langfuse not configured, using local fallback for '{prompt_name}'")

    # Fallback to local file
    return _apply_non_negotiable_guardrails(
        prompt_name, _load_fallback_prompt(prompt_name)
    )


def clear_prompt_cache() -> None:
    """Clear the prompt cache to reload prompts from Langfuse."""
    get_prompt.cache_clear()
    logger.info("Prompt cache cleared")
