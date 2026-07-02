"""Tests for the LLM-backed analysis and provider selection."""

from __future__ import annotations

import httpx

from src.approvals.analysis import build_analysis
from src.approvals.models import HealthReport, ServiceCheck
from src.llm import AzureOpenAIChatClient, DeepSeekClient, build_llm_client


def _unhealthy_report() -> HealthReport:
    return HealthReport(
        host="INDIGIINPAPP7",
        application="Outsystem",
        healthy=False,
        memory_percent=85,
        deployment_ready=True,
        services=[
            ServiceCheck("Memory Usage", False, "Memory usage is High: 85%"),
            ServiceCheck("W3SVC", True, "OK"),
        ],
    )


def _chat_response(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


# --- clients --------------------------------------------------------------


def test_deepseek_client_parses_reply():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        return _chat_response("Root Cause: memory high. Recommendation: restart.")

    client = DeepSeekClient(api_key="sk-x", transport=httpx.MockTransport(handler))
    text = client.chat("sys", "user")

    assert text == "Root Cause: memory high. Recommendation: restart."
    assert captured["url"].endswith("/chat/completions")
    assert captured["auth"] == "Bearer sk-x"


def test_azure_client_uses_deployment_and_api_key_header():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["api_key"] = request.headers.get("api-key")
        return _chat_response("Root Cause: x. Recommendation: y.")

    client = AzureOpenAIChatClient(
        endpoint="https://ex.openai.azure.com",
        api_key="az-key",
        deployment="gpt-4o",
        api_version="2024-10-21",
        transport=httpx.MockTransport(handler),
    )
    text = client.chat("sys", "user")

    assert text == "Root Cause: x. Recommendation: y."
    assert "/openai/deployments/gpt-4o/chat/completions" in captured["url"]
    assert "api-version=2024-10-21" in captured["url"]
    assert captured["api_key"] == "az-key"


# --- provider selection ---------------------------------------------------


def test_build_llm_client_selects_deepseek(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-x")
    client = build_llm_client()
    assert isinstance(client, DeepSeekClient)


def test_build_llm_client_selects_azure(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "azure")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://ex.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "az-key")
    monkeypatch.setenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o")
    client = build_llm_client()
    assert isinstance(client, AzureOpenAIChatClient)


def test_build_llm_client_none_when_disabled(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "none")
    assert build_llm_client() is None


def test_build_llm_client_none_when_unconfigured(monkeypatch):
    for var in [
        "LLM_PROVIDER",
        "DEEPSEEK_API_KEY",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_ENDPOINT",
    ]:
        monkeypatch.delenv(var, raising=False)
    assert build_llm_client() is None


# --- build_analysis -------------------------------------------------------


class _FakeClient:
    def __init__(self, text: str | None = None, raises: bool = False) -> None:
        self._text = text
        self._raises = raises

    def chat(self, system: str, user: str) -> str:
        if self._raises:
            raise RuntimeError("boom")
        return self._text or ""


def test_build_analysis_uses_llm_output():
    text = build_analysis(_unhealthy_report(), client=_FakeClient("LLM says restart it."))
    assert text == "LLM says restart it."


def test_build_analysis_falls_back_on_llm_error():
    text = build_analysis(_unhealthy_report(), client=_FakeClient(raises=True))
    assert "Root Cause:" in text and "Recommendation:" in text  # template used


def test_build_analysis_falls_back_on_empty_reply():
    text = build_analysis(_unhealthy_report(), client=_FakeClient(""))
    assert "Root Cause:" in text  # template used
