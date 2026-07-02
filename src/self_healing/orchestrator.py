"""Orchestrator that runs the self-healing phases and produces a Teams report.

Wires together the L1 test, classify, L2 fix, and validation phases, then maps the
outcomes onto a :class:`PipelineReport` for Adaptive Card delivery. Kubernetes
access is injected as a duck-typed client so the orchestrator is unit-testable
without a cluster (see tests/test_self_healing.py).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.notifications.models import EscalatedItem, FixedItem, PipelineReport, PodStatus
from src.self_healing.config import PipelineConfig
from src.self_healing.l1_tests import run_l1_tests
from src.self_healing.l2_fix import apply_fix
from src.self_healing.models import Classification, Failure, FixOutcome, FixTier
from src.self_healing.runbook import classify

logger = logging.getLogger(__name__)


@dataclass
class PipelineRunResult:
    """Full result of a pipeline run: the Teams report plus a phase-by-phase log."""

    report: PipelineReport
    phase_log: list[str] = field(default_factory=list)
    initial_failures: list[Failure] = field(default_factory=list)
    fix_outcomes: list[FixOutcome] = field(default_factory=list)
    remaining_failures: list[Failure] = field(default_factory=list)


class SelfHealingPipeline:
    """Runs detect -> classify -> fix -> validate -> report against one workload."""

    def __init__(self, kube, config: PipelineConfig | None = None) -> None:
        self.kube = kube
        self.config = config or PipelineConfig()

    def run(self, run_date: str) -> PipelineRunResult:
        """Execute the full pipeline once and return the report and phase log.

        @param run_date - Human-readable run date embedded in the report
        @returns PipelineRunResult with the Teams report and diagnostic phase log
        """
        log: list[str] = []

        # Phase 0/1 — drift + L1 readiness checks.
        initial_failures = run_l1_tests(self.kube, self.config)
        log.append(f"Phase 1 (L1): {len(initial_failures)} failure(s) detected")

        if not initial_failures:
            log.append("No failures — nothing to heal.")
            report = self._build_report(
                run_date, [], [], [], [], remaining=[]
            )
            return PipelineRunResult(report=report, phase_log=log)

        # Phase 2 — classify against the coverage matrix.
        classifications = [classify(failure) for failure in initial_failures]
        for classification in classifications:
            log.append(
                f"Phase 2 (Classify): {classification.failure.failure_id} "
                f"-> {classification.tier.value} ({classification.runbook.runbook_id})"
            )

        # Systemic guard — too many concurrent failures means don't auto-fix.
        if len(initial_failures) >= self.config.systemic_failure_threshold:
            log.append("Systemic incident detected — skipping L2, escalating all.")
            report = self._build_report(
                run_date, initial_failures, classifications, [], [], remaining=initial_failures
            )
            return PipelineRunResult(
                report=report,
                phase_log=log,
                initial_failures=initial_failures,
                remaining_failures=initial_failures,
            )

        # Phase 3 — L2 remediation for auto-fixable failures.
        outcomes: list[FixOutcome] = []
        for classification in classifications:
            outcome = apply_fix(self.kube, classification, self.config)
            outcomes.append(outcome)
            log.append(
                f"Phase 3 (L2): {outcome.failure_id} "
                f"{'FIXED' if outcome.fixed else 'ESCALATED'} — {outcome.detail}"
            )

        # Phase 5 — validation: re-run L1 to confirm the fixes.
        remaining = run_l1_tests(self.kube, self.config)
        log.append(f"Phase 5 (Validation): {len(remaining)} failure(s) remain")

        report = self._build_report(
            run_date, initial_failures, classifications, outcomes, [], remaining=remaining
        )
        return PipelineRunResult(
            report=report,
            phase_log=log,
            initial_failures=initial_failures,
            fix_outcomes=outcomes,
            remaining_failures=remaining,
        )

    def _build_report(
        self,
        run_date: str,
        initial_failures: list[Failure],
        classifications: list[Classification],
        outcomes: list[FixOutcome],
        _unused: list,
        *,
        remaining: list[Failure],
    ) -> PipelineReport:
        """Map phase results onto a PipelineReport for Adaptive Card delivery."""
        total_checks = 1  # one deployment health check in this local scenario
        failed = 1 if initial_failures else 0
        passed = total_checks - failed

        auto_fixable = sum(
            1 for c in classifications if c.tier == FixTier.AUTO_FIXABLE
        )
        escalated_count = sum(1 for c in classifications if c.tier == FixTier.ESCALATE)
        test_issues = sum(1 for c in classifications if c.tier == FixTier.TEST_ISSUE)

        fixed_outcomes = [o for o in outcomes if o.fixed]
        escalated_outcomes = [o for o in outcomes if o.escalated]

        failure_by_id = {f.failure_id: f for f in initial_failures}
        fixed_items = [
            FixedItem(
                failure_id=o.failure_id,
                description=failure_by_id.get(o.failure_id, _blank_failure()).title,
                runbook_id=o.runbook_id,
            )
            for o in fixed_outcomes
        ]
        escalated_items = [
            EscalatedItem(
                failure_id=o.failure_id,
                description=failure_by_id.get(o.failure_id, _blank_failure()).title,
                reason=o.reason or o.detail,
            )
            for o in escalated_outcomes
        ]

        pod_statuses = self._pod_statuses()
        staging_deployed = bool(fixed_outcomes)
        status = self._overall_status(initial_failures, remaining, escalated_outcomes)

        return PipelineReport(
            run_date=run_date,
            status=status,
            l1_passed=passed,
            l1_failed=failed,
            l1_skipped=0,
            l1_total=total_checks,
            auto_fixable=auto_fixable,
            escalated_count=escalated_count,
            test_issues=test_issues,
            l2_fixed=len(fixed_outcomes),
            l2_escalated=len(escalated_outcomes),
            l2_test_issues=0,
            staging_deployed=staging_deployed,
            validation_passing=total_checks - (1 if remaining else 0) if initial_failures else 0,
            validation_target=1 if initial_failures else 0,
            merge_request_created=False,
            fixed_items=fixed_items,
            escalated_items=escalated_items,
            pod_statuses=pod_statuses,
        )

    def _pod_statuses(self) -> list[PodStatus]:
        """Read the current deployment image and readiness for the report."""
        try:
            image = self.kube.get_deployment_image(self.config.deployment, self.config.container)
            available = self.kube.available_replicas(self.config.deployment)
        except Exception as exc:  # pragma: no cover - defensive; report is best-effort
            logger.warning("Could not read pod status for report: %s", exc)
            return []
        status = "Running" if available >= 1 else "NotReady"
        return [
            PodStatus(deployment=self.config.deployment, status=status, image_tag=image)
        ]

    def _overall_status(
        self,
        initial_failures: list[Failure],
        remaining: list[Failure],
        escalated_outcomes: list[FixOutcome],
    ) -> str:
        """Derive the report's overall status from the run outcome."""
        if not initial_failures:
            return "all_clear"
        if not remaining:
            return "all_clear"
        if len(remaining) >= self.config.systemic_failure_threshold:
            return "critical"
        return "issues_remain"


def _blank_failure() -> Failure:
    """Placeholder failure used when an outcome id has no matching failure."""
    return Failure(
        failure_id="",
        title="(unknown failure)",
        error="",
        category="unknown",
        signal="unknown",
    )
