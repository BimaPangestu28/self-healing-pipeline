"""FastAPI server for the approval-driven self-healing demo.

Reproduces the AION flow end-to-end against a real local cluster:
healthcheck (unhealthy) -> analysis/recommendation -> interactive approval card ->
approve -> real rollout restart -> verify -> completion card.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from fastapi import Body, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from src.approvals.agent import ChatAgent
from src.approvals.analysis import build_analysis
from src.approvals.bot_auth import bearer_token, bot_app_id, verify_bot_framework_jwt
from src.approvals.cards import build_approval_card, build_healthcheck_card, build_result_card
from src.approvals.models import HealthReport
from src.approvals.service import DemoService
from src.approvals.teams_endpoint import handle_teams_activity, verify_hmac
from src.self_healing.config import PipelineConfig
from src.self_healing.kube import KubeClient

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent / "static"


_DEMO_MANIFEST = str(Path(__file__).resolve().parents[1] / "deploy" / "memory-app.yaml")


def _build_service() -> DemoService:
    """Construct the demo service bound to the memory-app target on the cluster."""
    config = PipelineConfig(
        deployment="memory-app",
        container="app",
        service="memory-app",
        good_image="self-healing-memory-app:local",
        broken_image="self-healing-memory-app:local",
        manifest_path=_DEMO_MANIFEST,
    )
    kube = KubeClient(namespace=config.namespace)
    return DemoService(kube=kube, config=config)


service = _build_service()
agent = ChatAgent(service)
app = FastAPI(title="Self-Healing Approval Demo")


def _analysis_text(report: HealthReport) -> str:
    """Root-cause + recommendation narrative (LLM when configured, else templated)."""
    return build_analysis(report)


def _healthcheck_response(report: HealthReport) -> dict:
    """Shape a healthcheck report into the API response envelope."""
    return {
        "healthy": report.healthy,
        "memory_percent": report.memory_percent,
        "card": build_healthcheck_card(report, _analysis_text(report)),
    }


@app.get("/")
def index() -> FileResponse:
    """Serve the demo web UI."""
    return FileResponse(_STATIC_DIR / "index.html")


@app.post("/api/demo/reset")
def reset() -> dict:
    """Redeploy the sample app healthy and seed the simulated high-memory fault."""
    return _healthcheck_response(service.reset_target())


@app.post("/api/demo/healthcheck")
def healthcheck() -> dict:
    """Run a healthcheck against the current target state."""
    return _healthcheck_response(service.healthcheck())


@app.post("/api/demo/autonomous")
def autonomous() -> dict:
    """AIOps mode: create an incident, then auto-remediate with NO human approval."""
    service.reset_target()
    result = service.autonomous_remediate()
    before = result["before"]
    cards = [build_healthcheck_card(before, _analysis_text(before))]
    if not result["acted"]:
        return {"acted": False, "cards": cards, "note": "Target already healthy — no action taken."}
    cards.append(build_result_card(result["request"]))
    return {
        "acted": True,
        "cards": cards,
        "note": "Autonomous remediation: runbook tier autoFixable → executed without approval, then verified.",
    }


@app.post("/api/demo/request-approval")
def request_approval() -> dict:
    """Recommend a remediation for the current (unhealthy) state and open an approval."""
    report = service.healthcheck()
    action = service.recommend_action(report)
    if action is None:
        return {"pending": False, "message": "Target already healthy; no action needed."}
    request = service.create_approval(action)
    return {"pending": True, "request_id": request.request_id, "card": build_approval_card(request)}


@app.post("/api/demo/approve")
def approve(payload: dict = Body(default={})) -> JSONResponse:
    """Approve a request: execute the real remediation and return the result card."""
    request_id = payload.get("requestId") or payload.get("request_id")
    request = service.get(request_id) if request_id else None
    if request is None:
        return JSONResponse({"error": "unknown approval request"}, status_code=404)
    request = service.approve(request_id)
    return JSONResponse({"status": request.status.value, "card": build_result_card(request)})


@app.post("/api/demo/reject")
def reject(payload: dict = Body(default={})) -> JSONResponse:
    """Reject a request without touching the cluster."""
    request_id = payload.get("requestId") or payload.get("request_id")
    request = service.get(request_id) if request_id else None
    if request is None:
        return JSONResponse({"error": "unknown approval request"}, status_code=404)
    request = service.reject(request_id)
    return JSONResponse({"status": request.status.value, "card": build_result_card(request)})


@app.post("/api/demo/chat")
def chat(payload: dict = Body(default={})) -> JSONResponse:
    """Conversational endpoint: an LLM agent that can healthcheck + propose remediation."""
    session_id = payload.get("session_id") or "default"
    message = (payload.get("message") or "").strip()
    if not message:
        return JSONResponse({"reply": "Please type a message.", "cards": [], "llm": False})
    return JSONResponse(agent.handle(session_id, message))


@app.post("/api/teams/messages")
async def teams_messages(request: Request) -> JSONResponse:
    """Bot Framework messaging endpoint for Teams Adaptive Card actions.

    Point an Azure Bot (or a Power Automate flow) at this URL. Approve/Reject button
    clicks arrive as an ``adaptiveCard/action`` invoke; the response is a refreshed
    Adaptive Card that Teams renders in place.

    Inbound auth (first configured mode wins):
    - ``MICROSOFT_APP_ID`` set -> require a valid Bot Framework JWT (Azure Bot).
    - ``TEAMS_OUTGOING_WEBHOOK_SECRET`` set -> verify the HMAC signature.
    - neither -> open (development only).
    """
    body = await request.body()

    app_id = bot_app_id()
    secret = os.getenv("TEAMS_OUTGOING_WEBHOOK_SECRET", "").strip()
    if app_id:
        token = bearer_token(request.headers.get("authorization"))
        if not token or not verify_bot_framework_jwt(token, app_id):
            return JSONResponse({"error": "invalid or missing Bot Framework token"}, status_code=401)
    elif secret and not verify_hmac(secret, body, request.headers.get("authorization")):
        return JSONResponse({"error": "invalid HMAC signature"}, status_code=401)

    try:
        activity = json.loads(body or b"{}")
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)

    return JSONResponse(handle_teams_activity(service, activity))
