"""Tests for the conversational SRE agent (tool-calling, execution stays gated)."""

from __future__ import annotations

from src.approvals.agent import ChatAgent
from src.approvals.executors import KubernetesExecutor
from src.approvals.service import DemoService
from src.llm.types import LlmMessage, ToolCall
from src.self_healing.config import PipelineConfig

CONFIG = PipelineConfig(deployment="memory-app", container="app", service="memory-app")


class FakeKube:
    """Always-running deployment reporting high memory until restarted."""

    def __init__(self) -> None:
        self.namespace = CONFIG.namespace
        self.restart_calls = 0
        self.memory = 88

    def apply(self, manifest_path: str) -> None:
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
        self.memory = 5

    def wait_rollout(self, deployment: str, timeout: int = 120) -> bool:
        return True


class ScriptedLLM:
    """Returns a fixed sequence of LlmMessage objects on successive complete() calls."""

    def __init__(self, script: list[LlmMessage]) -> None:
        self._script = list(script)
        self._index = 0

    def complete(self, messages, tools=None, tool_choice="auto") -> LlmMessage:
        message = self._script[self._index]
        self._index += 1
        return message


def _service() -> DemoService:
    kube = FakeKube()
    return DemoService(kube=kube, config=CONFIG, executor=KubernetesExecutor(kube, CONFIG))


def test_agent_healthcheck_tool_returns_card_and_reply():
    llm = ScriptedLLM(
        [
            LlmMessage(tool_calls=[ToolCall("c1", "get_healthcheck", "{}")]),
            LlmMessage(content="Outsystem memory is high at 88%. Recommend a restart."),
        ]
    )
    agent = ChatAgent(_service(), client_factory=lambda: llm)

    out = agent.handle("s1", "how is outsystem doing?")

    assert out["llm"] is True
    assert "88" in out["reply"]
    assert len(out["cards"]) == 1
    assert out["cards"][0]["body"][0]["text"].startswith("🩺")


def test_agent_propose_opens_approval_card_without_executing():
    service = _service()
    llm = ScriptedLLM(
        [
            LlmMessage(tool_calls=[ToolCall("c2", "propose_remediation", "{}")]),
            LlmMessage(content="I've raised a remediation for your approval."),
        ]
    )
    agent = ChatAgent(service, client_factory=lambda: llm)

    out = agent.handle("s1", "please fix the memory issue")

    card = out["cards"][0]
    verbs = {action["data"]["verb"] for action in card["actions"]}
    assert verbs == {"approve", "reject"}
    assert len(service._requests) == 1  # a pending approval exists
    assert service.kube.restart_calls == 0  # nothing executed by the agent


def test_agent_plain_reply_has_no_cards():
    llm = ScriptedLLM([LlmMessage(content="Hello, I can check the Outsystem host.")])
    agent = ChatAgent(_service(), client_factory=lambda: llm)

    out = agent.handle("s1", "hi")
    assert out["reply"].startswith("Hello")
    assert out["cards"] == []


def test_agent_without_llm_reports_not_configured():
    agent = ChatAgent(_service(), client_factory=lambda: None)
    out = agent.handle("s1", "hi")
    assert out["llm"] is False
    assert "not configured" in out["reply"].lower()
