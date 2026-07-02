"""Coverage matrix / runbook lookup that classifies failures into fix tiers.

Mirrors Phase 2 of the pipeline spec: each known failure signal maps to a runbook
entry describing the confidence tier, the remediation action, and the maximum
number of fix attempts. Unknown signals fall through to an ``escalate`` runbook.
"""

from __future__ import annotations

from src.self_healing.models import Classification, Failure, FixTier, Runbook

# Signal -> runbook. Signals are produced by the L1 test phase (see l1_tests.py).
COVERAGE_MATRIX: dict[str, Runbook] = {
    "image_pull_error": Runbook(
        runbook_id="RB-INFRA-001",
        tier=FixTier.AUTO_FIXABLE,
        action="Reset deployment image to the known-good tag",
        category="infra",
        max_attempts=3,
        fix="reset_image",
    ),
    "image_drift": Runbook(
        runbook_id="RB-DRIFT-001",
        tier=FixTier.AUTO_FIXABLE,
        action="Reset drifted image tag to the known-good CI tag",
        category="drift",
        max_attempts=3,
        fix="reset_image",
    ),
    "crash_loop": Runbook(
        runbook_id="RB-INFRA-002",
        tier=FixTier.GUIDED,
        action="Restart the rollout to clear a transient crash loop",
        category="infra",
        max_attempts=2,
        fix="restart_rollout",
    ),
    "not_ready": Runbook(
        runbook_id="RB-INFRA-003",
        tier=FixTier.GUIDED,
        action="Restart the rollout to recover unready pods",
        category="infra",
        max_attempts=2,
        fix="restart_rollout",
    ),
}

# Fallback for signals with no matching runbook entry.
ESCALATE_RUNBOOK = Runbook(
    runbook_id="RB-ESCALATE",
    tier=FixTier.ESCALATE,
    action="No matching runbook; escalate to a human",
    category="unknown",
    max_attempts=0,
    fix=None,
)


def classify(failure: Failure) -> Classification:
    """Match a failure to its coverage-matrix runbook.

    @param failure - Failure detected by the L1 test phase
    @returns Classification pairing the failure with a runbook (escalate if unknown)
    """
    runbook = COVERAGE_MATRIX.get(failure.signal, ESCALATE_RUNBOOK)
    return Classification(failure=failure, runbook=runbook)


def matrix_coverage() -> dict[str, int]:
    """Return simple coverage stats for the report/telemetry."""
    total = len(COVERAGE_MATRIX)
    auto_fixable = sum(1 for rb in COVERAGE_MATRIX.values() if rb.tier == FixTier.AUTO_FIXABLE)
    return {"signals": total, "auto_fixable": auto_fixable}
