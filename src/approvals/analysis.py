"""Root-cause analysis + recommendation for a healthcheck.

Uses an LLM (Azure OpenAI or DeepSeek, selectable) when configured, and falls back
to a deterministic template otherwise. Only the *narrative* is LLM-generated —
detection and remediation stay rule-based and deterministic.
"""

from __future__ import annotations

import logging

from src.approvals.models import HealthReport
from src.llm import build_llm_client

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a senior Site Reliability Engineer assistant. Given a host healthcheck "
    "result, write a concise Root Cause and a clear Recommendation (an action to "
    "remediate). Keep it under 4 sentences, plain text, no preamble, no markdown "
    "headers. Start with 'Root Cause:' then 'Recommendation:'."
)


def _prompt(report: HealthReport) -> str:
    """Render the healthcheck into an LLM prompt."""
    services = "\n".join(
        f"- {service.name}: {'OK' if service.ok else 'NOK'} — {service.detail}"
        for service in report.services
    )
    return (
        f"Application: {report.application}\n"
        f"Host: {report.host}\n"
        f"Overall: {'Healthy' if report.healthy else 'Unhealthy'}\n"
        f"Memory utilization: {report.memory_percent}%\n"
        f"Services:\n{services}"
    )


def _template_analysis(report: HealthReport) -> str:
    """Deterministic fallback analysis (no LLM)."""
    if report.healthy:
        return "All services are healthy. No action required."
    return (
        f"Root Cause: The Memory Usage service check is NOK, reporting high "
        f"utilization at {report.memory_percent}%. The W3SVC service is healthy.\n\n"
        f"Recommendation: The overall health status of {report.application} on host "
        f"{report.host} is Unhealthy due to high memory consumption. A restart of the "
        f"{report.application} application is required to reclaim memory."
    )


def build_analysis(report: HealthReport, client=None) -> str:
    """Return an analysis string, LLM-generated when configured, else templated.

    @param report - the healthcheck to analyze
    @param client - optional LLM client (defaults to the env-selected provider)
    @returns analysis text (never raises; always falls back to the template)
    """
    llm = client if client is not None else build_llm_client()
    if llm is None:
        return _template_analysis(report)
    prompt = _prompt(report)
    try:
        text = llm.chat(_SYSTEM_PROMPT, prompt)
        result = text.strip() or _template_analysis(report)
    except Exception as exc:  # network/parse/etc — never break the flow
        logger.warning("LLM analysis failed (%s); using template fallback", exc)
        result = _template_analysis(report)

    from src import tool_trace

    provider = getattr(llm, "provider", "llm")
    tool_trace.record(tool=f"LLM · analysis ({provider})", input=prompt, output=result)
    return result
