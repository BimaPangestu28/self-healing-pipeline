import os
from typing import Any

from azure.identity.aio import DefaultAzureCredential

from src.config.settings import get_settings

try:
    from agent_framework_aisearch import AzureAISearchContextProvider
except ImportError:  # pragma: no cover - optional dependency
    AzureAISearchContextProvider = None


def _resolve_endpoint() -> str | None:
    endpoint = os.getenv("AZURE_SEARCH_ENDPOINT")
    if endpoint:
        return endpoint

    azure_ai_search = os.getenv("AZURE_AI_SEARCH")
    if azure_ai_search:
        return (
            azure_ai_search
            if azure_ai_search.startswith("http")
            else f"https://{azure_ai_search}.search.windows.net"
        )

    service_name = os.getenv("AZURE_AI_SEARCH_SERVICE_NAME")
    if service_name:
        return f"https://{service_name}.search.windows.net"

    return None


def _resolve_index_name() -> str | None:
    return os.getenv("AZURE_SEARCH_INDEX_NAME") or os.getenv("AZURE_AI_SEARCH_INDEX_NAME")


def create_azure_ai_search_context_provider() -> Any | None:
    """Create Azure AI Search context provider from environment configuration."""
    if AzureAISearchContextProvider is None:
        return None

    _ = get_settings()  # Ensure .env is loaded before env lookups.
    credential = DefaultAzureCredential()
    endpoint = _resolve_endpoint()
    index_name = _resolve_index_name()

    if endpoint and index_name:
        return AzureAISearchContextProvider(
            endpoint=endpoint,
            index_name=index_name,
            credential=credential,
        )

    return AzureAISearchContextProvider(
        credential=credential,
        env_file_path=".env",
    )
