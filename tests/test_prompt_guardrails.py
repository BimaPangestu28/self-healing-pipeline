"""Tests for prompt loading and optional guardrail handling."""

from unittest.mock import patch

from src.config.prompt_manager import _apply_non_negotiable_guardrails, clear_prompt_cache, get_prompt


def test_guardrail_added_for_router_prompt():
    base_prompt = "Base router prompt."
    result = _apply_non_negotiable_guardrails("router-agent", base_prompt)

    assert "This assistant is strictly read-only." in result
    assert "use mode \"reject\"" in result


def test_no_guardrail_for_other_prompts():
    base_prompt = "Base k8s prompt."
    result = _apply_non_negotiable_guardrails("k8s-monitor-agent", base_prompt)

    assert result == base_prompt


@patch("src.config.prompt_manager._get_langfuse_client")
@patch("src.config.prompt_manager._load_fallback_prompt")
def test_get_prompt_returns_fallback_when_langfuse_unavailable(
    mock_load_fallback, mock_get_langfuse_client
):
    clear_prompt_cache()
    mock_get_langfuse_client.return_value = None
    mock_load_fallback.return_value = "Fallback router prompt."

    prompt = get_prompt("router-agent")

    assert "Fallback router prompt." in prompt
    assert "This assistant is strictly read-only." in prompt
