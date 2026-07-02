"""Router-tier dispatcher for specialist execution and optional synthesis."""

from __future__ import annotations

import json
import re
from contextlib import suppress
from typing import Any

from agent_framework import ChatAgent

from src.config.chat_ui import get_agent_intro_message
from src.orchestration.types import DispatchResult, RouteDecision, SpecialistResult


class RouterDispatcher:
    """Deterministic orchestration around router/specialist/synthesizer agents."""

    def __init__(
        self,
        router: ChatAgent,
        specialists: dict[str, ChatAgent],
        synthesizer: ChatAgent | None = None,
    ) -> None:
        self._router = router
        self._specialists = specialists
        self._synthesizer = synthesizer
        self._threads: dict[str, dict[str, Any]] = {}

    async def dispatch(self, user_message: str, thread_id: str) -> DispatchResult:
        """Route request, run selected specialist agents, and synthesize output."""
        decision = await self._route_request(user_message, thread_id)

        if decision.mode == "intro":
            return DispatchResult(message=get_agent_intro_message())

        if decision.mode == "clarify":
            message = decision.clarifying_question or (
                "Please clarify whether you want Kubernetes monitoring analysis, "
                "Elasticsearch log analysis, or both."
            )
            return DispatchResult(message=message)

        if decision.mode == "reject":
            return DispatchResult(
                message=(
                    "Hi, thank you for the message. I could help you to monitor Kubernetes"
                    "and analyze Elasticsearch logs."
                )
            )

        results = await self._run_specialists(decision, user_message, thread_id)
        if not results:
            return DispatchResult(
                message="I could not determine the right specialist for this request."
            )

        if len(results) == 1:
            return DispatchResult(message=results[0].text)

        synthesized = await self._synthesize(user_message, results, thread_id)
        return DispatchResult(message=synthesized)

    def reset_thread(self, thread_id: str) -> None:
        """Clear dispatcher-managed per-tier threads for a session."""
        self._threads.pop(thread_id, None)

    def has_thread(self, thread_id: str) -> bool:
        """Return True when dispatcher has state for thread ID."""
        return thread_id in self._threads

    async def _route_request(self, user_message: str, thread_id: str) -> RouteDecision:
        """Run the router and coerce output into RouteDecision."""
        prompt = (
            "Classify the request and return ONLY JSON with keys "
            "targets, mode, clarifying_question, confidence.\n"
            "Request:\n"
            f"{user_message}"
        )

        thread = self._ensure_thread(self._router, thread_id, "router")
        result = await self._router.run(prompt, thread=thread)
        text = self._extract_text(result)
        with suppress(Exception):
            parsed = self._parse_json(text)
            return RouteDecision(**parsed)

        return self._fallback_decision(user_message)

    async def _run_specialists(
        self,
        decision: RouteDecision,
        user_message: str,
        thread_id: str,
    ) -> list[SpecialistResult]:
        """Run specialist agents selected by router."""
        targets = [target for target in decision.targets if target in self._specialists]
        if not targets:
            return []

        if "elasticsearch" in targets and "rag" in targets:
            targets = [
                target
                for target in ["elasticsearch", "rag"]
                if target in targets
            ] + [target for target in targets if target not in {"elasticsearch", "rag"}]

        results: list[SpecialistResult] = []
        elk_text: str | None = None
        for target in targets:
            specialist = self._specialists[target]
            thread = self._ensure_thread(specialist, thread_id, target)
            if target == "rag" and elk_text:
                result = await specialist.run(elk_text, thread=thread)
            else:
                result = await specialist.run(user_message, thread=thread)
            text = self._extract_text(result)
            results.append(SpecialistResult(target=target, text=text))
            if target == "elasticsearch":
                elk_text = text

        if "elasticsearch" in targets and "rag" not in targets and "rag" in self._specialists:
            if elk_text and _contains_error_signal(elk_text):
                rag_agent = self._specialists["rag"]
                rag_thread = self._ensure_thread(rag_agent, thread_id, "rag")
                rag_result = await rag_agent.run(elk_text, thread=rag_thread)
                results.append(
                    SpecialistResult(target="rag", text=self._extract_text(rag_result))
                )

        return results

    async def _synthesize(
        self,
        user_message: str,
        results: list[SpecialistResult],
        thread_id: str,
    ) -> str:
        """Combine multi-specialist outputs into one user-facing response."""
        if self._synthesizer is None:
            blocks = [f"[{result.target}]\n{result.text}" for result in results]
            return "\n\n".join(blocks)

        specialist_text = "\n\n".join(
            f"[{result.target}]\n{result.text}" for result in results
        )
        synth_prompt = (
            "Synthesize the specialist outputs into one concise response.\n"
            "For alert inputs, use exactly these sections in order: "
            "Error Logs Summary, Root Cause, Recommendation, Pod Groups, RAG References.\n"
            "Integrate the RAG specialist's Explanation into Root Cause and its "
            "Recommendation into the Recommendation section. "
            "The RAG References section must ONLY contain the reference list lines "
            "(e.g. '- <id>: app=...'). Do not duplicate content across sections.\n"
            f"User request:\n{user_message}\n\n"
            f"Specialist outputs:\n{specialist_text}"
        )

        thread = self._ensure_thread(self._synthesizer, thread_id, "synthesizer")
        result = await self._synthesizer.run(synth_prompt, thread=thread)
        synthesized = self._extract_text(result)
        rag_references = self._extract_rag_references(results)
        if rag_references and "RAG References" not in synthesized:
            return f"{synthesized.rstrip()}\n\n{rag_references}"
        return synthesized

    @staticmethod
    def _extract_rag_references(results: list[SpecialistResult]) -> str | None:
        for result in results:
            if result.target != "rag":
                continue
            match = re.search(r"(RAG References:\n(?:- .*(?:\n|$))*)", result.text.strip())
            if match:
                return match.group(1).rstrip()
        return None

    def _ensure_thread(self, agent: ChatAgent, session_id: str, key: str):
        """Get or create per-session thread for a specific tier/agent."""
        session_threads = self._threads.setdefault(session_id, {})
        if key not in session_threads:
            session_threads[key] = agent.get_new_thread()
        return session_threads[key]

    @staticmethod
    def _extract_text(result) -> str:
        """Safely extract text from framework run result."""
        text = getattr(result, "text", None)
        if isinstance(text, str) and text.strip():
            return text
        return str(result)

    @staticmethod
    def _parse_json(text: str) -> dict:
        """Parse router JSON, including fenced JSON fallback."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", cleaned, re.DOTALL)
            if fenced:
                cleaned = fenced.group(1)

        return json.loads(cleaned)

    @staticmethod
    def _fallback_decision(user_message: str) -> RouteDecision:
        """Heuristic fallback when router output is malformed."""
        message = user_message.lower()
        has_mutating_intent = any(
            token in message
            for token in [
                "scale",
                "rollout",
                "restart",
                "delete",
                "apply",
                "patch",
                "edit",
                "create",
                "exec ",
                "kubectl exec",
            ]
        )
        has_k8s = any(token in message for token in ["k8s", "kubernetes", "deployment", "pod"])
        has_logs = any(token in message for token in ["log", "logs", "elk", "elasticsearch", "es"])
        has_error_text = _contains_error_signal(message)
        has_rag = any(
            token in message
            for token in [
                "severity",
                "severities",
                "classify",
                "classification",
                "triage",
                "label",
                "priority",
            ]
        )

        if has_mutating_intent and has_k8s:
            return RouteDecision(mode="reject", confidence=0.6)
        if has_k8s and has_logs:
            return RouteDecision(
                targets=["kubernetes_monitoring", "elasticsearch"],
                mode="multi",
                confidence=0.5,
            )
        if has_logs and (has_rag or has_error_text):
            return RouteDecision(targets=["elasticsearch", "rag"], mode="multi", confidence=0.5)
        if (has_rag or has_error_text) and not has_k8s:
            return RouteDecision(targets=["rag"], mode="single", confidence=0.5)
        if has_k8s:
            return RouteDecision(targets=["kubernetes_monitoring"], mode="single", confidence=0.5)
        if has_logs:
            return RouteDecision(targets=["elasticsearch"], mode="single", confidence=0.5)

        return RouteDecision(mode="clarify", confidence=0.0)


def _contains_error_signal(text: str) -> bool:
    lowered = text.lower()
    return any(
        token in lowered
        for token in [
            "error",
            "exception",
            "stack trace",
            "traceback",
            "fatal",
            "panic",
            "segfault",
            "nullpointer",
            "null pointer",
        ]
    )
