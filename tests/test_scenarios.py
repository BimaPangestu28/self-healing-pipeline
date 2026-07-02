"""Unit tests for the demo use-case scenarios (fake cluster)."""

from __future__ import annotations

from src.approvals.scenarios import list_scenarios, run_scenario
from src.self_healing.config import PipelineConfig

CONFIG = PipelineConfig(
    deployment="memory-app", container="app", service="memory-app",
    good_image="self-healing-memory-app:local",
)


class FakeKube:
    """Fake cluster tracking image + replica count."""

    def __init__(self) -> None:
        self.namespace = CONFIG.namespace
        self.image = CONFIG.good_image
        self.replicas = 1

    def set_deployment_image(self, deployment, container, image):
        self.image = image

    def get_deployment_image(self, deployment, container):
        return self.image

    def scale_deployment(self, deployment, replicas):
        self.replicas = replicas

    def desired_replicas(self, deployment):
        return self.replicas

    def available_replicas(self, deployment):
        return self.replicas if self.image == CONFIG.good_image else 0

    def ready_endpoint_count(self, service):
        return self.replicas if self.image == CONFIG.good_image else 0

    def wait_rollout(self, deployment, timeout=120):
        return self.image == CONFIG.good_image and self.replicas >= 1

    def restart_rollout(self, deployment):
        pass

    def pod_memory_percent(self, deployment):
        return 42

    def pod_identity(self, deployment):
        return {"pod": f"{deployment}-abc", "node": "kind", "pod_ip": "10.244.0.5"}


def _overall(card):
    facts = {x["title"]: x["value"] for e in card["body"] if e.get("type") == "FactSet" for x in e["facts"]}
    return facts.get("Overall Status")


def test_list_scenarios_includes_categories():
    ids = {s["id"] for s in list_scenarios()}
    assert {"high_memory", "image_drift", "scaled_to_zero", "capacity_report"} <= ids
    cats = {s["category"] for s in list_scenarios()}
    assert "Remediation" in cats and "Diagnostics" in cats


def test_image_drift_detects_and_resets():
    kube = FakeKube()
    out = run_scenario("image_drift", kube, CONFIG, service=None)
    assert len(out["cards"]) == 2
    assert kube.image == CONFIG.good_image  # reset to known-good
    assert "OK Healthy" in _overall(out["cards"][-1])


def test_scaled_to_zero_scales_back_up():
    kube = FakeKube()
    out = run_scenario("scaled_to_zero", kube, CONFIG, service=None)
    assert kube.replicas == 1  # scaled back up
    assert "OK Healthy" in _overall(out["cards"][-1])


def test_capacity_report_is_read_only():
    kube = FakeKube()
    before_image, before_replicas = kube.image, kube.replicas
    out = run_scenario("capacity_report", kube, CONFIG, service=None)
    assert len(out["cards"]) == 1
    assert kube.image == before_image and kube.replicas == before_replicas  # unchanged


def test_unknown_scenario_is_handled():
    out = run_scenario("nope", FakeKube(), CONFIG, service=None)
    assert out["cards"] == [] and "Unknown" in out["note"]
