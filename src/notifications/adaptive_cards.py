"""Builders that render structured payloads into Microsoft Teams Adaptive Cards.

The output of these builders is a plain ``dict`` matching the Adaptive Card
schema. ``wrap_as_teams_message`` wraps a card in the message envelope expected
by a Teams incoming webhook (Power Automate "Workflows" webhook or a classic
Office 365 connector).

Reference: https://adaptivecards.io/explorer/
"""

from __future__ import annotations

from typing import Any

from src.notifications.models import PipelineReport

ADAPTIVE_CARD_SCHEMA = "http://adaptivecards.io/schemas/adaptive-card.json"
ADAPTIVE_CARD_VERSION = "1.4"
ADAPTIVE_CARD_CONTENT_TYPE = "application/vnd.microsoft.card.adaptive"

# Maps a pipeline status to (display label, Adaptive Card color token).
_STATUS_PRESENTATION: dict[str, tuple[str, str]] = {
    "all_clear": ("✅ ALL CLEAR", "Good"),
    "issues_remain": ("⚠️ ISSUES REMAIN", "Warning"),
    "critical": ("🔴 CRITICAL", "Attention"),
}


def _text_block(
    text: str,
    *,
    weight: str | None = None,
    size: str | None = None,
    color: str | None = None,
    wrap: bool = True,
    is_subtle: bool = False,
    spacing: str | None = None,
) -> dict[str, Any]:
    """Build a single Adaptive Card ``TextBlock`` element."""
    block: dict[str, Any] = {"type": "TextBlock", "text": text, "wrap": wrap}
    if weight:
        block["weight"] = weight
    if size:
        block["size"] = size
    if color:
        block["color"] = color
    if is_subtle:
        block["isSubtle"] = True
    if spacing:
        block["spacing"] = spacing
    return block


def _fact_set(facts: list[tuple[str, str]]) -> dict[str, Any]:
    """Build an Adaptive Card ``FactSet`` from (title, value) pairs."""
    return {
        "type": "FactSet",
        "facts": [{"title": title, "value": value} for title, value in facts],
    }


def _bullet_section(heading: str, lines: list[str]) -> list[dict[str, Any]]:
    """Build a bold heading followed by one wrapped bullet line per entry."""
    if not lines:
        return []

    elements = [_text_block(heading, weight="Bolder", spacing="Medium")]
    elements.extend(_text_block(f"- {line}", spacing="None") for line in lines)
    return elements


def _open_url_actions(links: list[tuple[str, str | None]]) -> list[dict[str, Any]]:
    """Build ``Action.OpenUrl`` actions, skipping entries without a URL."""
    return [
        {"type": "Action.OpenUrl", "title": title, "url": url}
        for title, url in links
        if url
    ]


def _adaptive_card(body: list[dict[str, Any]], actions: list[dict[str, Any]]) -> dict[str, Any]:
    """Assemble a complete Adaptive Card document from body and actions."""
    card: dict[str, Any] = {
        "type": "AdaptiveCard",
        "$schema": ADAPTIVE_CARD_SCHEMA,
        "version": ADAPTIVE_CARD_VERSION,
        "body": body,
    }
    if actions:
        card["actions"] = actions
    return card


def _format_fixed_item(item: Any) -> str:
    """Render a fixed failure into a single summary line."""
    suffix = f" — auto-fixed via runbook {item.runbook_id}" if item.runbook_id else ""
    return f"[{item.failure_id}] {item.description}{suffix}"


def _format_escalated_item(item: Any) -> str:
    """Render an escalated failure into a single summary line."""
    return f"[{item.failure_id}] {item.description} — Reason: {item.reason}"


def _format_pod_status(item: Any) -> str:
    """Render a pod status into a single summary line."""
    image = f" (image: {item.image_tag})" if item.image_tag else ""
    return f"{item.deployment}: {item.status}{image}"


