"""Human-in-the-loop approval workflow for remediation actions.

Reproduces the AION "Action Approval Required" flow: an unhealthy healthcheck
produces a recommended action, an interactive Adaptive Card asks a human to
Approve/Reject, and on approval the remediation is executed against the cluster
and verified.
"""

from src.approvals.cards import (
    build_approval_card,
    build_healthcheck_card,
    build_result_card,
)
from src.approvals.service import (
    ActionSpec,
    ApprovalRequest,
    ApprovalStatus,
    DemoService,
    HealthReport,
    ServiceCheck,
)

__all__ = [
    "build_approval_card",
    "build_healthcheck_card",
    "build_result_card",
    "ActionSpec",
    "ApprovalRequest",
    "ApprovalStatus",
    "DemoService",
    "HealthReport",
    "ServiceCheck",
]
