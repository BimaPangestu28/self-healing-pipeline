"""Conversational SRE agent (LLM tool-calling) for the demo chat.

The agent can inspect the target (``get_healthcheck``) and *propose* a remediation
(``propose_remediation``) — but it can NEVER execute anything itself. Remediation
only happens when a human clicks Approve on the approval card the proposal returns.
This keeps the LLM advisory while all mutations stay behind human approval.
"""

from __future__ import annotations

import json
import logging

from src.approvals.cards import build_approval_card, build_healthcheck_card
from src.approvals.service import DemoService

logger = logging.getLogger(__name__)

_MAX_STEPS = 5
_HISTORY_LIMIT = 12

_SYSTEM_PROMPT = (
    "You are AION, an SRE assistant for the Outsystem application on host "
    "INDIGIINPAPP7. Use get_healthcheck to inspect health (memory, W3SVC) and "
    "propose_remediation to raise a remediation for human approval. You must NEVER "
    "claim to have restarted, executed, or fixed anything yourself — remediation "
    "only happens after a human approves the card. Be concise and practical."
)

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_healthcheck",
            "description": "Run a healthcheck on the Outsystem host and return its status.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_remediation",
            "description": (
                "Propose a remediation for the current issue. Opens a human approval "
                "card; does NOT execute anything."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


class ChatAgent:
    """LLM-driven chat over the approval service, with per-session history."""

    def __init__(self, service: DemoService, client_factory=None) -> None:
        self.service = service
        if client_factory is None:
            from src.llm import build_llm_client

            client_factory = build_llm_client
        self._client_factory = client_factory
        self._history: dict[str, list[dict]] = {}

    def handle(self, session_id: str, message: str) -> dict:
        """Process a user message; return {reply, cards, llm}.

        @param session_id - conversation id (keeps per-session history)
        @param message - the user's text
        @returns dict with the assistant reply, any Adaptive Cards, and whether an
                 LLM was used
        """
        client = self._client_factory()
        if client is None:
            return {
                "reply": "LLM is not configured. Set LLM_PROVIDER + credentials "
                "(e.g. LLM_PROVIDER=deepseek, DEEPSEEK_API_KEY).",
                "cards": [],
                "llm": False,
            }

        history = self._history.get(session_id, [])
        messages = [{"role": "system", "content": _SYSTEM_PROMPT}, *history,
                    {"role": "user", "content": message}]
        cards: list[dict] = []

        for _ in range(_MAX_STEPS):
            try:
                reply = client.complete(messages, _TOOLS)
            except Exception as exc:  # network/parse — surface gracefully
                logger.warning("agent LLM call failed: %s", exc)
                return {"reply": f"LLM error: {exc}", "cards": cards, "llm": True}

            if not reply.tool_calls:
                text = (reply.content or "").strip()
                self._remember(session_id, history, message, text)
                return {"reply": text, "cards": cards, "llm": True}

            messages.append(
                {
                    "role": "assistant",
                    "content": reply.content or "",
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {"name": call.name, "arguments": call.arguments},
                        }
                        for call in reply.tool_calls
                    ],
                }
            )
            for call in reply.tool_calls:
                result, card = self._dispatch(call.name, call.arguments)
                if card is not None:
                    cards.append(card)
                messages.append(
                    {"role": "tool", "tool_call_id": call.id, "content": json.dumps(result)}
                )

        return {"reply": "Stopped after too many tool steps.", "cards": cards, "llm": True}

    def _remember(self, session_id: str, history: list[dict], user: str, assistant: str) -> None:
        """Append the exchange to bounded per-session history."""
        updated = [*history, {"role": "user", "content": user},
                   {"role": "assistant", "content": assistant}]
        self._history[session_id] = updated[-_HISTORY_LIMIT:]

    def _dispatch(self, name: str, arguments: str) -> tuple[dict, dict | None]:
        """Execute a tool and return (json-result, optional Adaptive Card)."""
        if name == "get_healthcheck":
            report = self.service.healthcheck()
            card = build_healthcheck_card(report)
            return (
                {
                    "host": report.host,
                    "application": report.application,
                    "healthy": report.healthy,
                    "memory_percent": report.memory_percent,
                    "services": [
                        {"name": s.name, "ok": s.ok, "detail": s.detail}
                        for s in report.services
                    ],
                },
                card,
            )

        if name == "propose_remediation":
            report = self.service.healthcheck()
            action = self.service.recommend_action(report)
            if action is None:
                return ({"proposed": False, "reason": "host is already healthy"}, None)
            request = self.service.create_approval(action)
            return (
                {
                    "proposed": True,
                    "request_id": request.request_id,
                    "action": action.action,
                    "description": action.description,
                    "note": "Awaiting human approval on the card.",
                },
                build_approval_card(request),
            )

        return ({"error": f"unknown tool: {name}"}, None)
