from agent_framework import ChatAgent

from src.clients.azure_openai import get_chat_client
from src.config.prompt_manager import get_prompt
from src.config.settings import get_model_options, get_settings
from src.tools.k8s_monitoring import k8s_monitoring_tools


async def create_k8s_monitoring_agent() -> ChatAgent:
    """Create the Kubernetes Monitoring Agent."""
    settings = get_settings()
    return ChatAgent(
        chat_client=get_chat_client(),
        name="k8s-monitoring-agent",
        description="Kubernetes Monitoring Agent for metrics, health checks, capacity analysis, and performance insights",
        instructions=get_prompt("k8s-monitor-agent"),
        tools=k8s_monitoring_tools,
        default_options=get_model_options(settings.azure_openai_classifier_deployment),
    )
