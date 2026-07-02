"""FastAPI routes for SRE Agent API."""

import asyncio
import logging
import uuid
from asyncio import Lock
from contextlib import nullcontext

from agent_framework.observability import get_tracer
from fastapi import APIRouter, HTTPException
import httpx

from rag.query import extract_ranked_matches, query_similar_docs

from src.api.models import (
    AlertWebhookRequest,
    AlertWebhookResponse,
    ApprovalRequest,
    ChatRequest,
    ChatResponse,
    HealthResponse,
    ModelConfigResponse,
    UpdateModelRequest,
)

from src.agents.elasticsearch_agent import create_elasticsearch_agent
from src.agents.k8s_monitoring_agent import create_k8s_monitoring_agent
from src.agents.rag_agent import create_rag_agent
from src.agents.router_agent import create_router_agent
from src.agents.synthesizer_agent import create_synthesizer_agent
from src.clients.azure_openai import reset_chat_client
from src.config.chat_ui import get_agent_intro_message, is_new_session_command, with_new_session_hint
from src.config.model_registry import refresh_runtime_model_from_registry
from src.config.observability import setup_langfuse_otel
from src.config.settings import (
    get_active_deployment,
    get_available_runtime_models,
    get_settings,
    is_supported_runtime_model,
    set_active_deployment,
)
from src.notifications.adaptive_cards import build_alert_card
from src.notifications.models import PipelineReport, PipelineReportResponse
from src.notifications.teams import send_adaptive_card, send_pipeline_report
from src.orchestration.dispatcher import RouterDispatcher

# Router for API endpoints
logger = logging.getLogger(__name__)
router = APIRouter()

# Initialize Langfuse OTEL and tracer
_otel_enabled = setup_langfuse_otel()
_tracer = get_tracer() if _otel_enabled else None

# In-memory storage for active thread IDs.
_threads: dict[str, bool] = {}
_dispatcher: RouterDispatcher | None = None
_agent_refresh_lock = Lock()

WEBHOOK_SEND_TIMEOUT_SECONDS = 10.0
KIBANA_ALERT_TRIGGER = "kibana alert"
RAG_TOP_K = 1


async def _get_dispatcher() -> RouterDispatcher:
    """Lazy-initialize router-tier dispatcher."""
    global _dispatcher
    if _dispatcher is None:
        # Ensure runtime model is refreshed before agents initialize.
        get_active_deployment()
        router_agent = await create_router_agent()
        k8s_agent = await create_k8s_monitoring_agent()
        elk_agent = await create_elasticsearch_agent()
        rag_agent = await create_rag_agent()
        synthesizer = await create_synthesizer_agent()
        _dispatcher = RouterDispatcher(
            router=router_agent,
            specialists={
                "kubernetes_monitoring": k8s_agent,
                "elasticsearch": elk_agent,
                "rag": rag_agent,
            },
            synthesizer=synthesizer,
        )
    return _dispatcher


async def _refresh_model_and_agents() -> None:
    """Refresh model from registry and rebuild agents if it changed."""
    global _dispatcher, _threads
    async with _agent_refresh_lock:
        updated = await refresh_runtime_model_from_registry()
        if updated:
            _dispatcher = None
            _threads.clear()
            await _get_dispatcher()


def _format_alert_prompt(payload: AlertWebhookRequest) -> str:
    details = payload.model_dump(exclude_none=True)
    lines = ["[ALERT] Incoming alert webhook"]

    rule_name = payload.rule_name or details.get("rule_name")
    if rule_name:
        lines.append(f"Rule: {rule_name}")
    if payload.severity:
        lines.append(f"Severity: {payload.severity}")
    if payload.context_message:
        lines.append(f"Message: {payload.context_message}")

    k8s_context = []
    if payload.namespace:
        k8s_context.append(f"Namespace={payload.namespace}")
    if payload.pod_name:
        k8s_context.append(f"Pod={payload.pod_name}")
    if payload.container_name:
        k8s_context.append(f"Container={payload.container_name}")
    if payload.node_name:
        k8s_context.append(f"Node={payload.node_name}")
    if k8s_context:
        lines.append("Kubernetes: " + ", ".join(k8s_context))

    if payload.app_name:
        lines.append(f"App: {payload.app_name}")
    if payload.value:
        lines.append(f"Value: {payload.value}")
    if payload.date:
        lines.append(f"Time: {payload.date}")
    if payload.link:
        lines.append(f"Link: {payload.link}")

    return "\n".join(lines)


def _extract_rag_matches(result: dict, k: int) -> list[dict]:
    matches: list[dict] = []
    for item in extract_ranked_matches(result, k=k):
        matches.append(
            {
                "id": item.get("id"),
                "app": item.get("app"),
                "error": item.get("error"),
                "category": item.get("category"),
                "explanation": item.get("explanation"),
                "severity": item.get("severity"),
                "similarity": item.get("similarity"),
            }
        )
    return matches


