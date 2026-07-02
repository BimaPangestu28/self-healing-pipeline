"""Data models for self-healing pipeline reports delivered to Microsoft Teams."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Overall run outcome, mirroring the Phase 7 report status in the pipeline spec.
PipelineStatus = Literal["all_clear", "issues_remain", "critical"]


class FixedItem(BaseModel):
    """A single failure that the L2 agent auto-fixed during the run."""

    failure_id: str = Field(..., description="Failure identifier, e.g. 'F001'")
    description: str = Field(..., description="Short human-readable description of the fix")
    runbook_id: str | None = Field(None, description="Runbook entry that guided the fix")


class EscalatedItem(BaseModel):
    """A single failure escalated to a human because it could not be auto-fixed."""

    failure_id: str = Field(..., description="Failure identifier, e.g. 'F005'")
    description: str = Field(..., description="Short human-readable description of the failure")
    reason: str = Field(..., description="Why the failure was escalated instead of fixed")


class PodStatus(BaseModel):
    """Runtime status of a Kubernetes deployment reported in the summary."""

    deployment: str = Field(..., description="Deployment name, e.g. 'enterprise-staging'")
    status: str = Field(..., description="Pod status, e.g. 'Running'")
    image_tag: str | None = Field(None, description="Currently deployed image tag")


class PipelineReport(BaseModel):
    """Structured self-healing pipeline run summary rendered into an Adaptive Card."""

    run_date: str = Field(..., description="Human-readable run date, e.g. '2026-07-02'")
    status: PipelineStatus = Field("all_clear", description="Overall run outcome")

    # Phase 1 — L1 test execution results.
    l1_passed: int = Field(0, ge=0)
    l1_failed: int = Field(0, ge=0)
    l1_skipped: int = Field(0, ge=0)
    l1_total: int = Field(0, ge=0)

    # Phase 2 — runbook classification counts.
    auto_fixable: int = Field(0, ge=0)
    escalated_count: int = Field(0, ge=0)
    test_issues: int = Field(0, ge=0)

    # Phase 3 — L2 fix outcomes.
    l2_fixed: int = Field(0, ge=0)
    l2_escalated: int = Field(0, ge=0)
    l2_test_issues: int = Field(0, ge=0)

    # Phase 4-6 — deploy, validation, merge request.
    staging_deployed: bool = Field(False, description="Whether L2 fixes were pushed to staging")
    validation_passing: int = Field(0, ge=0, description="Previously-failed tests now passing")
    validation_target: int = Field(0, ge=0, description="Total previously-failed tests re-run")
    merge_request_created: bool = Field(False, description="Whether a staging->main MR was opened")
    merge_request_url: str | None = Field(None, description="Link to the created merge request")
    report_url: str | None = Field(None, description="Link to the full L2 fix report")

    # Detail sections.
    fixed_items: list[FixedItem] = Field(default_factory=list)
    escalated_items: list[EscalatedItem] = Field(default_factory=list)
    pod_statuses: list[PodStatus] = Field(default_factory=list)


class PipelineReportResponse(BaseModel):
    """Response returned after attempting to deliver a pipeline report to Teams."""

    status: str = Field(..., description="Processing status, e.g. 'ok'")
    delivered: bool = Field(..., description="Whether the Adaptive Card was delivered to Teams")
    detail: str | None = Field(None, description="Optional human-readable delivery detail")
