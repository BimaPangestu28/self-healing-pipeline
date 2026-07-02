"""Domain models for the self-healing pipeline (failures, classification, fixes)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FixTier(str, Enum):
    """Confidence tier assigned by the coverage matrix, mirroring the pipeline spec."""

    AUTO_FIXABLE = "autoFixable"
    GUIDED = "guidedInvestigate"
    BRIEF = "briefInvestigate"
    ESCALATE = "escalate"
    TEST_ISSUE = "testIssues"


@dataclass(frozen=True)
class Failure:
    """A single regression detected by the L1 test phase."""

    failure_id: str
    title: str
    error: str
    category: str
    signal: str
    deployment: str | None = None
    namespace: str | None = None
    container: str | None = None
    image: str | None = None


@dataclass(frozen=True)
class Runbook:
    """A coverage-matrix entry mapping a failure signal to a remediation."""

    runbook_id: str
    tier: FixTier
    action: str
    category: str
    max_attempts: int
    fix: str | None = None  # machine action key, e.g. "reset_image"; None => no auto-fix


@dataclass(frozen=True)
class Classification:
    """The result of matching a failure to the coverage matrix."""

    failure: Failure
    runbook: Runbook

    @property
    def tier(self) -> FixTier:
        """Confidence tier of the matched runbook."""
        return self.runbook.tier

    @property
    def is_auto_fixable(self) -> bool:
        """True when the pipeline may attempt an automated fix."""
        return self.runbook.fix is not None and self.tier in {
            FixTier.AUTO_FIXABLE,
            FixTier.GUIDED,
            FixTier.BRIEF,
            FixTier.TEST_ISSUE,
        }


@dataclass(frozen=True)
class FixOutcome:
    """The result of attempting to remediate a single failure."""

    failure_id: str
    fixed: bool
    escalated: bool
    detail: str
    runbook_id: str | None = None
    reason: str | None = None  # populated when escalated
