"""L2 fix phase: apply the runbook remediation for a classified failure.

Only two mutating actions are supported, matching the coverage matrix: resetting a
deployment's image to the known-good tag, and restarting a rollout. Anything the
runbook marks as non-auto-fixable is escalated without touching the cluster.
"""

from __future__ import annotations

import logging

from src.self_healing.config import PipelineConfig
from src.self_healing.kube import KubeClient, KubeError
from src.self_healing.models import Classification, FixOutcome

logger = logging.getLogger(__name__)


def apply_fix(
    kube: KubeClient, classification: Classification, config: PipelineConfig
) -> FixOutcome:
    """Attempt to remediate a single classified failure.

    @param kube - kubectl client scoped to the target namespace
    @param classification - failure paired with its coverage-matrix runbook
    @param config - pipeline configuration (known-good image, timeouts)
    @returns FixOutcome describing whether the failure was fixed or escalated
    """
    failure = classification.failure
    runbook = classification.runbook

    if not classification.is_auto_fixable:
        return FixOutcome(
            failure_id=failure.failure_id,
            fixed=False,
            escalated=True,
            detail="No automated remediation available for this signal.",
            runbook_id=runbook.runbook_id,
            reason=runbook.action,
        )

    deployment = failure.deployment or config.deployment
    try:
        if runbook.fix == "reset_image":
            return _reset_image(kube, deployment, config, runbook.runbook_id, failure.failure_id)
        if runbook.fix == "restart_rollout":
            return _restart_rollout(
                kube, deployment, config, runbook.runbook_id, failure.failure_id
            )
    except KubeError as exc:
        logger.warning("Fix for %s failed: %s", failure.failure_id, exc)
        return FixOutcome(
            failure_id=failure.failure_id,
            fixed=False,
            escalated=True,
            detail=f"Remediation raised an error: {exc}",
            runbook_id=runbook.runbook_id,
            reason=str(exc),
        )

    return FixOutcome(
        failure_id=failure.failure_id,
        fixed=False,
        escalated=True,
        detail=f"Unknown fix action '{runbook.fix}'.",
        runbook_id=runbook.runbook_id,
        reason=f"unsupported fix action {runbook.fix}",
    )


def _reset_image(
    kube: KubeClient,
    deployment: str,
    config: PipelineConfig,
    runbook_id: str,
    failure_id: str,
) -> FixOutcome:
    """Reset a deployment's image to the known-good tag and wait for rollout."""
    kube.set_deployment_image(deployment, config.container, config.good_image)
    rolled_out = kube.wait_rollout(deployment, timeout=config.rollout_timeout_seconds)
    return FixOutcome(
        failure_id=failure_id,
        fixed=rolled_out,
        escalated=not rolled_out,
        detail=(
            f"Set image -> {config.good_image}; "
            f"rollout {'succeeded' if rolled_out else 'did not complete in time'}"
        ),
        runbook_id=runbook_id,
        reason=None if rolled_out else "rollout timed out after image reset",
    )


def _restart_rollout(
    kube: KubeClient,
    deployment: str,
    config: PipelineConfig,
    runbook_id: str,
    failure_id: str,
) -> FixOutcome:
    """Restart a deployment rollout and wait for it to complete."""
    kube.restart_rollout(deployment)
    rolled_out = kube.wait_rollout(deployment, timeout=config.rollout_timeout_seconds)
    return FixOutcome(
        failure_id=failure_id,
        fixed=rolled_out,
        escalated=not rolled_out,
        detail=f"Restarted rollout; {'succeeded' if rolled_out else 'timed out'}",
        runbook_id=runbook_id,
        reason=None if rolled_out else "rollout timed out after restart",
    )
