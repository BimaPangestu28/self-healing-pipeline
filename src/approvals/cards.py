"""Adaptive Cards for the approval flow (healthcheck, approval, result).

These mirror the AION Teams cards: an "Auto Healthcheck Result" summary, an
interactive "Action Approval Required" card with Approve/Reject actions, and a
completion card. The approval actions use ``Action.Execute`` (the Teams Universal
Action model) with a ``verb`` and a ``data`` payload, so the same card works both
in the web renderer and when posted to Teams via a bot.
"""

from __future__ import annotations

from typing import Any

from src.approvals.models import ApprovalRequest, ApprovalStatus, HealthReport

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


def build_incident_card(
    *,
    title: str,
    application: str,
    host: str,
    pod: str | None,
    healthy: bool,
    services: list[tuple[str, bool, str]],
    analysis: str | None = None,
) -> dict[str, Any]:
    """Generic incident/healthcheck card for any scenario (not just memory)."""
    status_label, status_color = _status_text(healthy)
    facts = [("Host (node)", host), ("Application", application)]
    if pod:
        facts.append(("Pod", pod))
    body: list[dict[str, Any]] = [
        _text(f"🩺 {title}", weight="Bolder", size="Large"),
        _text(f"Overall Status: {status_label}", weight="Bolder", color=status_color),
        _facts(facts),
        _text("Checks", weight="Bolder", spacing="Medium"),
    ]
    for name, ok, detail in services:
        body.append(_text(f"- {name}: {'✅ OK' if ok else '❌ NOK'} — {detail}", spacing="None"))
    if analysis:
        body.append(_text("Analysis & Recommendation", weight="Bolder", spacing="Medium"))
        body.append(_text(analysis))
    return _card(body)


def build_scenario_result_card(
    *,
    title: str,
    healthy: bool,
    action: str,
    tool: str,
    duration_seconds: float,
    host: str,
    services: list[tuple[str, bool, str]],
) -> dict[str, Any]:
    """Generic completion card for a scenario remediation."""
    color = "Good" if healthy else "Attention"
    body: list[dict[str, Any]] = [
        _text(title, weight="Bolder", size="Large", color=color),
        _facts(
            [
                ("Action", action),
                ("Host", host),
                ("Overall Status", "✅ OK Healthy" if healthy else "❌ Unhealthy"),
            ]
        ),
        _text("Checks", weight="Bolder", spacing="Medium"),
    ]
    for name, ok, detail in services:
        body.append(_text(f"- {name}: {'✅ OK' if ok else '❌ NOK'} — {detail}", spacing="None"))
    body.append(_text(f"{tool.title()} Execution", weight="Bolder", spacing="Medium"))
    body.append(
        _facts(
            [
                ("Duration", f"{duration_seconds} seconds"),
                ("Result", "✅ Successful" if healthy else "❌ Failed"),
            ]
        )
    )
    return _card(body)


def build_message_card(text: str, *, color: str | None = None) -> dict[str, Any]:
    """Render a single-line informational Adaptive Card."""
    return _card([_text(text, weight="Bolder", **({"color": color} if color else {}))])


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
    identity_facts = [("Host (node)", report.host), ("Application", report.application)]
    if report.pod:
        identity_facts.append(("Pod", report.pod))
    if report.pod_ip:
        identity_facts.append(("Pod IP", report.pod_ip))
    body: list[dict[str, Any]] = [
        _text(f"🩺 Auto Healthcheck Result for {report.application}", weight="Bolder", size="Large"),
        _text(f"Overall Status: {status_label}", weight="Bolder", color=status_color),
        _facts(identity_facts),
        _text("Services", weight="Bolder", spacing="Medium"),
    ]
    body.extend(_service_lines(report))
    if analysis:
        body.append(_text("Analysis & Recommendation", weight="Bolder", spacing="Medium"))
        body.append(_text(analysis))
    return _card(body)


def _decision_action(title: str, verb: str, request_id: str, style: str) -> dict[str, Any]:
    """Build an Action.Execute decision button carrying verb + requestId."""
    return {
        "type": "Action.Execute",
        "title": title,
        "verb": verb,
        "style": style,
        "data": {"verb": verb, "requestId": request_id},
    }


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
        _decision_action("Approve", "approve", request.request_id, "positive"),
        _decision_action("Reject", "reject", request.request_id, "destructive"),
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

    execution = request.execution
    verify = request.verify
    success = bool(execution and execution.success)
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

    tool_label = (execution.tool if execution else "job").title()
    body.append(_text(f"{tool_label} Execution", weight="Bolder", spacing="Medium"))
    exec_facts: list[tuple[str, str]] = [("Job", execution.job_id if execution else "-")]
    if execution and execution.template_id:  # AWX-only
        exec_facts.append(("Template ID", execution.template_id))
    if execution and execution.target_host:  # AWX-only
        exec_facts.append(("Target Host", execution.target_host))
    exec_facts.append(("Duration", f"{execution.duration_seconds if execution else 0} seconds"))
    exec_facts.append(("Result", "✅ Successful" if success else "❌ Failed"))
    body.append(_facts(exec_facts))
    return _card(body)
