from agent_framework import ChatAgent

from src.clients.azure_openai import get_chat_client
from src.config.prompt_manager import get_prompt
from src.config.settings import get_model_options


async def create_synthesizer_agent() -> ChatAgent:
    """Create the synthesis agent for multi-specialist responses."""
    return ChatAgent(
        chat_client=get_chat_client(),
        name="synthesizer-agent",
        description="Synthesizer agent to combine specialist outputs into a concise answer",
        instructions=get_prompt("synthesizer-agent"),
        tools=[],
        default_options=get_model_options(),
    )
