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
# How much memory to allocate in the target to create a real high-memory state.
_LEAK_MEGABYTES = 340
# Fallback values used only when the real cgroup metric cannot be read.
_FALLBACK_UNHEALTHY_MEMORY = 88
_FALLBACK_HEALED_MEMORY = 6


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
        # Identity is derived from the cluster on each healthcheck (see below);
        # these are fallbacks used only before the first read / when reads fail.
        self.host = self.config.namespace
        self.application = self.config.deployment
        self._identity: dict[str, str | None] = {"pod": None, "node": None, "pod_ip": None}
        # Used only when the real cgroup metric cannot be read.
        self._fallback_memory = _FALLBACK_UNHEALTHY_MEMORY
        self._requests: dict[str, ApprovalRequest] = {}

    # --- target lifecycle ---------------------------------------------------

    def reset_target(self) -> HealthReport:
        """Deploy the target, then create a real high-memory state to remediate."""
        try:
            self.kube.apply(self.config.manifest_path)
            # Start from a fresh pod so a prior leak can't stack and OOM the container.
            self.kube.restart_rollout(self.config.deployment)
            self.kube.wait_rollout(self.config.deployment, timeout=self.config.rollout_timeout_seconds)
            # Drive the app into a real high-memory state (held in the pod).
            self.kube.trigger_memory_pressure(self.config.deployment, _LEAK_MEGABYTES)
        except KubeError as exc:  # pragma: no cover - surfaced to the caller/UI
            logger.warning("reset_target could not prepare the cluster: %s", exc)
        self._fallback_memory = _FALLBACK_UNHEALTHY_MEMORY
        self._requests.clear()
        return self.healthcheck()

    def _read_memory_percent(self) -> int:
        """Read the real pod memory %, falling back to the last known state."""
        try:
            measured = self.kube.pod_memory_percent(self.config.deployment)
        except KubeError as exc:  # pragma: no cover - defensive
            logger.warning("memory read failed: %s", exc)
            measured = None
        return measured if measured is not None else self._fallback_memory

    def healthcheck(self) -> HealthReport:
        """Probe the target: real readiness, real pod memory, real cluster identity."""
        try:
            ready = (
                self.kube.available_replicas(self.config.deployment) >= 1
                and self.kube.ready_endpoint_count(self.config.service) >= 1
            )
        except KubeError as exc:  # pragma: no cover - defensive
            logger.warning("healthcheck kube read failed: %s", exc)
            ready = False

        try:
            self._identity = self.kube.pod_identity(self.config.deployment)
        except KubeError as exc:  # pragma: no cover - defensive
            logger.warning("pod identity read failed: %s", exc)

        # Host = the node the workload runs on; application = the deployment name.
        self.host = self._identity.get("node") or self.config.namespace
        self.application = self.config.deployment

        memory_percent = self._read_memory_percent()
        logger.info(
            "healthcheck: node=%s pod=%s memory=%d%% ready=%s",
            self.host, self._identity.get("pod"), memory_percent, ready,
        )
        memory_ok = memory_percent < MEMORY_NOK_THRESHOLD
        services = [
            ServiceCheck(
                name="Memory Usage",
                ok=memory_ok,
                detail=(
                    f"Memory usage is High: {memory_percent}%"
                    if not memory_ok
                    else f"Memory usage normal: {memory_percent}%"
                ),
            ),
            ServiceCheck(name="W3SVC", ok=ready, detail="OK" if ready else "Not serving"),
        ]
        healthy = memory_ok and ready
        return HealthReport(
            host=self.host,
            application=self.application,
            healthy=healthy,
            memory_percent=memory_percent,
            deployment_ready=ready,
            services=services,
            pod=self._identity.get("pod"),
            pod_ip=self._identity.get("pod_ip"),
        )

    # --- recommendation + approval -----------------------------------------

    def recommend_action(self, report: HealthReport) -> ActionSpec | None:
        """Propose a remediation action for an unhealthy report, if one applies."""
        if report.healthy:
            return None
        reason = "high memory usage" if report.memory_percent >= MEMORY_NOK_THRESHOLD else "unready pods"
        return ActionSpec(
            action=f"restart_deployment/{self.config.deployment}",
            tool=self.executor.tool,
            description=(
                f"Restart deployment {self.config.deployment} in namespace "
                f"{self.config.namespace} to remediate {reason}"
            ),
            parameters=self._action_parameters(report),
        )

    def _action_parameters(self, report: HealthReport) -> dict[str, str]:
        """Build remediation parameters from the real cluster identity per backend."""
        if self.executor.tool == "awx":
            return {
                "template_id": self.config.awx_template_id,
                "limit_ip": report.pod_ip or "",
            }
        return {
            "namespace": self.config.namespace,
            "deployment": self.config.deployment,
            "pod": report.pod or "",
            "node": report.host,
        }

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
        logger.info(
            "approve %s: executing '%s' via %s executor",
            request_id, request.action.action, self.executor.tool,
        )
        execution = self.executor.execute(request.action)
        request.execution = execution
        if execution.success:
            # Restart freed the held memory; new pod starts at baseline.
            self._fallback_memory = _FALLBACK_HEALED_MEMORY
        request.verify = self.healthcheck()
        request.status = ApprovalStatus.EXECUTED if execution.success else ApprovalStatus.FAILED
        return request

    def autonomous_remediate(self) -> dict:
        """Detect -> recommend -> execute -> verify with NO human approval (AIOps mode).

        Intended for high-confidence, low-risk actions. Returns the pre-check report
        and the executed request (with verification), or acted=False when healthy.
        """
        logger.info("autonomous: begin (no approval gate)")
        before = self.healthcheck()
        if before.healthy:
            return {"before": before, "acted": False, "request": None}
        action = self.recommend_action(before)
        if action is None:
            return {"before": before, "acted": False, "request": None}
        logger.info("autonomous: policy autoFixable -> auto-approving '%s'", action.action)
        request = self.create_approval(action)
        decided = self.approve(request.request_id)  # executes + verifies, no human
        return {"before": before, "acted": True, "request": decided}

    def _require(self, request_id: str) -> ApprovalRequest:
        request = self._requests.get(request_id)
        if request is None:
            raise KeyError(f"Unknown approval request: {request_id}")
        return request
