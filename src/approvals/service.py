"""Approval-driven remediation service backing the end-to-end demo.

The target host's health is modelled after the AION Outsystem healthcheck: a
memory service that can be NOK (high utilization) and a W3SVC service. The memory
metric is simulated so the demo is deterministic, but the remediation is executed
by a real :class:`Executor` backend (Kubernetes rollout restart by default,
optionally Ansible or AWX).
"""

from __future__ import annotations

import logging
import time
import uuid

from src.approvals.executors import Executor, build_executor
from src.approvals.models import (
    ActionSpec,
    ApprovalRequest,
    ApprovalStatus,
    HealthReport,
    ServiceCheck,
)
from src.self_healing.config import PipelineConfig
from src.self_healing.kube import KubeError

logger = logging.getLogger(__name__)

# Memory utilization at or above this percentage is considered NOK.
MEMORY_NOK_THRESHOLD = 80
_UNHEALTHY_MEMORY = 85
_HEALED_MEMORY = 32


class DemoService:
    """Coordinates healthcheck -> recommend -> approve -> execute -> verify.

    A single-instance, in-memory service intended for the demo server. Kubernetes
    reads and the remediation executor are injected so it can be driven by a real
    cluster or by fakes in tests.
    """

    def __init__(
        self,
        kube,
        config: PipelineConfig | None = None,
        executor: Executor | None = None,
    ) -> None:
        self.kube = kube
        self.config = config or PipelineConfig()
        self.executor = executor or build_executor(kube, self.config)
        self.host = "INDIGIINPAPP7"
        self.application = "Outsystem"
        self.memory_percent = _UNHEALTHY_MEMORY
        self._requests: dict[str, ApprovalRequest] = {}

    # --- target lifecycle ---------------------------------------------------

    def reset_target(self) -> HealthReport:
        """Deploy the sample app healthy and seed the simulated high-memory fault."""
        try:
            self.kube.apply(self.config.manifest_path)
            self.kube.set_deployment_image(
                self.config.deployment, self.config.container, self.config.good_image
            )
            self.kube.wait_rollout(self.config.deployment, timeout=self.config.rollout_timeout_seconds)
        except KubeError as exc:  # pragma: no cover - surfaced to the caller/UI
            logger.warning("reset_target could not prepare the cluster: %s", exc)
        self.memory_percent = _UNHEALTHY_MEMORY
        self._requests.clear()
        return self.healthcheck()

    def healthcheck(self) -> HealthReport:
        """Probe the target: real deployment readiness + simulated memory metric."""
        try:
            ready = (
                self.kube.available_replicas(self.config.deployment) >= 1
                and self.kube.ready_endpoint_count(self.config.service) >= 1
            )
        except KubeError as exc:  # pragma: no cover - defensive
            logger.warning("healthcheck kube read failed: %s", exc)
            ready = False

        memory_ok = self.memory_percent < MEMORY_NOK_THRESHOLD
        services = [
            ServiceCheck(
                name="Memory Usage",
                ok=memory_ok,
                detail=(
                    f"Memory usage is High: {self.memory_percent}%"
                    if not memory_ok
                    else f"Memory usage normal: {self.memory_percent}%"
                ),
            ),
            ServiceCheck(name="W3SVC", ok=ready, detail="OK" if ready else "Not serving"),
        ]
        healthy = memory_ok and ready
        return HealthReport(
            host=self.host,
            application=self.application,
            healthy=healthy,
            memory_percent=self.memory_percent,
            deployment_ready=ready,
            services=services,
        )

    # --- recommendation + approval -----------------------------------------

    def recommend_action(self, report: HealthReport) -> ActionSpec | None:
        """Propose a remediation action for an unhealthy report, if one applies."""
        if report.healthy:
            return None
        if report.memory_percent >= MEMORY_NOK_THRESHOLD:
            return ActionSpec(
                action="service_management_outsystem_memory",
                tool=self.executor.tool,
                description="Clear Host Full memory Outsystem",
                parameters={"template_id": "9666", "limit_ip": "10.59.129.87"},
            )
        return ActionSpec(
            action="service_management_outsystem_restart",
            tool=self.executor.tool,
            description="Restart Outsystem application",
            parameters={"template_id": "9665", "limit_ip": "10.59.129.87"},
        )

    def create_approval(self, action: ActionSpec) -> ApprovalRequest:
        """Register a pending approval request for an action."""
        request = ApprovalRequest(
            request_id=f"AR{int(time.time())}{uuid.uuid4().hex[:4].upper()}",
            requestor="AION Alert Aggregator",
            application=self.application,
            host=self.host,
            action=action,
        )
        self._requests[request.request_id] = request
        return request

    def get(self, request_id: str) -> ApprovalRequest | None:
        """Return an approval request by id."""
        return self._requests.get(request_id)

    def reject(self, request_id: str) -> ApprovalRequest:
        """Mark an approval request as rejected."""
        request = self._require(request_id)
        request.status = ApprovalStatus.REJECTED
        return request

    def approve(self, request_id: str) -> ApprovalRequest:
        """Approve a request: execute the remediation and verify the result."""
        request = self._require(request_id)
        if request.status != ApprovalStatus.PENDING:
            return request

        request.status = ApprovalStatus.APPROVED
        execution = self.executor.execute(request.action)
        request.execution = execution
        if execution.success:
            self.memory_percent = _HEALED_MEMORY
        request.verify = self.healthcheck()
        request.status = ApprovalStatus.EXECUTED if execution.success else ApprovalStatus.FAILED
        return request

    def _require(self, request_id: str) -> ApprovalRequest:
        request = self._requests.get(request_id)
        if request is None:
            raise KeyError(f"Unknown approval request: {request_id}")
        return request
