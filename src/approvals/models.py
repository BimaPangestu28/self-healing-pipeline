"""Domain models for the approval-driven remediation flow."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ApprovalStatus(str, Enum):
    """Lifecycle of an approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    FAILED = "failed"


@dataclass(frozen=True)
class ServiceCheck:
    """Result of a single service probe within a healthcheck."""

    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class HealthReport:
    """Outcome of an Outsystem-style healthcheck for one host."""

    host: str
    application: str
    healthy: bool
    memory_percent: int
    deployment_ready: bool
    services: list[ServiceCheck]


@dataclass(frozen=True)
class ActionSpec:
    """A remediation action proposed for approval."""

    action: str
    tool: str
    description: str
    parameters: dict[str, str]


@dataclass(frozen=True)
class ExecutionResult:
    """Outcome of executing a remediation action via some executor backend."""

    success: bool
    tool: str
    job_id: str
    template_id: str
    target_host: str
    duration_seconds: float
    detail: str = ""


@dataclass
class ApprovalRequest:
    """A pending/decided approval for a remediation action."""

    request_id: str
    requestor: str
    application: str
    host: str
    action: ActionSpec
    status: ApprovalStatus = ApprovalStatus.PENDING
    execution: ExecutionResult | None = None
    verify: HealthReport | None = None
