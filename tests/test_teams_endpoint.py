"""Tests for the Teams Adaptive Card invoke handler and HMAC verification."""

from __future__ import annotations

import base64
import hashlib
import hmac

from src.approvals.executors import KubernetesExecutor
from src.approvals.service import DemoService
from src.approvals.teams_endpoint import handle_teams_activity, verify_hmac
from src.self_healing.config import PipelineConfig

CONFIG = PipelineConfig()


class FakeKube:
    """Always-running deployment that heals on restart."""

    def __init__(self) -> None:
        self.namespace = CONFIG.namespace
        self.restart_calls = 0
        self.memory = 88

    def apply(self, manifest_path: str) -> None:
        pass

    def set_deployment_image(self, deployment: str, container: str, image: str) -> None:
        pass

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
        self.memory = 6

    def wait_rollout(self, deployment: str, timeout: int = 120) -> bool:
        return True


def _service() -> DemoService:
    kube = FakeKube()
    return DemoService(kube=kube, config=CONFIG, executor=KubernetesExecutor(kube, CONFIG))


def _invoke(verb: str, request_id: str) -> dict:
    return {
        "type": "invoke",
        "name": "adaptiveCard/action",
        "value": {
            "action": {
                "type": "Action.Execute",
                "verb": verb,
                "data": {"verb": verb, "requestId": request_id},
            }
        },
    }


def _card_text(response: dict) -> str:
    body = response["value"]["body"]
    return "\n".join(el.get("text", "") for el in body if el.get("type") == "TextBlock")


def test_invoke_approve_executes_and_refreshes_card():
    service = _service()
    request = service.create_approval(service.recommend_action(service.healthcheck()))

    response = handle_teams_activity(service, _invoke("approve", request.request_id))

    assert response["statusCode"] == 200
    assert response["type"] == "application/vnd.microsoft.card.adaptive"
    assert "Completed Successfully" in _card_text(response)
    assert service.kube.restart_calls == 1


def test_invoke_reject_does_not_touch_cluster():
    service = _service()
    request = service.create_approval(service.recommend_action(service.healthcheck()))

    response = handle_teams_activity(service, _invoke("reject", request.request_id))

    assert "Rejected" in _card_text(response)
    assert service.kube.restart_calls == 0


def test_invoke_unknown_request_returns_message():
    service = _service()
    response = handle_teams_activity(service, _invoke("approve", "AR-does-not-exist"))
    assert "Unknown or expired" in _card_text(response)


def test_non_invoke_activity_is_handled_gracefully():
    service = _service()
    response = handle_teams_activity(service, {"type": "message", "text": "hi"})
    assert response["statusCode"] == 200
    assert "Approve/Reject" in _card_text(response)


def test_verify_hmac_accepts_valid_signature():
    secret = base64.b64encode(b"super-secret-key").decode()
    body = b'{"type":"invoke"}'
    signature = base64.b64encode(
        hmac.new(base64.b64decode(secret), body, hashlib.sha256).digest()
    ).decode()
    assert verify_hmac(secret, body, f"HMAC {signature}") is True


def test_verify_hmac_rejects_bad_signature():
    secret = base64.b64encode(b"super-secret-key").decode()
    assert verify_hmac(secret, b"{}", "HMAC d29yb25n") is False
    assert verify_hmac(secret, b"{}", None) is False
    assert verify_hmac(secret, b"{}", "Bearer token") is False
