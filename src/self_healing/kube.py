"""Thin kubectl wrapper for the self-healing pipeline.

Shells out to ``kubectl``; every method returns plain Python values so the
orchestrator stays free of subprocess and JSON-parsing details. Only the minimal
mutating operations required for remediation are exposed (set image, rollout
restart), keeping the surface area auditable.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass

from src import tool_trace

logger = logging.getLogger(__name__)


class KubeError(RuntimeError):
    """Raised when a kubectl invocation fails unexpectedly."""


@dataclass(frozen=True)
class PodInfo:
    """Condensed pod state used to derive failure signals."""

    name: str
    phase: str
    ready: bool
    waiting_reason: str | None


class KubeClient:
    """Namespaced kubectl client scoped to a single kube context."""

    def __init__(
        self,
        namespace: str = "self-healing",
        context: str | None = None,
        kubectl: str = "kubectl",
    ) -> None:
        self.namespace = namespace
        self.context = context
        self.kubectl = kubectl

    def _command(self, args: list[str], *, namespaced: bool = True) -> list[str]:
        """Assemble a full kubectl command with context/namespace flags."""
        command = [self.kubectl]
        if self.context:
            command += ["--context", self.context]
        if namespaced:
            command += ["--namespace", self.namespace]
        return command + args

    def _run(
        self,
        args: list[str],
        *,
        namespaced: bool = True,
        check: bool = True,
        timeout: float = 60.0,
    ) -> subprocess.CompletedProcess[str]:
        """Run a kubectl command, raising KubeError on failure when ``check`` is set."""
        command = self._command(args, namespaced=namespaced)
        logger.info("kubectl %s", " ".join(args))
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=timeout
            )
        except subprocess.TimeoutExpired as exc:
            raise KubeError(f"kubectl timed out: {' '.join(args)}") from exc
        except FileNotFoundError as exc:
            raise KubeError(f"kubectl executable not found: {self.kubectl}") from exc

        produced = (result.stdout or result.stderr or "").strip()
        tool_trace.record(
            tool="kubectl",
            input=" ".join(args),
            output=produced or "(no output)",
            ok=result.returncode == 0,
        )

        if check and result.returncode != 0:
            raise KubeError(
                f"kubectl {' '.join(args)} failed ({result.returncode}): {result.stderr.strip()}"
            )
        return result

    # --- cluster / manifest -------------------------------------------------

    def cluster_reachable(self) -> bool:
        """Return True when the API server responds to a version query."""
        result = self._run(["version", "-o", "json"], namespaced=False, check=False, timeout=30)
        return result.returncode == 0

    def apply(self, manifest_path: str) -> None:
        """Apply a manifest file (namespaces declared in the manifest are honored)."""
        self._run(["apply", "-f", manifest_path], namespaced=False)

    # --- deployment reads ---------------------------------------------------

    def get_deployment_image(self, deployment: str, container: str) -> str | None:
        """Return the image reference for a container in a deployment, or None."""
        jsonpath = (
            "{.spec.template.spec.containers[?(@.name=='" + container + "')].image}"
        )
        result = self._run(
            ["get", "deployment", deployment, "-o", f"jsonpath={jsonpath}"],
            check=False,
        )
        image = result.stdout.strip()
        return image or None

    def available_replicas(self, deployment: str) -> int:
        """Return the number of available replicas (0 when unset/absent)."""
        result = self._run(
            ["get", "deployment", deployment, "-o", "jsonpath={.status.availableReplicas}"],
            check=False,
        )
        return _safe_int(result.stdout.strip())

    def ready_endpoint_count(self, service: str) -> int:
        """Return the number of ready backend IPs behind a service.

        A service only lists endpoint addresses for pods that pass readiness, so a
        non-zero count is a reliable "the app is actually serving" signal.
        """
        result = self._run(
            ["get", "endpoints", service, "-o", "jsonpath={.subsets[*].addresses[*].ip}"],
            check=False,
        )
        return len([ip for ip in result.stdout.split() if ip.strip()])

    def pod_infos(self, selector: str) -> list[PodInfo]:
        """Return condensed pod state for pods matching a label selector."""
        result = self._run(["get", "pods", "-l", selector, "-o", "json"], check=False)
        if result.returncode != 0 or not result.stdout.strip():
            return []

        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            return []

        infos: list[PodInfo] = []
        for item in payload.get("items", []):
            status = item.get("status", {})
            container_statuses = status.get("containerStatuses") or []
            ready = (
                all(cs.get("ready") for cs in container_statuses)
                if container_statuses
                else False
            )
            waiting_reason = None
            for container_status in container_statuses:
                waiting = container_status.get("state", {}).get("waiting")
                if waiting and waiting.get("reason"):
                    waiting_reason = waiting["reason"]
                    break
            infos.append(
                PodInfo(
                    name=item.get("metadata", {}).get("name", "unknown"),
                    phase=status.get("phase", "Unknown"),
                    ready=ready,
                    waiting_reason=waiting_reason,
                )
            )
        return infos

    # --- real memory metric (via pod cgroup) --------------------------------

    def _first_running_pod(self, deployment: str) -> str | None:
        """Return the newest Ready, non-terminating pod for a deployment, or None.

        Picking the newest Ready pod (and excluding pods with a deletionTimestamp)
        avoids racing with a pod that is still terminating from a prior restart.
        """
        result = self._run(["get", "pods", "-l", f"app={deployment}", "-o", "json"], check=False)
        if result.returncode != 0 or not result.stdout.strip():
            return None
        try:
            items = json.loads(result.stdout).get("items", [])
        except json.JSONDecodeError:
            return None

        candidates: list[tuple[str, str]] = []
        for item in items:
            metadata = item.get("metadata", {})
            status = item.get("status", {})
            if metadata.get("deletionTimestamp"):
                continue
            if status.get("phase") != "Running":
                continue
            container_statuses = status.get("containerStatuses") or []
            if container_statuses and not all(cs.get("ready") for cs in container_statuses):
                continue
            candidates.append((metadata.get("creationTimestamp", ""), metadata.get("name", "")))

        if not candidates:
            return None
        candidates.sort()  # ISO timestamps sort chronologically; newest is last
        return candidates[-1][1] or None

    def _exec_read(self, pod: str, shell_command: str) -> str | None:
        """Run a shell command in a pod and return its stripped stdout, or None."""
        result = self._run(
            ["exec", pod, "--", "sh", "-c", shell_command], check=False, timeout=15
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip()

    def pod_memory_percent(self, deployment: str) -> int | None:
        """Return a pod's memory usage as a percentage of its limit, read from cgroup.

        Reads the container cgroup (v2 first, then v1) inside a Running pod, so the
        value is the real, current memory usage — no metrics-server lag. Returns
        None when it cannot be determined (e.g. no pod, no shell, no limit set).
        """
        pod = self._first_running_pod(deployment)
        if not pod:
            return None

        used = self._exec_read(pod, "cat /sys/fs/cgroup/memory.current 2>/dev/null")
        limit = self._exec_read(pod, "cat /sys/fs/cgroup/memory.max 2>/dev/null")
        if used is None or not limit or limit == "max":
            # cgroup v1 fallback
            used = self._exec_read(pod, "cat /sys/fs/cgroup/memory/memory.usage_in_bytes 2>/dev/null")
            limit = self._exec_read(pod, "cat /sys/fs/cgroup/memory/memory.limit_in_bytes 2>/dev/null")

        try:
            used_bytes = int(used)
            limit_bytes = int(limit)
        except (TypeError, ValueError):
            return None
        if limit_bytes <= 0:
            return None
        return max(0, min(100, round(used_bytes / limit_bytes * 100)))

    def pod_identity(self, deployment: str) -> dict[str, str | None]:
        """Return real identity of the deployment's pod: {pod, node, pod_ip}."""
        pod = self._first_running_pod(deployment)
        if not pod:
            return {"pod": None, "node": None, "pod_ip": None}
        result = self._run(
            ["get", "pod", pod, "-o", "jsonpath={.spec.nodeName}|{.status.podIP}"],
            check=False,
        )
        node, _, pod_ip = result.stdout.strip().partition("|")
        return {"pod": pod, "node": node or None, "pod_ip": pod_ip or None}

    def trigger_memory_pressure(self, deployment: str, megabytes: int) -> bool:
        """Ask the target app (via its pod) to allocate and hold N MB of memory."""
        pod = self._first_running_pod(deployment)
        if not pod:
            return False
        code = (
            "import urllib.request;"
            f"urllib.request.urlopen('http://localhost:8080/leak?mb={megabytes}', timeout=10).read()"
        )
        result = self._run(
            ["exec", pod, "--", "python", "-c", code], check=False, timeout=30
        )
        return result.returncode == 0

    # --- mutating remediation ----------------------------------------------

    def set_deployment_image(self, deployment: str, container: str, image: str) -> None:
        """Set the container image on a deployment (triggers a rollout)."""
        self._run(["set", "image", f"deployment/{deployment}", f"{container}={image}"])

    def restart_rollout(self, deployment: str) -> None:
        """Trigger a rolling restart of a deployment."""
        self._run(["rollout", "restart", f"deployment/{deployment}"])

    def scale_deployment(self, deployment: str, replicas: int) -> None:
        """Scale a deployment to the given replica count."""
        self._run(["scale", f"deployment/{deployment}", f"--replicas={replicas}"])

    def desired_replicas(self, deployment: str) -> int:
        """Return the deployment's desired replica count (spec.replicas)."""
        result = self._run(
            ["get", "deployment", deployment, "-o", "jsonpath={.spec.replicas}"],
            check=False,
        )
        return _safe_int(result.stdout.strip())

    def wait_rollout(self, deployment: str, timeout: int = 120) -> bool:
        """Wait for a deployment rollout to complete; return True on success."""
        result = self._run(
            ["rollout", "status", f"deployment/{deployment}", f"--timeout={timeout}s"],
            check=False,
            timeout=timeout + 15,
        )
        return result.returncode == 0


def _safe_int(value: str) -> int:
    """Parse an integer from kubectl output, treating blanks as 0."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
