from agent_framework import ChatAgent

from src.clients.azure_openai import get_chat_client
from src.config.prompt_manager import get_prompt
from src.config.settings import get_model_options, get_settings


async def create_router_agent() -> ChatAgent:
    """Create the lightweight routing agent."""
    settings = get_settings()
    return ChatAgent(
        chat_client=get_chat_client(),
        name="router-agent",
        description="Router agent for intent classification and specialist selection",
        instructions=get_prompt("router-agent"),
        tools=[],
        default_options=get_model_options(settings.azure_openai_classifier_deployment),
    )
