from agent_framework.azure import AzureOpenAIResponsesClient
from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential

from src.config.settings import get_active_api_key, get_active_deployment, get_active_endpoint, get_settings

_client: AzureOpenAIResponsesClient | None = None


def get_chat_client() -> AzureOpenAIResponsesClient:
    """Get or create the Azure OpenAI Responses client singleton."""
    global _client

    if _client is None:
        settings = get_settings()
        endpoint = get_active_endpoint()
        api_key = get_active_api_key()

        # Use API Key authentication if provided, otherwise use Azure Identity
        if api_key:
            _client = AzureOpenAIResponsesClient(
                endpoint=endpoint,
                deployment_name=get_active_deployment(),
                api_version=settings.azure_openai_api_version,
                credential=AzureKeyCredential(api_key),
            )
        else:
            # Use Managed Identity / Azure CLI / Environment credentials
            _client = AzureOpenAIResponsesClient(
                endpoint=endpoint,
                deployment_name=get_active_deployment(),
                api_version=settings.azure_openai_api_version,
                credential=DefaultAzureCredential(),
            )

    return _client


def reset_chat_client() -> None:
    """Reset cached chat client so it can be rebuilt with new deployment config."""
    global _client
    _client = None
