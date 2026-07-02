"""Human-in-the-loop approval workflow for remediation actions.

Reproduces the AION "Action Approval Required" flow: an unhealthy healthcheck
produces a recommended action, an interactive Adaptive Card asks a human to
Approve/Reject, and on approval the remediation is executed by a pluggable
backend (Kubernetes / Ansible / AWX) and verified.
"""

from src.approvals.cards import (
    build_approval_card,
    build_healthcheck_card,
    build_result_card,
)
from src.approvals.executors import (
    AnsibleExecutor,
    AwxExecutor,
    Executor,
    KubernetesExecutor,
    build_executor,
)
from src.approvals.models import (
    ActionSpec,
    ApprovalRequest,
    ApprovalStatus,
    ExecutionResult,
    HealthReport,
    ServiceCheck,
)
from src.approvals.service import DemoService

__all__ = [
    "build_approval_card",
    "build_healthcheck_card",
    "build_result_card",
    "AnsibleExecutor",
    "AwxExecutor",
    "Executor",
    "KubernetesExecutor",
    "build_executor",
    "ActionSpec",
    "ApprovalRequest",
    "ApprovalStatus",
    "ExecutionResult",
    "HealthReport",
    "ServiceCheck",
    "DemoService",
]