async def _fetch_rag_matches(text: str | None, k: int = RAG_TOP_K) -> list[dict]:
    if not text or not text.strip():
        return []

    def _query() -> dict:
        return query_similar_docs(
            text=text,
            k=k,
            key="error",
            select="id, app, error, severity, category, explanation",
        )

    try:
        result = await asyncio.to_thread(_query)
    except Exception as exc:
        logger.warning("RAG lookup failed: %s", exc)
        return []

    return _extract_rag_matches(result, k)


def _format_rag_context(matches: list[dict]) -> str:
    if not matches:
        return "RAG Knowledge: none"

    lines = ["RAG Knowledge (top matches):"]
    for match in matches:
        lines.append(
            " - id={id}, app={app}, category={category}, severity={severity}, "
            "error={error}, explanation={explanation}".format(
                id=match.get("id"),
                app=match.get("app"),
                category=match.get("category"),
                severity=match.get("severity"),
                error=match.get("error"),
                explanation=match.get("explanation"),
            )
        )
    return "\n".join(lines)


def _format_rag_references(matches: list[dict]) -> str:
    if not matches:
        return "RAG References:\n- No similar knowledge found."

    lines = ["RAG References:"]
    for match in matches[:RAG_TOP_K]:
        lines.append(
            "- {id}: app={app}, category={category}, error={error}, "
            "explanation={explanation} (severity {severity})".format(
                id=match.get("id"),
                app=match.get("app"),
                category=match.get("category"),
                error=match.get("error"),
                explanation=match.get("explanation"),
                severity=match.get("severity"),
            )
        )
    return "\n".join(lines)


def _append_rag_references(analysis: str, matches: list[dict]) -> str:
    references = _format_rag_references(matches)
    if not analysis:
        return references
    return f"{analysis.rstrip()}\n\n{references}"



