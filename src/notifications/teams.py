"""Async client for delivering Adaptive Cards to a Microsoft Teams webhook."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from src.config.settings import get_teams_webhook_url
from src.notifications.adaptive_cards import (
    build_pipeline_report_card,
    wrap_as_teams_message,
)
from src.notifications.models import PipelineReport

logger = logging.getLogger(__name__)

TEAMS_SEND_TIMEOUT_SECONDS = 10.0


class TeamsNotificationError(RuntimeError):
    """Raised when Teams delivery fails and the caller opts into strict mode."""


async def send_adaptive_card(
    card: dict[str, Any],
    *,
    webhook_url: str | None = None,
    raise_on_error: bool = False,
) -> bool:
    """Deliver an Adaptive Card to a Teams incoming webhook.

    Delivery is best-effort by default: transport and HTTP errors are logged and
    reported as ``False`` so a failed notification never breaks the caller. Set
    ``raise_on_error`` to surface failures as ``TeamsNotificationError`` instead.

    @param card - Adaptive Card document produced by a build_* function
    @param webhook_url - Override webhook URL (defaults to configured URL)
    @param raise_on_error - Raise instead of returning False on delivery failure
    @returns True when the card was accepted by Teams, False otherwise
    @throws TeamsNotificationError - On delivery failure when raise_on_error is set
    """
    url = webhook_url or get_teams_webhook_url()
    if not url:
        logger.info("Teams webhook not configured; skipping Adaptive Card delivery.")
        return False

    payload = wrap_as_teams_message(card)

    try:
        async with httpx.AsyncClient(timeout=TEAMS_SEND_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code if exc.response is not None else "unknown"
        body = exc.response.text[:2000] if exc.response is not None else ""
        logger.warning("Teams delivery failed: status=%s body=%s", status, body)
        if raise_on_error:
            raise TeamsNotificationError(f"Teams delivery failed with status {status}") from exc
        return False
    except httpx.HTTPError as exc:
        logger.warning("Teams delivery error: %s", exc)
        if raise_on_error:
            raise TeamsNotificationError(f"Teams delivery error: {exc}") from exc
        return False

    logger.info("Teams Adaptive Card delivered successfully.")
    return True


async def send_pipeline_report(
    report: PipelineReport,
    *,
    webhook_url: str | None = None,
    raise_on_error: bool = False,
) -> bool:
    """Render a pipeline report as an Adaptive Card and deliver it to Teams.

    @param report - Structured pipeline run summary (PipelineReport)
    @param webhook_url - Override webhook URL (defaults to configured URL)
    @param raise_on_error - Raise instead of returning False on delivery failure
    @returns True when the card was accepted by Teams, False otherwise
    """
    card = build_pipeline_report_card(report)
    return await send_adaptive_card(
        card, webhook_url=webhook_url, raise_on_error=raise_on_error
    )
