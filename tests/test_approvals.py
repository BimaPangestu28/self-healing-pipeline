"""Unit tests for the approval-driven remediation service and cards."""

from __future__ import annotations

from src.approvals.cards import build_approval_card, build_healthcheck_card, build_result_card
from src.approvals.service import ApprovalStatus, DemoService
from src.self_healing.config import PipelineConfig

CONFIG = PipelineConfig()


class FakeKube:
    """Fake cluster where the deployment is always running and healable by restart."""

    def __init__(self) -> None:
        self.namespace = CONFIG.namespace
        self.restart_calls = 0
        self.applied = False
        self.image = CONFIG.good_image

    def apply(self, manifest_path: str) -> None:
        self.applied = True

    def set_deployment_image(self, deployment: str, container: str, image: str) -> None:
        self.image = image

    def available_replicas(self, deployment: str) -> int:
        return 1

    def ready_endpoint_count(self, service: str) -> int:
        return 1

    def restart_rollout(self, deployment: str) -> None:
        self.restart_calls += 1

    def wait_rollout(self, deployment: str, timeout: int = 120) -> bool:
        return True


def _service() -> DemoService:
    return DemoService(kube=FakeKube(), config=CONFIG)


def test_healthcheck_starts_unhealthy_due_to_memory():
    service = _service()
    report = service.healthcheck()
    assert report.healthy is False
    assert report.memory_percent == 85
    memory = next(s for s in report.services if s.name == "Memory Usage")
    assert memory.ok is False


def test_recommend_action_for_high_memory():
    service = _service()
    action = service.recommend_action(service.healthcheck())
    assert action is not None
    assert action.action == "service_management_outsystem_memory"
    assert action.tool == "ansible"


def test_approve_executes_and_heals():
    service = _service()
    action = service.recommend_action(service.healthcheck())
    request = service.create_approval(action)

    decided = service.approve(request.request_id)

    assert decided.status is ApprovalStatus.EXECUTED
    assert service.kube.restart_calls == 1  # real remediation invoked
    assert decided.execution["success"] is True
    assert decided.verify.healthy is True  # verification healthcheck now healthy


def test_reject_leaves_target_untouched():
    service = _service()
    action = service.recommend_action(service.healthcheck())
    request = service.create_approval(action)

    decided = service.reject(request.request_id)

    assert decided.status is ApprovalStatus.REJECTED
    assert service.kube.restart_calls == 0
    assert service.healthcheck().healthy is False


def test_approval_card_has_approve_and_reject_actions():
    service = _service()
    request = service.create_approval(service.recommend_action(service.healthcheck()))
    card = build_approval_card(request)

    verbs = {action["data"]["verb"] for action in card["actions"]}
    assert verbs == {"approve", "reject"}
    assert card["actions"][0]["type"] == "Action.Submit"


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
