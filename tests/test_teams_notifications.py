"""Tests for the Teams Adaptive Card builders and delivery client."""

from __future__ import annotations

import httpx

from src.notifications import adaptive_cards, teams
from src.notifications.adaptive_cards import (
    ADAPTIVE_CARD_CONTENT_TYPE,
    build_alert_card,
    build_pipeline_report_card,
    wrap_as_teams_message,
)
from src.notifications.models import EscalatedItem, FixedItem, PipelineReport, PodStatus


def _sample_report() -> PipelineReport:
    return PipelineReport(
        run_date="2026-07-02",
        status="issues_remain",
        l1_passed=460,
        l1_failed=4,
        l1_total=464,
        auto_fixable=3,
        escalated_count=1,
        l2_fixed=3,
        l2_escalated=1,
        staging_deployed=True,
        validation_passing=3,
        validation_target=4,
        merge_request_created=True,
        merge_request_url="https://gitlab.example/mr/1",
        report_url="https://reports.example/l2.md",
        fixed_items=[FixedItem(failure_id="F001", description="GMV NaN", runbook_id="RB-1")],
        escalated_items=[
            EscalatedItem(failure_id="F005", description="Auth loop", reason="needs schema change")
        ],
        pod_statuses=[PodStatus(deployment="sample-app", status="Running", image_tag="v1.10.1")],
    )


def _iter_text(node) -> list[str]:
    """Recursively collect every TextBlock string in a card body."""
    texts: list[str] = []
    if isinstance(node, dict):
        if node.get("type") == "TextBlock":
            texts.append(node.get("text", ""))
        for value in node.values():
            texts.extend(_iter_text(value))
    elif isinstance(node, list):
        for item in node:
            texts.extend(_iter_text(item))
    return texts


def test_pipeline_card_has_expected_shape():
    card = build_pipeline_report_card(_sample_report())

    assert card["type"] == "AdaptiveCard"
    assert card["version"] == adaptive_cards.ADAPTIVE_CARD_VERSION
    # FactSet with the six summary rows is present.
    fact_sets = [el for el in card["body"] if el.get("type") == "FactSet"]
    assert fact_sets and len(fact_sets[0]["facts"]) == 6

    all_text = "\n".join(_iter_text(card["body"]))
    assert "QA Pipeline Report — 2026-07-02" in all_text
    assert "ISSUES REMAIN" in all_text
    assert "F001" in all_text  # fixed item rendered
    assert "F005" in all_text  # escalated item rendered
    assert "sample-app: Running (image: v1.10.1)" in all_text

    # Action buttons include both URLs.
    action_urls = {action["url"] for action in card.get("actions", [])}
    assert "https://gitlab.example/mr/1" in action_urls
    assert "https://reports.example/l2.md" in action_urls


def test_status_color_mapping():
    card = build_pipeline_report_card(_sample_report())
    status_block = card["body"][1]
    assert status_block["color"] == "Warning"


def test_wrap_as_teams_message_envelope():
    card = build_pipeline_report_card(_sample_report())
    message = wrap_as_teams_message(card)
    assert message["type"] == "message"
    attachment = message["attachments"][0]
    assert attachment["contentType"] == ADAPTIVE_CARD_CONTENT_TYPE
    assert attachment["content"] is card


def test_alert_card_contains_analysis_and_severity():
    card = build_alert_card(
        title="High CPU on auth-service",
        analysis="CPU saturated; scale out recommended.",
        severity="critical",
        source_link="https://kibana.example/alert/1",
    )
    all_text = "\n".join(_iter_text(card["body"]))
    assert "High CPU on auth-service" in all_text
    assert "CPU saturated" in all_text
    facts = [el for el in card["body"] if el.get("type") == "FactSet"][0]["facts"]
    assert {"title": "Severity", "value": "critical"} in facts


async def test_send_returns_false_when_webhook_unset(monkeypatch):
    monkeypatch.setattr(teams, "get_teams_webhook_url", lambda: None)
    delivered = await teams.send_adaptive_card({"type": "AdaptiveCard"})
    assert delivered is False


async def test_send_posts_wrapped_card(monkeypatch):
    captured: dict = {}

    class _FakeResponse:
        status_code = 200
        text = ""

        def raise_for_status(self) -> None:
            return None

    class _FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self) -> "_FakeClient":
            return self

        async def __aexit__(self, *args) -> bool:
            return False

        async def post(self, url: str, json=None):
            captured["url"] = url
            captured["json"] = json
            return _FakeResponse()

    monkeypatch.setattr(teams, "get_teams_webhook_url", lambda: "https://teams.example/webhook")
    monkeypatch.setattr(teams.httpx, "AsyncClient", _FakeClient)

    card = {"type": "AdaptiveCard", "version": "1.4"}
    delivered = await teams.send_adaptive_card(card)

    assert delivered is True
    assert captured["url"] == "https://teams.example/webhook"
    assert captured["json"]["type"] == "message"
    assert captured["json"]["attachments"][0]["content"] is card
    # httpx import kept referenced for type checkers / linters.
    assert isinstance(httpx.Timeout(1.0), httpx.Timeout)
