"""Microsoft Teams notification layer using Adaptive Cards.

Renders structured SRE and self-healing pipeline payloads into Adaptive Cards
and delivers them to a Microsoft Teams incoming webhook (Power Automate
"Workflows" webhook or a classic Office 365 connector).
"""

from src.notifications.adaptive_cards import (
    build_alert_card,
    build_pipeline_report_card,
    wrap_as_teams_message,
)
from src.notifications.models import (
    EscalatedItem,
    FixedItem,
    PipelineReport,
    PipelineReportResponse,
    PodStatus,
)
from src.notifications.teams import (
    TeamsNotificationError,
    send_adaptive_card,
    send_pipeline_report,
)

__all__ = [
    "build_alert_card",
    "build_pipeline_report_card",
    "wrap_as_teams_message",
    "EscalatedItem",
    "FixedItem",
    "PipelineReport",
    "PipelineReportResponse",
    "PodStatus",
    "TeamsNotificationError",
    "send_adaptive_card",
    "send_pipeline_report",
]
