"""Pluggable remediation executors.

The approval service delegates the actual remediation to an :class:`Executor`.
Three backends are provided:

- :class:`KubernetesExecutor` — a ``kubectl rollout restart`` on the local cluster
  (zero external dependencies; the default).
- :class:`AnsibleExecutor` — runs a real ``ansible-playbook`` locally (the playbook
  restarts the workload), mirroring the spec's Ansible remediation.
- :class:`AwxExecutor` — launches an AWX/Tower job template over the REST API and
  polls it to completion (matching the production template_id-driven flow).

``build_executor`` selects a backend from environment variables so the demo can
switch backends without code changes.
"""

from __future__ import annotations

import abc
import logging
import os
import subprocess
import time
from pathlib import Path

import httpx

from src.approvals.models import ActionSpec, ExecutionResult
from src.self_healing.config import PipelineConfig
from src.self_healing.kube import KubeError

logger = logging.getLogger(__name__)

_DEFAULT_PLAYBOOK = str(Path(__file__).resolve().parents[2] / "deploy" / "ansible" / "restart_app.yml")


def _job_id() -> str:
    """Synthesize a short numeric job id for display."""
    return str(int(time.time()))[-7:]


class Executor(abc.ABC):
    """Executes an approved remediation action and reports the result."""

    tool: str = "generic"

    @abc.abstractmethod
    def execute(self, action: ActionSpec) -> ExecutionResult:
        """Run the remediation for an action and return a structured result."""


class KubernetesExecutor(Executor):
    """Remediates by restarting the target deployment on the cluster."""

    tool = "kubernetes"

    def __init__(self, kube, config: PipelineConfig) -> None:
        self.kube = kube
        self.config = config

    def execute(self, action: ActionSpec) -> ExecutionResult:
        started = time.time()
        success = False
        detail = ""
        try:
            self.kube.restart_rollout(self.config.deployment)
            success = self.kube.wait_rollout(
                self.config.deployment, timeout=self.config.rollout_timeout_seconds
            )
            detail = "rollout restart completed" if success else "rollout did not complete"
        except KubeError as exc:  # pragma: no cover - surfaced to the UI
            logger.warning("kubernetes remediation failed: %s", exc)
            detail = str(exc)
        return ExecutionResult(
            success=success,
            tool=self.tool,
            job_id=_job_id(),
            template_id=action.parameters.get("template_id", ""),
            target_host=action.parameters.get("limit_ip", ""),
            duration_seconds=round(time.time() - started, 3),
            detail=detail,
        )


class AnsibleExecutor(Executor):
    """Remediates by running a real ansible-playbook locally."""

    tool = "ansible"

    def __init__(self, config: PipelineConfig, playbook: str | None = None) -> None:
        self.config = config
        self.playbook = playbook or _DEFAULT_PLAYBOOK

    def execute(self, action: ActionSpec) -> ExecutionResult:
        started = time.time()
        command = [
            "ansible-playbook",
            self.playbook,
            "-i",
            "localhost,",
            "-c",
            "local",
            "-e",
            f"namespace={self.config.namespace}",
            "-e",
            f"deployment={self.config.deployment}",
            "-e",
            f"timeout_seconds={self.config.rollout_timeout_seconds}",
        ]
        success = False
        detail = ""
        try:
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.config.rollout_timeout_seconds + 60,
            )
            success = proc.returncode == 0
            output = proc.stdout if success else (proc.stderr or proc.stdout)
            detail = output.strip()[-600:]
        except FileNotFoundError:
            detail = "ansible-playbook not found on PATH"
        except subprocess.TimeoutExpired:
            detail = "ansible-playbook timed out"

        return ExecutionResult(
            success=success,
            tool=self.tool,
            job_id=_job_id(),
            template_id=action.parameters.get("template_id", ""),
            target_host=action.parameters.get("limit_ip", ""),
            duration_seconds=round(time.time() - started, 3),
            detail=detail,
        )


class AwxExecutor(Executor):
    """Remediates by launching an AWX/Tower job template over the REST API."""

    tool = "awx"

    def __init__(
        self,
        config: PipelineConfig,
        base_url: str,
        token: str = "",
        poll_interval: float = 2.0,
        max_polls: int = 60,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.config = config
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.poll_interval = poll_interval
        self.max_polls = max_polls
        self._transport = transport

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=30.0, transport=self._transport)

    def execute(self, action: ActionSpec) -> ExecutionResult:
        started = time.time()
        template_id = action.parameters.get("template_id", "")
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        job_id = ""
        status = "unknown"
        try:
            with self._client() as client:
                launch = client.post(
                    f"{self.base_url}/api/v2/job_templates/{template_id}/launch/",
                    headers=headers,
                    json={"limit": action.parameters.get("limit_ip", "")},
                )
                launch.raise_for_status()
                launched = launch.json()
                job_id = str(launched.get("id") or launched.get("job") or "")
                status = launched.get("status", "pending")

                for _ in range(self.max_polls):
                    if status in {"successful", "failed", "error", "canceled"}:
                        break
                    poll = client.get(f"{self.base_url}/api/v2/jobs/{job_id}/", headers=headers)
                    poll.raise_for_status()
                    status = poll.json().get("status", status)
                    if status in {"successful", "failed", "error", "canceled"}:
                        break
                    time.sleep(self.poll_interval)
        except httpx.HTTPError as exc:
            logger.warning("AWX remediation failed: %s", exc)
            return ExecutionResult(
                success=False,
                tool=self.tool,
                job_id=job_id,
                template_id=template_id,
                target_host=action.parameters.get("limit_ip", ""),
                duration_seconds=round(time.time() - started, 3),
                detail=str(exc),
            )

        return ExecutionResult(
            success=status == "successful",
            tool=self.tool,
            job_id=job_id,
            template_id=template_id,
            target_host=action.parameters.get("limit_ip", ""),
            duration_seconds=round(time.time() - started, 3),
            detail=f"awx job status={status}",
        )


def build_executor(kube, config: PipelineConfig) -> Executor:
    """Select a remediation executor from environment configuration.

    - ``AWX_URL`` set (or ``EXECUTOR=awx``) -> AwxExecutor
    - ``EXECUTOR=ansible`` -> AnsibleExecutor
    - otherwise -> KubernetesExecutor (default)
    """
    mode = os.getenv("EXECUTOR", "").strip().lower()
    awx_url = os.getenv("AWX_URL", "").strip()

    if awx_url or mode == "awx":
        return AwxExecutor(config, base_url=awx_url, token=os.getenv("AWX_TOKEN", "").strip())
    if mode == "ansible":
        return AnsibleExecutor(config)
    return KubernetesExecutor(kube, config)
