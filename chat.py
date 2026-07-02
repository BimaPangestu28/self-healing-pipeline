"""Terminal chat interface for quick interaction with the router-tier SRE agent."""

import asyncio
import atexit
from contextlib import nullcontext

from agent_framework.observability import get_tracer
from dotenv import load_dotenv
from opentelemetry import trace

from src.agents.elasticsearch_agent import create_elasticsearch_agent
from src.agents.k8s_monitoring_agent import create_k8s_monitoring_agent
from src.agents.rag_agent import create_rag_agent
from src.agents.router_agent import create_router_agent
from src.agents.synthesizer_agent import create_synthesizer_agent
from src.config.chat_ui import AGENT_INTRO_MESSAGE, with_new_session_hint
from src.config.observability import get_langfuse_trace_link, setup_langfuse_otel
from src.orchestration.dispatcher import RouterDispatcher

# Load environment variables
load_dotenv()

# Initialize Langfuse OTEL before creating agents
_otel_enabled = setup_langfuse_otel()
_tracer = None
if _otel_enabled:
    print("Langfuse OTEL observability enabled")
    _tracer = get_tracer()
else:
    print("Langfuse OTEL observability disabled or not configured")


def _flush_traces():
    """Flush pending traces before exit."""
    try:
        provider = trace.get_tracer_provider()
        if hasattr(provider, "force_flush"):
            provider.force_flush(timeout_millis=5000)
    except Exception:
        pass


# Register trace flush on exit
atexit.register(_flush_traces)


async def _create_dispatcher() -> RouterDispatcher:
    """Create router-tier dispatcher for terminal usage."""
    router = await create_router_agent()
    k8s_agent = await create_k8s_monitoring_agent()
    elk_agent = await create_elasticsearch_agent()
    rag_agent = await create_rag_agent()
    synthesizer = await create_synthesizer_agent()
    return RouterDispatcher(
        router=router,
        specialists={
            "kubernetes_monitoring": k8s_agent,
            "elasticsearch": elk_agent,
            "rag": rag_agent,
        },
        synthesizer=synthesizer,
    )


async def main():
    """Run the terminal chat interface."""
    print("Initializing SRE router-tier agents...")
    dispatcher = await _create_dispatcher()

    # Generate session_id and user_id for tracking
    import uuid

    session_id = str(uuid.uuid4())
    user_id = input("Enter your user ID (or press Enter for 'anonymous'): ").strip() or "anonymous"

    print("SRE Agent Insignia ready!")
    print("-" * 50)
    print(f"Session ID: {session_id}")
    print(f"User ID: {user_id}")
    print("-" * 50)
    print(with_new_session_hint(AGENT_INTRO_MESSAGE))
    print("Commands: 'quit' or 'exit' to exit, 'clear' for new conversation, 'trace' for last trace link")
    print("-" * 50)

    last_trace_link = None

    while True:
        try:
            user_input = input("\nYou: ").strip()

            if not user_input:
                continue

            if user_input.lower() in ("quit", "exit"):
                print("Goodbye!")
                _flush_traces()
                break

            if user_input.lower() == "clear":
                session_id = str(__import__("uuid").uuid4())
                dispatcher.reset_thread(session_id)
                print(f"Started new conversation. New Session ID: {session_id}")
                print(with_new_session_hint(AGENT_INTRO_MESSAGE))
                continue

            if user_input.lower() == "trace":
                if last_trace_link:
                    print(f"Last trace: {last_trace_link}")
                else:
                    print("No trace available yet.")
                continue

            # Create span context for tracing
            span_context = _tracer.start_as_current_span("sre_agent.chat") \
                if _tracer else nullcontext()

            with span_context as root_span:
                # Set input attribute on span (Langfuse expects "input.value")
                if _tracer and root_span:
                    root_span.set_attribute("input.value", user_input)
                    root_span.set_attribute("langfuse.session.id", session_id)
                    root_span.set_attribute("langfuse.user.id", user_id)

                dispatch_result = await dispatcher.dispatch(user_input, session_id)
                result_text = with_new_session_hint(dispatch_result.message)

                # Set output attribute on span (Langfuse expects "output.value")
                if _tracer and root_span:
                    root_span.set_attribute("output.value", result_text)

                # Capture trace link after agent run
                last_trace_link = get_langfuse_trace_link()

            # Print response
            print(f"\nAgent: {result_text}")

            # Show trace link if OTEL is enabled
            if _otel_enabled and last_trace_link:
                print(f"\n[Trace: {last_trace_link}]")

        except KeyboardInterrupt:
            print("\nGoodbye!")
            _flush_traces()
            break
        except Exception as e:
            print(f"\nError: {e}")


if __name__ == "__main__":
    asyncio.run(main())
