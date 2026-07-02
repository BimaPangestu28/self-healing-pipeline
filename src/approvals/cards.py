"""Adaptive Cards for the approval flow (healthcheck, approval, result).

These mirror the AION Teams cards: an "Auto Healthcheck Result" summary, an
interactive "Action Approval Required" card with Approve/Reject actions, and a
completion card. The approval actions are ``Action.Submit`` with a ``verb`` in
their data payload so any host (the demo web renderer, a Teams bot, or a Power
Automate flow) can route the decision back to the backend.
"""

from __future__ import annotations

from typing import Any

from src.approvals.service import ApprovalRequest, ApprovalStatus, HealthReport

SCHEMA = "http://adaptivecards.io/schemas/adaptive-card.json"
VERSION = "1.4"


def _text(text: str, **kwargs: Any) -> dict[str, Any]:
    """Build a TextBlock with sensible wrapping defaults."""
    block: dict[str, Any] = {"type": "TextBlock", "text": text, "wrap": True}
    block.update(kwargs)
    return block


def _facts(pairs: list[tuple[str, str]]) -> dict[str, Any]:
    """Build a FactSet from (title, value) pairs."""
    return {"type": "FactSet", "facts": [{"title": t, "value": v} for t, v in pairs]}


def _card(body: list[dict[str, Any]], actions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Assemble an Adaptive Card document."""
    card: dict[str, Any] = {"type": "AdaptiveCard", "$schema": SCHEMA, "version": VERSION, "body": body}
    if actions:
        card["actions"] = actions
    return card


def _status_text(healthy: bool) -> tuple[str, str]:
    """Return (label, color) for an overall health status."""
    return ("✅ OK Healthy", "Good") if healthy else ("❌ Unhealthy", "Attention")


def _service_lines(report: HealthReport) -> list[dict[str, Any]]:
    """Render each service check as a bullet TextBlock."""
    lines: list[dict[str, Any]] = []
    for service in report.services:
        mark = "✅ OK" if service.ok else "❌ NOK"
        lines.append(_text(f"- {service.name}: {mark} — {service.detail}", spacing="None"))
    return lines


def build_healthcheck_card(report: HealthReport, analysis: str | None = None) -> dict[str, Any]:
    """Render an Outsystem-style healthcheck result (optionally with analysis)."""
    status_label, status_color = _status_text(report.healthy)
    body: list[dict[str, Any]] = [
        _text(f"🩺 Auto Healthcheck Result for {report.application}", weight="Bolder", size="Large"),
        _text(f"Overall Status: {status_label}", weight="Bolder", color=status_color),
        _facts([("Host", report.host), ("Application", report.application)]),
        _text("Services", weight="Bolder", spacing="Medium"),
    ]
    body.extend(_service_lines(report))
    if analysis:
        body.append(_text("Analysis & Recommendation", weight="Bolder", spacing="Medium"))
        body.append(_text(analysis))
    return _card(body)


def build_approval_card(request: ApprovalRequest) -> dict[str, Any]:
    """Render the interactive 'Action Approval Required' card with Approve/Reject."""
    action = request.action
    body: list[dict[str, Any]] = [
        _text("🛎️ Action Approval Required", weight="Bolder", size="Large"),
        _facts(
            [
                ("Request ID", request.request_id),
                ("Requestor", request.requestor),
                ("Action", action.action),
                ("Tool", action.tool),
                ("Application", request.application),
                ("Description", action.description),
            ]
        ),
        _text("Parameters", weight="Bolder", spacing="Medium"),
        _facts([(key, value) for key, value in action.parameters.items()]),
    ]
    actions = [
        {
            "type": "Action.Submit",
            "title": "Approve",
            "style": "positive",
            "data": {"verb": "approve", "requestId": request.request_id},
        },
        {
            "type": "Action.Submit",
            "title": "Reject",
            "style": "destructive",
            "data": {"verb": "reject", "requestId": request.request_id},
        },
    ]
    return _card(body, actions)


def build_result_card(request: ApprovalRequest) -> dict[str, Any]:
    """Render the completion card after an approval decision."""
    if request.status is ApprovalStatus.REJECTED:
        return _card(
            [
                _text("⛔ Action Rejected", weight="Bolder", size="Large", color="Attention"),
                _facts(
                    [
                        ("Request ID", request.request_id),
                        ("Action", request.action.action),
                    ]
                ),
                _text("No changes were made to the host.", spacing="Medium"),
            ]
        )

    execution = request.execution or {}
    verify = request.verify
    success = bool(execution.get("success"))
    title = "✅ Alert Action Completed Successfully" if success else "❌ Alert Action Failed"
    title_color = "Good" if success else "Attention"

    status_label = "✅ OK Healthy" if (verify and verify.healthy) else "❌ Unhealthy"
    body: list[dict[str, Any]] = [
        _text(title, weight="Bolder", size="Large", color=title_color),
        _facts(
            [
                ("Request ID", request.request_id),
                ("Action", request.action.action),
                ("Host", request.host),
                ("Overall Status", status_label),
            ]
        ),
    ]

    if verify:
        body.append(_text("Services", weight="Bolder", spacing="Medium"))
        body.extend(_service_lines(verify))

    body.append(_text("Ansible Execution", weight="Bolder", spacing="Medium"))
    body.append(
        _facts(
            [
                ("Job", str(execution.get("job_id", "-"))),
                ("Template ID", str(execution.get("template_id", "-"))),
                ("Target Host", str(execution.get("target_host", "-"))),
                ("Duration", f"{execution.get('duration_seconds', 0)} seconds"),
                ("Result", "✅ Successful" if success else "❌ Failed"),
            ]
        )
    )
    return _card(body)
