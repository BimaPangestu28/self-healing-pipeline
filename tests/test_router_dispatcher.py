from types import SimpleNamespace

from src.config.chat_ui import AGENT_INTRO_MESSAGE
from src.orchestration.dispatcher import RouterDispatcher


class FakeAgent:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []
        self.thread_count = 0

    def get_new_thread(self):
        self.thread_count += 1
        return f"thread-{self.thread_count}"

    async def run(self, message, thread=None):
        self.calls.append((message, thread))
        text = self._responses.pop(0)
        return SimpleNamespace(text=text)


async def test_dispatch_single_target():
    router = FakeAgent([
        '{"targets": ["kubernetes_monitoring"], "mode": "single", "clarifying_question": null, "confidence": 0.92}'
    ])
    k8s = FakeAgent(["k8s-output"])

    dispatcher = RouterDispatcher(router=router, specialists={"kubernetes_monitoring": k8s})

    result = await dispatcher.dispatch("check deployment", "t1")

    assert result.message == "k8s-output"
    assert len(k8s.calls) == 1


async def test_dispatch_greeting_returns_intro_without_specialist_call():
    router = FakeAgent([
        '{"targets": [], "mode": "intro", "clarifying_question": null, "confidence": 0.95}'
    ])
    k8s = FakeAgent(["k8s-output"])

    dispatcher = RouterDispatcher(router=router, specialists={"kubernetes_monitoring": k8s})

    result = await dispatcher.dispatch("hello", "t-greet")

    assert result.message == AGENT_INTRO_MESSAGE
    assert len(router.calls) == 1
    assert len(k8s.calls) == 0


async def test_dispatch_capability_question_returns_intro_without_specialist_call():
    router = FakeAgent([
        '{"targets": [], "mode": "intro", "clarifying_question": null, "confidence": 0.94}'
    ])
    k8s = FakeAgent(["k8s-output"])

    dispatcher = RouterDispatcher(router=router, specialists={"kubernetes_monitoring": k8s})

    result = await dispatcher.dispatch("what can you do?", "t-cap")

    assert result.message == AGENT_INTRO_MESSAGE
    assert len(router.calls) == 1
    assert len(k8s.calls) == 0


async def test_dispatch_good_morning_returns_intro_without_specialist_call():
    router = FakeAgent([
        '{"targets": [], "mode": "intro", "clarifying_question": null, "confidence": 0.9}'
    ])
    k8s = FakeAgent(["k8s-output"])

    dispatcher = RouterDispatcher(router=router, specialists={"kubernetes_monitoring": k8s})

    result = await dispatcher.dispatch("good morning", "t-good-morning")

    assert result.message == AGENT_INTRO_MESSAGE
    assert len(router.calls) == 1
    assert len(k8s.calls) == 0


async def test_dispatch_multi_target_uses_synthesizer():
    router = FakeAgent([
        '{"targets": ["kubernetes_monitoring", "elasticsearch"], "mode": "multi", "clarifying_question": null, "confidence": 0.85}'
    ])
    k8s = FakeAgent(["k8s-output"])
    elk = FakeAgent(["elk-output"])
    synth = FakeAgent(["final-merged"])

    dispatcher = RouterDispatcher(
        router=router,
        specialists={"kubernetes_monitoring": k8s, "elasticsearch": elk},
        synthesizer=synth,
    )

    result = await dispatcher.dispatch("investigate pod and logs", "t2")

    assert result.message == "final-merged"
    assert len(k8s.calls) == 1
    assert len(elk.calls) == 1
    assert len(synth.calls) == 1


async def test_dispatch_multi_target_appends_rag_references_when_missing_from_synth_output():
    router = FakeAgent([
        '{"targets": ["elasticsearch", "rag"], "mode": "multi", "clarifying_question": null, "confidence": 0.85}'
    ])
    elk = FakeAgent(["elk-output"])
    rag = FakeAgent(
        [
            "Explanation: likely high severity\n"
            "Recommendation: inspect retries\n"
            "RAG References:\n"
            "- doc-1: app=payments, category=timeout, error=deadline exceeded, "
            "explanation=upstream timeout (severity HIGH)"
        ]
    )
    synth = FakeAgent(["final-merged"])

    dispatcher = RouterDispatcher(
        router=router,
        specialists={"elasticsearch": elk, "rag": rag},
        synthesizer=synth,
    )

    result = await dispatcher.dispatch("investigate payment timeout", "t-rag-ref")

    assert result.message.endswith(
        "RAG References:\n"
        "- doc-1: app=payments, category=timeout, error=deadline exceeded, "
        "explanation=upstream timeout (severity HIGH)"
    )


async def test_dispatch_fallback_when_router_output_invalid():
    router = FakeAgent(["not-json"])
    elk = FakeAgent(["elk-output"])

    dispatcher = RouterDispatcher(router=router, specialists={"elasticsearch": elk})

    result = await dispatcher.dispatch("find error logs", "t3")

    assert result.message == "elk-output"


async def test_dispatch_fallback_rejects_mutating_k8s_requests():
    router = FakeAgent(["not-json"])
    k8s = FakeAgent(["k8s-output"])

    dispatcher = RouterDispatcher(router=router, specialists={"kubernetes_monitoring": k8s})

    result = await dispatcher.dispatch("scale deployment ai-ops-api to 5 replicas", "t-scale")

    assert "read-only" in result.message.lower()
    assert "can't perform operational changes" in result.message.lower()
    assert len(k8s.calls) == 0


async def test_reset_thread_clears_state():
    router = FakeAgent([
        '{"targets": ["elasticsearch"], "mode": "single", "clarifying_question": null, "confidence": 0.9}',
        '{"targets": ["elasticsearch"], "mode": "single", "clarifying_question": null, "confidence": 0.9}',
    ])
    elk = FakeAgent(["first", "second"])

    dispatcher = RouterDispatcher(router=router, specialists={"elasticsearch": elk})

    await dispatcher.dispatch("logs", "t4")
    first_thread = elk.calls[0][1]

    dispatcher.reset_thread("t4")
    await dispatcher.dispatch("logs", "t4")
    second_thread = elk.calls[1][1]

    assert first_thread != second_thread
