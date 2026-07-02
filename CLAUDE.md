# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Multi-agent SRE ("Site Reliability Engineer") assistant built on the **Microsoft Agent Framework** (`agent-framework`) and **Azure OpenAI** (Responses API). It acts as a read-only L1/L2 SRE that diagnoses Kubernetes deployments and analyzes Elasticsearch logs. Two entry points share the same agent stack: a FastAPI server (`main.py`) and a terminal chat REPL (`chat.py`).

## Commands

Uses **uv** (Python 3.13+). `--prerelease=allow` is required because `agent-framework` is a beta dependency.

```bash
uv sync                                   # install deps (dev extras: uv sync --extra dev)

uv run python chat.py                     # terminal chat REPL (dev/testing)
uv run python main.py                     # FastAPI server on APP_PORT (default 8001), auto-reload
uv run uvicorn main:app --host 0.0.0.0 --port 8001 --reload

uv run pytest                             # run all tests (asyncio_mode=auto, testpaths=tests)
uv run pytest tests/test_router_dispatcher.py            # single file
uv run pytest tests/test_router_dispatcher.py::test_dispatch_single_target   # single test

uv run ruff check .                       # lint (line-length 100)
uv run ruff format .                      # format
uv run mypy src                           # type check

docker compose up -d                      # production run; loads .env
```

Copy `.env.example` to `.env` before running anything. `AZURE_OPENAI_API_VERSION` must be `preview` for reasoning models (o1/o3/gpt-5) — the app uses the Responses API, not chat completions.

## Architecture

The system is a **deterministic router → specialists → synthesizer pipeline**, NOT a free-form agent handoff. The orchestration logic lives in Python code (`RouterDispatcher`), and the LLM agents are invoked as discrete steps rather than calling each other.

### Request flow

`main.py` / `chat.py` → `RouterDispatcher.dispatch()` (`src/orchestration/dispatcher.py`) is the core coordinator:

1. **Route** — the `router-agent` classifies the request into a `RouteDecision` (JSON with `targets`, `mode`, `clarifying_question`, `confidence`). `mode` is one of `single | multi | clarify | reject | intro`. If the router's JSON is malformed, `_fallback_decision()` applies keyword heuristics.
2. **Run specialists** — selected specialists from `{kubernetes_monitoring, elasticsearch, rag}` run in sequence. Special chaining: Elasticsearch output is fed as input to the RAG agent, and if ELK output contains an error signal (`_contains_error_signal`), RAG runs automatically even when not explicitly targeted.
3. **Synthesize** — with >1 specialist result, the `synthesizer-agent` merges outputs into fixed sections (Error Logs Summary, Root Cause, Recommendation, Pod Groups, RAG References). A single result is returned verbatim.

Threads are per-session **and** per-tier: `RouterDispatcher._threads[session_id][tier_key]` keeps separate conversation threads for router/each specialist/synthesizer.

### Layers (`src/`)

- **`agents/`** — one `create_*_agent()` factory per agent, each returning a framework `ChatAgent`. Agents differ only in name, description, `instructions` (loaded via `get_prompt`), and `tools`. Router/k8s/rag use the classifier deployment; elasticsearch/synthesizer use the active deployment.
- **`tools/`** — `@ai_function`-decorated async functions grouped into lists (`elasticsearch_tools`, `k8s_monitoring_tools`, `rag_tools`). All tool output goes through `format_tool_result` / `truncate_string` in `tools/utils.py` to prevent context flooding — preserve this when adding tools.
- **`clients/`** — `azure_openai.py` builds a singleton `AzureOpenAIResponsesClient` (API key or `DefaultAzureCredential`); `reset_chat_client()` rebuilds it after model changes. `kube_tools_api.py` / `non_kube_tools_api.py` are HTTP clients for the two external tool backends.
- **`config/`** — `settings.py` (pydantic-settings + runtime model overrides), `prompt_manager.py`, `model_registry.py`, `observability.py`, `chat_ui.py`.
- **`api/`** — `routes.py` (endpoints + alert/RAG glue), `models.py` (pydantic request/response).
- **`orchestration/`** — `dispatcher.py` + `types.py` (`RouteDecision`, `SpecialistResult`, `DispatchResult`).

### Read-only safety guarantee

The agents are strictly read-only. `prompt_manager.NON_NEGOTIABLE_GUARDRAILS` **appends hardcoded refusal rules to the router prompt in code**, so mutating intents (scale/restart/rollout/apply/patch/delete/exec) are rejected regardless of what the Langfuse-hosted prompt says. Keep this guarantee intact when editing routing or prompts.

## Configuration & prompts

- **Prompts** are fetched from **Langfuse** at runtime by name (`prompt_manager.get_prompt`, `@lru_cache`), falling back to `src/config/prompts/*.txt` when Langfuse is unconfigured or fails. Edit both the Langfuse prompt and the local fallback to keep them in sync.
- **Model selection is dynamic and layered**: remote model registry (`GET {NON_KUBE_TOOLS_BASE_URL}/chat-model`) → runtime override (`PUT /api/v1/model`) → `.env` default. `get_active_deployment()` resolves this order; `refresh_runtime_model_from_registry()` rebuilds the dispatcher when the model changes. Runtime-selectable models are whitelisted in `settings.AVAILABLE_RUNTIME_MODELS`.
- **Reasoning vs standard models**: `get_model_options()` branches on `is_reasoning_model()` (prefixes `o1`, `o3`, `gpt-5*`) — reasoning models get `reasoning.effort`, standard models get `temperature`/`top_p`.
- **Observability**: `setup_langfuse_otel()` wires OpenTelemetry → Langfuse. Spans set `input.value`/`output.value`/`langfuse.session.id`/`langfuse.user.id` attributes (Langfuse conventions). Terminal chat exposes the trace link via the `trace` command.

## API endpoints (`/api/v1`)

`POST /chat`, `POST /webhook/alerts`, `POST /approve` (no-op — kept for client compat), `GET/PUT /model` (aliased `/mode`), `GET/DELETE /threads`, `GET /health`.

Messages containing `"kibana alert"` trigger special handling in `/chat`: async broadcast to `{NON_KUBE_TOOLS_BASE_URL}/webhook/broadcast`, plus a direct RAG lookup that augments the dispatch prompt and appends a RAG References block. `/webhook/alerts` formats structured alert payloads into a prompt via `_format_alert_prompt`.

## RAG scripts (`rag/`)

Standalone Azure AI Search workflow, separate from the agent runtime (though `rag/query.py` is imported by `api/routes.py` for the alert path). Vector fields follow the `vector_<key>` naming convention (e.g. `vector_error`).

```bash
uv run python rag/embed.py data/errors_dataset.json error   # adds vector_error field → new file
uv run python rag/upload.py data/vectorized_errors_dataset.json
uv run python rag/query.py "Attempt to read property" --k 5 --key error
```

`query_similar_docs` filters matches by `DEFAULT_MIN_SIMILARITY = 0.8` (strictly greater than).

## Testing conventions

Tests use fake agents (`FakeAgent` returning `SimpleNamespace(text=...)`) to exercise `RouterDispatcher` without hitting Azure — no live API calls. `pytest-asyncio` is in auto mode, so `async def test_*` needs no decorator. When changing dispatcher routing/chaining, update `tests/test_router_dispatcher.py`.

## Deployment

Pushing to `main` triggers `.github/workflows/docker-build-push.yml`: builds the image, pushes to Azure Container Registry, then SSH-deploys `docker-compose.yml` to the server. Commit convention is `chore:`/`feat:`/`fix:` prefixes.
