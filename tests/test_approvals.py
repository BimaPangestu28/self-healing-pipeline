"""Unit tests for the approval-driven remediation service, executors, and cards."""

from __future__ import annotations

import httpx

from src.approvals.cards import build_approval_card, build_healthcheck_card, build_result_card
from src.approvals.executors import AwxExecutor, KubernetesExecutor
from src.approvals.models import ActionSpec, ApprovalStatus
from src.approvals.service import DemoService
from src.self_healing.config import PipelineConfig

CONFIG = PipelineConfig()


class FakeKube:
    """Fake cluster where the deployment is always running and healable by restart."""

    def __init__(self) -> None:
        self.namespace = CONFIG.namespace
        self.restart_calls = 0
        self.applied = False
        self.image = CONFIG.good_image
        self.memory = 88  # starts high; restart heals it

    def apply(self, manifest_path: str) -> None:
        self.applied = True

    def set_deployment_image(self, deployment: str, container: str, image: str) -> None:
        self.image = image

    def available_replicas(self, deployment: str) -> int:
        return 1

    def ready_endpoint_count(self, service: str) -> int:
        return 1

    def pod_memory_percent(self, deployment: str) -> int:
        return self.memory

    def pod_identity(self, deployment: str) -> dict:
        return {"pod": f"{deployment}-abc123", "node": "colima", "pod_ip": "10.42.0.9"}

    def trigger_memory_pressure(self, deployment: str, megabytes: int) -> bool:
        self.memory = 88
        return True

    def restart_rollout(self, deployment: str) -> None:
        self.restart_calls += 1
        self.memory = 6  # new pod starts at baseline

    def wait_rollout(self, deployment: str, timeout: int = 120) -> bool:
        return True


def _service() -> DemoService:
    kube = FakeKube()
    return DemoService(kube=kube, config=CONFIG, executor=KubernetesExecutor(kube, CONFIG))


# --- service flow ---------------------------------------------------------


def test_healthcheck_starts_unhealthy_due_to_memory():
    service = _service()
    report = service.healthcheck()
    assert report.healthy is False
    assert report.memory_percent == 88
    memory = next(s for s in report.services if s.name == "Memory Usage")
    assert memory.ok is False


def test_recommend_action_uses_real_cluster_identity():
    service = _service()
    action = service.recommend_action(service.healthcheck())
    assert action is not None
    assert action.action.startswith("restart_deployment/")
    # Kubernetes executor -> parameters come from the cluster, not hardcoded AWX ids.
    assert action.parameters["namespace"] == CONFIG.namespace
    assert action.parameters["deployment"] == CONFIG.deployment
    assert action.parameters["node"] == "colima"
    assert action.parameters["pod"].startswith(CONFIG.deployment)


def test_approve_executes_and_heals():
    service = _service()
    action = service.recommend_action(service.healthcheck())
    request = service.create_approval(action)

    decided = service.approve(request.request_id)

    assert decided.status is ApprovalStatus.EXECUTED
    assert service.kube.restart_calls == 1  # real remediation invoked
    assert decided.execution is not None and decided.execution.success is True
    assert decided.verify is not None and decided.verify.healthy is True


def test_autonomous_remediate_heals_without_approval():
    service = _service()
    result = service.autonomous_remediate()
    assert result["acted"] is True
    assert service.kube.restart_calls >= 1  # remediation executed
    assert result["request"].status is ApprovalStatus.EXECUTED
    assert result["request"].verify is not None and result["request"].verify.healthy is True


def test_reject_leaves_target_untouched():
    service = _service()
    action = service.recommend_action(service.healthcheck())
    request = service.create_approval(action)

    decided = service.reject(request.request_id)

    assert decided.status is ApprovalStatus.REJECTED
    assert service.kube.restart_calls == 0
    assert service.healthcheck().healthy is False


# --- cards ----------------------------------------------------------------


def test_approval_card_has_execute_actions_with_verbs():
    service = _service()
    request = service.create_approval(service.recommend_action(service.healthcheck()))
    card = build_approval_card(request)

    assert card["actions"][0]["type"] == "Action.Execute"
    verbs = {action["data"]["verb"] for action in card["actions"]}
    assert verbs == {"approve", "reject"}


def test_result_card_reports_success_after_approval():
    service = _service()
    request = service.create_approval(service.recommend_action(service.healthcheck()))
    service.approve(request.request_id)

    card = build_result_card(request)
    texts = [el.get("text", "") for el in card["body"] if el.get("type") == "TextBlock"]
    assert any("Completed Successfully" in t for t in texts)


def test_healthcheck_card_shows_unhealthy_status():
    service = _service()
    card = build_healthcheck_card(service.healthcheck(), analysis="x")
    status_block = card["body"][1]
    assert "Unhealthy" in status_block["text"]
    assert status_block["color"] == "Attention"


# --- executors ------------------------------------------------------------


def _memory_action() -> ActionSpec:
    return ActionSpec(
        action="service_management_outsystem_memory",
        tool="ansible",
        description="Clear Host Full memory Outsystem",
        parameters={"template_id": "9666", "limit_ip": "10.59.129.87"},
    )


def test_kubernetes_executor_restarts_deployment():
    kube = FakeKube()
    result = KubernetesExecutor(kube, CONFIG).execute(_memory_action())
    assert result.success is True
    assert result.tool == "kubernetes"
    assert kube.restart_calls == 1


def test_awx_executor_launches_and_polls_to_success():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/launch/"):
            return httpx.Response(201, json={"id": 42, "status": "pending"})
        if "/jobs/42/" in request.url.path:
            return httpx.Response(200, json={"status": "successful"})
        return httpx.Response(404, json={})

    executor = AwxExecutor(
        CONFIG,
        base_url="https://awx.test",
        token="secret",
        poll_interval=0,
        transport=httpx.MockTransport(handler),
    )
    result = executor.execute(_memory_action())

    assert result.success is True
    assert result.tool == "awx"
    assert result.job_id == "42"


def test_awx_executor_reports_failure_status():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/launch/"):
            return httpx.Response(201, json={"id": 7, "status": "pending"})
        return httpx.Response(200, json={"status": "failed"})

    executor = AwxExecutor(
        CONFIG,
        base_url="https://awx.test",
        poll_interval=0,
        transport=httpx.MockTransport(handler),
    )
    result = executor.execute(_memory_action())
    assert result.success is False
    assert result.job_id == "7"
