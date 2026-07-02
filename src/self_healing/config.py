"""Configuration for the self-healing pipeline against a local Kubernetes cluster."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Repository-root-relative default manifest for the sample workload.
_DEFAULT_MANIFEST = str(Path(__file__).resolve().parents[2] / "deploy" / "sample-app.yaml")


@dataclass(frozen=True)
class PipelineConfig:
    """Static configuration describing the workload the pipeline heals.

    The sample workload is intentionally deployed with a broken image tag so the
    pipeline can demonstrate detect -> classify -> fix -> validate against a real
    cluster without building a custom container image.
    """

    namespace: str = "self-healing"
    deployment: str = "sample-app"
    container: str = "whoami"
    service: str = "sample-app"

    # Known-good image the L2 fix resets to, and the broken tag used to seed drift.
    good_image: str = "traefik/whoami:v1.10.1"
    broken_image: str = "traefik/whoami:v9.9.9-broken-drift"

    # A valid deployed tag must match this pattern (semver like "v1.10.1").
    expected_tag_pattern: str = r"^v\d+\.\d+\.\d+$"

    manifest_path: str = _DEFAULT_MANIFEST
    context: str | None = None  # kube context; None => current context

    # AWX job template id used only when the AWX executor is selected.
    awx_template_id: str = ""

    rollout_timeout_seconds: int = 120

    # >= this many concurrent failures is treated as a systemic incident (escalate all).
    systemic_failure_threshold: int = 20