async def _broadcast_to_webhook(
    *, message: str, thread_id: str, original_message: str
) -> None:
    settings = get_settings()
    base_url = settings.non_kube_tools_base_url.rstrip("/")
    url = f"{base_url}/webhook/broadcast"
    # Send only fields accepted by the webhook service.
    safe_message = message or ""
    if len(safe_message) > 4096:
        safe_message = safe_message[:4096]
    payload = {
        "message": safe_message,
        "parse_markdown": False,
    }
    headers = {}
    if settings.webhook_api_key:
        headers["x-api-key"] = settings.webhook_api_key
    headers["accept"] = "application/json"
    logger.info("Webhook broadcast payload: %s", payload)
    async with httpx.AsyncClient(timeout=WEBHOOK_SEND_TIMEOUT_SECONDS) as client:
        try:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response else "unknown"
            body = exc.response.text if exc.response else ""
            logger.warning(
                "Webhook broadcast failed: status=%s body=%s url=%s",
                status,
                body[:2000],
                url,
            )
        except httpx.HTTPError as exc:
            logger.warning("Webhook broadcast error: %s url=%s", exc, url)


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(
        status="healthy" if _dispatcher is not None else "unhealthy",
        version="1.0.0",
        agents_loaded=_dispatcher is not None,
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Handle chat messages and coordinate with SRE router/specialist agents.
    """
    global _threads

    await _refresh_model_and_agents()
    dispatcher = await _get_dispatcher()

    if is_new_session_command(request.message):
        if request.thread_id and request.thread_id in _threads:
            _threads.pop(request.thread_id)
            dispatcher.reset_thread(request.thread_id)

        thread_id = str(uuid.uuid4())
        _threads[thread_id] = True
        return ChatResponse(
            message=with_new_session_hint(get_agent_intro_message()),
            thread_id=thread_id,
            pending_approvals=None,
        )

    # Get or create thread for conversation continuity.
    thread_id = request.thread_id
    if not thread_id or thread_id not in _threads:
        thread_id = str(uuid.uuid4())
        _threads[thread_id] = True

    try:
        image_notice = (
            "Note: image input is not supported here, so the image was ignored.\n\n"
            if request.images
            else ""
        )
        # Create span context for tracing
        span_context = _tracer.start_as_current_span("sre_agent.chat") \
            if _tracer else nullcontext()

        with span_context as root_span:
            # Set input attribute on span (Langfuse expects "input.value")
            if _tracer and root_span:
                root_span.set_attribute("input.value", request.message)
                root_span.set_attribute("langfuse.session.id", thread_id)
                if request.user_id:
                    root_span.set_attribute("langfuse.user.id", request.user_id)

            rag_matches: list[dict] = []
            message_for_dispatch = request.message
            if KIBANA_ALERT_TRIGGER in request.message.lower():
                asyncio.create_task(
                    _broadcast_to_webhook(
                        message=request.message,
                        thread_id=thread_id,
                        original_message=request.message,
                    )
                )
                rag_matches = await _fetch_rag_matches(request.message)
                if rag_matches:
                    message_for_dispatch = (
                        f"{request.message}\n\n{_format_rag_context(rag_matches)}"
                    )

            dispatch_result = await dispatcher.dispatch(message_for_dispatch, thread_id)
            pending_approvals = dispatch_result.pending_approvals
            response_text = with_new_session_hint(f"{image_notice}{dispatch_result.message}")
            if rag_matches:
                response_text = _append_rag_references(response_text, rag_matches)

            # Set output attribute on span (Langfuse expects "output.value")
            if _tracer and root_span:
                root_span.set_attribute("output.value", response_text)

            if KIBANA_ALERT_TRIGGER in request.message.lower():
                await _broadcast_to_webhook(
                    message=response_text,
                    thread_id=thread_id,
                    original_message=request.message,
                )

        return ChatResponse(
            message=response_text,
            thread_id=thread_id,
            pending_approvals=pending_approvals,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)}")


@router.post("/webhook/alerts", response_model=AlertWebhookResponse)
async def receive_alert(payload: AlertWebhookRequest) -> AlertWebhookResponse:
    """Receive alert webhook and analyze with SRE agents."""
    await _refresh_model_and_agents()
    dispatcher = await _get_dispatcher()

    rag_matches: list[dict] = []
    try:
        thread_id = str(uuid.uuid4())
        prompt = _format_alert_prompt(payload)
        rag_input = payload.context_message or payload.rule_name or payload.app_name or prompt
        rag_matches = await _fetch_rag_matches(rag_input)
        if rag_matches:
            prompt = f"{prompt}\n\n{_format_rag_context(rag_matches)}"
        dispatch_result = await dispatcher.dispatch(prompt, thread_id)
        analysis = dispatch_result.message
        if rag_matches:
            analysis = _append_rag_references(analysis, rag_matches)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error analyzing alert: {exc}")

    # Deliver the analysis to Microsoft Teams as an Adaptive Card (best-effort).
    alert_title = payload.rule_name or payload.app_name or "SRE Alert"
    alert_card = build_alert_card(
        title=alert_title,
        analysis=analysis,
        severity=payload.severity,
        source_link=payload.link,
    )
    await send_adaptive_card(alert_card)

    return AlertWebhookResponse(
        status="ok",
        analysis=analysis,
    )


@router.post("/pipeline/report", response_model=PipelineReportResponse)
async def deliver_pipeline_report(report: PipelineReport) -> PipelineReportResponse:
    """Render a self-healing pipeline run summary as an Adaptive Card and post it to Teams.

    This is the Phase 7 delivery hook: an external orchestrator (cron/agent) POSTs
    the structured run summary and this service renders and delivers the card.
    """
    delivered = await send_pipeline_report(report)
    detail = (
        "Adaptive Card delivered to Teams."
        if delivered
        else "Teams webhook not configured or delivery failed; see server logs."
    )
    return PipelineReportResponse(status="ok", delivered=delivered, detail=detail)


@router.get("/model", response_model=ModelConfigResponse)
@router.get("/mode", response_model=ModelConfigResponse)
async def get_model_config() -> ModelConfigResponse:
    """Get current active deployment and .env default deployment."""
    settings = get_settings()
    return ModelConfigResponse(
        active_model=get_active_deployment(),
        default_model=settings.azure_openai_deployment,
        available_models=get_available_runtime_models(),
    )


@router.put("/model", response_model=ModelConfigResponse)
@router.put("/mode", response_model=ModelConfigResponse)
async def update_model_config(request: UpdateModelRequest) -> ModelConfigResponse:
    """Update active deployment at runtime and reinitialize agents/client."""
    global _dispatcher, _threads

    model_name = request.model_name.strip()
    if not model_name:
        raise HTTPException(status_code=400, detail="model_name cannot be empty")
    if not is_supported_runtime_model(model_name):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported model_name '{model_name}'. "
                f"Supported models: {', '.join(get_available_runtime_models())}"
            ),
        )

    async with _agent_refresh_lock:
        set_active_deployment(model_name)
        reset_chat_client()
        _dispatcher = None
        await _get_dispatcher()
        _threads.clear()

    settings = get_settings()
    return ModelConfigResponse(
        active_model=get_active_deployment(),
        default_model=settings.azure_openai_deployment,
        available_models=get_available_runtime_models(),
    )


@router.post("/approve", response_model=ChatResponse)
async def approve_operation(request: ApprovalRequest) -> ChatResponse:
    """No-op approval endpoint for compatibility with earlier API clients."""
    if request.thread_id and request.thread_id not in _threads:
        raise HTTPException(status_code=404, detail="Thread not found")

    return ChatResponse(
        message="No pending approvals in router-tier architecture.",
        thread_id=request.thread_id,
        pending_approvals=None,
    )


@router.delete("/threads/{thread_id}")
async def delete_thread(thread_id: str) -> dict:
    """Delete a conversation thread."""
    global _threads, _dispatcher

    if thread_id in _threads:
        _threads.pop(thread_id)
        if _dispatcher:
            _dispatcher.reset_thread(thread_id)
        return {"status": "deleted", "thread_id": thread_id}

    raise HTTPException(status_code=404, detail="Thread not found")


@router.get("/threads")
async def list_threads() -> dict:
    """List all active conversation threads."""
    global _threads

    return {
        "threads": list(_threads.keys()),
        "count": len(_threads),
    }
