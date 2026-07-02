"""Self-healing pipeline that detects, classifies, and auto-fixes Kubernetes workload regressions.

Adapted from the OpenClaw "Self-Healing Pipeline" spec to run against a local
Kubernetes cluster and report results to Microsoft Teams as Adaptive Cards.

Phases:
    0. Drift check      — compare running image against known-good tag pattern
    1. L1 test          — probe deployment readiness / service endpoints
    2. Classify         — match failures to the coverage matrix (runbook lookup)
    3. L2 fix           — apply the runbook remediation (e.g. reset image)
    5. Validation       — re-run L1 checks to confirm the fix
    7. Report           — render an Adaptive Card and deliver it to Teams
"""

from src.self_healing.config import PipelineConfig
from src.self_healing.models import (
    Classification,
    Failure,
    FixOutcome,
    FixTier,
    Runbook,
)
from src.self_healing.orchestrator import SelfHealingPipeline

__all__ = [
    "PipelineConfig",
    "Classification",
    "Failure",
    "FixOutcome",
    "FixTier",
    "Runbook",
    "SelfHealingPipeline",
]