def build_pipeline_report_card(report: PipelineReport) -> dict[str, Any]:
    """Render a self-healing pipeline run summary into an Adaptive Card.

    Mirrors the Phase 7 Telegram report layout from the pipeline spec, adapted to
    an Adaptive Card with a color-coded status header, a summary FactSet, and
    fixed / escalated / pod-status detail sections.

    @param report - Structured pipeline run summary (PipelineReport)
    @returns Adaptive Card document (dict)
    """
    status_label, status_color = _STATUS_PRESENTATION.get(
        report.status, _STATUS_PRESENTATION["issues_remain"]
    )

    staging_deploy = "✅ Pushed" if report.staging_deployed else "❌ Skipped"
    merge_request = "✅ Created" if report.merge_request_created else "❌ Not created"

    body: list[dict[str, Any]] = [
        _text_block(
            f"🔄 QA Pipeline Report — {report.run_date}",
            weight="Bolder",
            size="Large",
        ),
        _text_block(f"Status: {status_label}", weight="Bolder", color=status_color),
        _fact_set(
            [
                (
                    "L1 Run",
                    f"{report.l1_passed} passed, {report.l1_failed} failed, "
                    f"{report.l1_skipped} skipped (of {report.l1_total} total)",
                ),
                (
                    "Classification",
                    f"{report.auto_fixable} auto-fixable, "
                    f"{report.escalated_count} escalated, {report.test_issues} test-issues",
                ),
                (
                    "L2 Fixes",
                    f"{report.l2_fixed} fixed, {report.l2_escalated} escalated, "
                    f"{report.l2_test_issues} test-issues",
                ),
                ("Staging Deploy", staging_deploy),
                (
                    "Validation",
                    f"{report.validation_passing}/{report.validation_target} now passing",
                ),
                ("MR Created", merge_request),
            ]
        ),
    ]

    body.extend(
        _bullet_section(
            "Fixed This Run",
            [_format_fixed_item(item) for item in report.fixed_items],
        )
    )
    body.extend(
        _bullet_section(
            "Escalated (Needs Human)",
            [_format_escalated_item(item) for item in report.escalated_items],
        )
    )
    body.extend(
        _bullet_section(
            "K8s Pod Status",
            [_format_pod_status(item) for item in report.pod_statuses],
        )
    )

    actions = _open_url_actions(
        [
            ("View Merge Request", report.merge_request_url),
            ("View Fix Report", report.report_url),
        ]
    )
    return _adaptive_card(body, actions)


def build_alert_card(
    *,
    title: str,
    analysis: str,
    severity: str | None = None,
    source_link: str | None = None,
) -> dict[str, Any]:
    """Render an SRE alert analysis into an Adaptive Card.

    @param title - Alert headline (rule name or short summary)
    @param analysis - SRE agent analysis text to display in the card body
    @param severity - Optional severity label surfaced as a fact
    @param source_link - Optional link to the originating alert
    @returns Adaptive Card document (dict)
    """
    body: list[dict[str, Any]] = [
        _text_block("🚨 SRE Alert Analysis", weight="Bolder", size="Large"),
    ]
    if title:
        body.append(_text_block(title, weight="Bolder"))
    if severity:
        body.append(_fact_set([("Severity", severity)]))
    body.append(_text_block(analysis, spacing="Medium"))

    actions = _open_url_actions([("View Alert Source", source_link)])
    return _adaptive_card(body, actions)


def wrap_as_teams_message(card: dict[str, Any]) -> dict[str, Any]:
    """Wrap an Adaptive Card in the Teams incoming-webhook message envelope.

    Accepted by both Power Automate "Workflows" webhooks and classic Office 365
    connector webhooks.

    @param card - Adaptive Card document produced by a build_* function
    @returns Teams webhook message payload (dict)
    """
    return {
        "type": "message",
        "attachments": [
            {
                "contentType": ADAPTIVE_CARD_CONTENT_TYPE,
                "content": card,
            }
        ],
    }
