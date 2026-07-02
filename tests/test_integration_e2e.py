"""End-to-end integration tests against the REAL demo app and a REAL cluster.

Unlike the unit tests (which use an in-memory FakeKube), these drive the actual
FastAPI application (``demo.app:app``) via Starlette's TestClient, exercising the
real ``DemoService`` -> ``KubeClient`` -> ``kubectl`` -> cluster path. Approving a
request performs a real ``kubectl rollout restart`` on the sample deployment.

The whole module is skipped when no Kubernetes cluster is reachable (e.g. in CI),
so it only runs where a local cluster (colima/k3s, minikube, kind, …) is available.
"""

from __future__ import annotations

import shutil

import pytest

from src.self_healing.kube import KubeClient


def _cluster_available() -> bool:
    """True when kubectl exists and the API server is reachable."""
    if shutil.which("kubectl") is None:
        return False
    try:
        return KubeClient(namespace="self-healing").cluster_reachable()
    except Exception:
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _cluster_available(), reason="no reachable Kubernetes cluster"),
]


def _card_text(card: dict) -> str:
    return "\n".join(el.get("text", "") for el in card["body"] if el.get("type") == "TextBlock")


def _card_facts(card: dict) -> dict[str, str]:
    return {
        fact["title"]: fact["value"]
        for element in card["body"]
        if element.get("type") == "FactSet"
        for fact in element["facts"]
    }


@pytest.fixture()
def client():
    """A TestClient bound to the real demo application."""
    from fastapi.testclient import TestClient

    from demo.app import app

    with TestClient(app) as test_client:
        yield test_client


def test_full_approval_flow_heals_real_cluster(client):
    """Alert (unhealthy) -> approval -> approve -> real remediation -> healthy."""
    # ① Alert: the target starts unhealthy (simulated memory 85%).
    reset = client.post("/api/demo/reset")
    assert reset.status_code == 200
    assert reset.json()["healthy"] is False
    assert reset.json()["memory_percent"] == 85

    # ② Approval: an action is recommended and a request opened.
    approval = client.post("/api/demo/request-approval").json()
    assert approval["pending"] is True
    request_id = approval["request_id"]

    # ③ Approve: executes a real rollout restart on the cluster and verifies.
    result = client.post("/api/demo/approve", json={"requestId": request_id}).json()
    assert result["status"] == "executed"
    assert "Completed Successfully" in _card_text(result["card"])
    assert _card_facts(result["card"])["Overall Status"] == "✅ OK Healthy"

    # ④ Verify: a fresh healthcheck reports healthy after the fix.
    healthcheck = client.post("/api/demo/healthcheck").json()
    assert healthcheck["healthy"] is True
    assert healthcheck["memory_percent"] == 32


def test_full_teams_invoke_flow_heals_real_cluster(client):
    """The same flow driven through the Teams adaptiveCard/action invoke endpoint."""
    client.post("/api/demo/reset")
    request_id = client.post("/api/demo/request-approval").json()["request_id"]

    invoke = {
        "type": "invoke",
        "name": "adaptiveCard/action",
        "value": {
            "action": {
                "type": "Action.Execute",
                "verb": "approve",
                "data": {"verb": "approve", "requestId": request_id},
            }
        },
    }
    response = client.post("/api/teams/messages", json=invoke).json()

    assert response["statusCode"] == 200
    assert response["type"] == "application/vnd.microsoft.card.adaptive"
    assert "Completed Successfully" in _card_text(response["value"])
    assert client.post("/api/demo/healthcheck").json()["healthy"] is True


def test_reject_flow_leaves_cluster_unhealthy(client):
    """Rejecting an approval performs no remediation; the target stays unhealthy."""
    client.post("/api/demo/reset")
    request_id = client.post("/api/demo/request-approval").json()["request_id"]

    result = client.post("/api/demo/reject", json={"requestId": request_id}).json()
    assert result["status"] == "rejected"
    assert "Rejected" in _card_text(result["card"])
    assert client.post("/api/demo/healthcheck").json()["healthy"] is False
