from agent_framework import ChatAgent

from src.clients.azure_openai import get_chat_client
from src.config.prompt_manager import get_prompt
from src.config.settings import get_model_options, get_settings
from src.tools.rag import rag_tools


async def create_rag_agent() -> ChatAgent:
    """Create the RAG Error Severity Agent."""
    settings = get_settings()
    return ChatAgent(
        chat_client=get_chat_client(),
        name="rag-agent",
        description=(
            "RAG agent for matching error messages and returning severity from the index"
        ),
        instructions=get_prompt("rag-agent"),
        tools=rag_tools,
        default_options=get_model_options(settings.azure_openai_classifier_deployment),
    )
