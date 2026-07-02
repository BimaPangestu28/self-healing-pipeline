from agent_framework import ChatAgent

from src.clients.azure_openai import get_chat_client
from src.config.prompt_manager import get_prompt
from src.config.settings import get_model_options
from src.tools.elasticsearch import elasticsearch_tools


async def create_elasticsearch_agent() -> ChatAgent:
    """Create the Elasticsearch Agent."""
    return ChatAgent(
        chat_client=get_chat_client(),
        name="elasticsearch-agent",
        description="Elasticsearch Agent for log search, document retrieval, error detection, and incident investigation",
        instructions=get_prompt("elasticsearch-agent"),
        tools=elasticsearch_tools,
        default_options=get_model_options(),
    )
