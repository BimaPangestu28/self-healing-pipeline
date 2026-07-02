"""Unit tests for the self-healing pipeline using an in-memory fake cluster."""

from __future__ import annotations

from src.self_healing.config import PipelineConfig
from src.self_healing.kube import PodInfo
from src.self_healing.l1_tests import run_l1_tests
from src.self_healing.models import Failure, FixTier
from src.self_healing.orchestrator import SelfHealingPipeline
from src.self_healing.runbook import classify

CONFIG = PipelineConfig()


class FakeKube:
    """Stateful in-memory stand-in for KubeClient.

    A workload is 'healthy' when its image tag does not contain 'broken'. Setting a
    good image makes subsequent readiness checks pass, so a pipeline run can heal it.
    """

    def __init__(self, image: str) -> None:
        self.namespace = CONFIG.namespace
        self.image = image
        self.set_calls: list[str] = []
        self.restart_calls: int = 0

    def _healthy(self) -> bool:
        return "broken" not in self.image

    def get_deployment_image(self, deployment: str, container: str) -> str:
        return self.image

    def available_replicas(self, deployment: str) -> int:
        return 1 if self._healthy() else 0

    def ready_endpoint_count(self, service: str) -> int:
        return 1 if self._healthy() else 0

    def pod_infos(self, selector: str) -> list[PodInfo]:
        if self._healthy():
            return [PodInfo("sample-app-abc", "Running", True, None)]
        return [PodInfo("sample-app-abc", "Pending", False, "ImagePullBackOff")]

    def set_deployment_image(self, deployment: str, container: str, image: str) -> None:
        self.image = image
        self.set_calls.append(image)

    def restart_rollout(self, deployment: str) -> None:
        self.restart_calls += 1

    def wait_rollout(self, deployment: str, timeout: int = 120) -> bool:
        return self._healthy()


# --- classification -------------------------------------------------------


def test_classify_image_pull_error_is_auto_fixable():
    failure = Failure(
        failure_id="F001",
        title="broken",
        error="",
        category="infra",
        signal="image_pull_error",
    )
    classification = classify(failure)
    assert classification.tier is FixTier.AUTO_FIXABLE
    assert classification.runbook.fix == "reset_image"
    assert classification.is_auto_fixable


def test_classify_unknown_signal_escalates():
    failure = Failure(
        failure_id="F999",
        title="mystery",
        error="",
        category="unknown",
        signal="totally_unknown_signal",
    )
    classification = classify(failure)
    assert classification.tier is FixTier.ESCALATE
    assert not classification.is_auto_fixable


# --- L1 detection ---------------------------------------------------------


def test_l1_detects_broken_deployment():
    kube = FakeKube(image=CONFIG.broken_image)
    failures = run_l1_tests(kube, CONFIG)
    assert len(failures) == 1
    assert failures[0].signal == "image_pull_error"


def test_l1_healthy_deployment_has_no_failures():
    kube = FakeKube(image=CONFIG.good_image)
    assert run_l1_tests(kube, CONFIG) == []


def test_l1_detects_image_drift_when_running_but_off_pattern():
    kube = FakeKube(image="traefik/whoami:latest")  # healthy but tag off-pattern
    failures = run_l1_tests(kube, CONFIG)
    assert len(failures) == 1
    assert failures[0].signal == "image_drift"


# --- full pipeline --------------------------------------------------------


def test_pipeline_heals_broken_deployment():
    kube = FakeKube(image=CONFIG.broken_image)
    pipeline = SelfHealingPipeline(kube=kube, config=CONFIG)

    result = pipeline.run(run_date="2026-07-02")

    assert kube.image == CONFIG.good_image  # image was reset to known-good
    assert result.report.status == "all_clear"
    assert result.report.l2_fixed == 1
    assert result.report.l2_escalated == 0
    assert not result.remaining_failures
    assert [item.failure_id for item in result.report.fixed_items] == ["F001"]


def test_pipeline_reports_all_clear_when_already_healthy():
    kube = FakeKube(image=CONFIG.good_image)
    pipeline = SelfHealingPipeline(kube=kube, config=CONFIG)

    result = pipeline.run(run_date="2026-07-02")

    assert result.report.status == "all_clear"
    assert result.report.l1_failed == 0
    assert result.report.l2_fixed == 0
    assert kube.set_calls == []  # nothing mutated
