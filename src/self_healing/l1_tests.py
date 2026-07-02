"""L1 test phase: probe the deployed workload and emit structured failures.

This is the local-cluster analogue of the spec's Playwright/pytest L1 suite. Rather
than driving a browser, it asserts the two properties that matter for a deployed
service: the deployment reports available replicas, and its service has at least
one ready endpoint (which only happens when pods pass readiness).
"""

from __future__ import annotations

import logging
import re

from src.self_healing.config import PipelineConfig
from src.self_healing.kube import KubeClient
from src.self_healing.models import Failure

logger = logging.getLogger(__name__)

# Pod container "waiting" reasons that indicate an image problem.
_IMAGE_ERROR_REASONS = {"ImagePullBackOff", "ErrImagePull", "InvalidImageName"}
_CRASH_REASONS = {"CrashLoopBackOff", "RunContainerError"}


def _derive_signal(waiting_reasons: list[str]) -> str:
    """Map raw pod waiting reasons to a coverage-matrix signal."""
    for reason in waiting_reasons:
        if reason in _IMAGE_ERROR_REASONS:
            return "image_pull_error"
        if reason in _CRASH_REASONS:
            return "crash_loop"
    return "not_ready"


def run_l1_tests(kube: KubeClient, config: PipelineConfig) -> list[Failure]:
    """Run the L1 readiness/drift checks against the configured deployment.

    @param kube - kubectl client scoped to the target namespace
    @param config - pipeline configuration describing the workload
    @returns List of failures (empty when the workload is healthy)
    """
    failures: list[Failure] = []

    available = kube.available_replicas(config.deployment)
    endpoints = kube.ready_endpoint_count(config.service)
    image = kube.get_deployment_image(config.deployment, config.container)

    if available < 1 or endpoints < 1:
        waiting_reasons = [
            pod.waiting_reason
            for pod in kube.pod_infos(f"app={config.deployment}")
            if pod.waiting_reason
        ]
        signal = _derive_signal(waiting_reasons)
        failures.append(
            Failure(
                failure_id="F001",
                title=f"{config.deployment} has no ready endpoints",
                error=(
                    f"availableReplicas={available}, endpoints={endpoints}, "
                    f"podWaiting={waiting_reasons or 'none'}"
                ),
                category="infra",
                signal=signal,
                deployment=config.deployment,
                namespace=config.namespace,
                container=config.container,
                image=image,
            )
        )
        return failures

    # Healthy pods but a drifted image tag is still a (lower-severity) regression.
    tag = image.split(":")[-1] if image and ":" in image else (image or "")
    if image and not re.search(config.expected_tag_pattern, tag):
        failures.append(
            Failure(
                failure_id="F002",
                title=f"{config.deployment} is running a drifted image tag",
                error=f"image={image} does not match expected pattern {config.expected_tag_pattern}",
                category="drift",
                signal="image_drift",
                deployment=config.deployment,
                namespace=config.namespace,
                container=config.container,
                image=image,
            )
        )

    return failures
