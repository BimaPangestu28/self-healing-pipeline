from functools import lru_cache
from threading import Lock
from typing import Literal

from pydantic_settings import BaseSettings
import httpx


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Azure OpenAI Configuration
    azure_openai_endpoint: str
    azure_openai_api_key: str | None = None
    azure_openai_api_version: str = "preview"
    azure_openai_deployment: str = "gpt-4.1-mini"
    # Optional remote model registry
    model_registry_timeout_seconds: float = 5.0

    # Tools API Configuration
    kube_tools_base_url: str
    non_kube_tools_base_url: str
    tools_api_key: str | None = None
    # Backward compatibility for older env naming
    kube_tools_api_key: str | None = None
    webhook_api_key: str | None = None

    # Classifier deployment for router, k8s-monitoring, and rag agents
    azure_openai_classifier_deployment: str = "gpt-4.1-mini"

    # Model generation parameters (standard models: gpt-4.1, gpt-4o, etc.)
    agent_temperature: float = 0.8
    agent_top_p: float = 0.9
    agent_max_tokens: int | None = None

    # Reasoning model parameters (o1, o3, gpt-5)
    agent_reasoning_effort: Literal["low", "medium", "high"] = "medium"

    # Langfuse Observability (optional)
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str | None = None

    # OpenTelemetry Configuration
    enable_otel: bool = True
    environment: str = "production"
    otel_enable_sensitive_data: bool = True

    # API auth (optional)
    api_bearer_token: str | None = None

    # Microsoft Teams notifications (Adaptive Cards)
    teams_webhook_url: str | None = None
    teams_notifications_enabled: bool = True

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def get_teams_webhook_url() -> str | None:
    """Get the active Microsoft Teams webhook URL, or None when disabled/unset."""
    settings = get_settings()
    if not settings.teams_notifications_enabled:
        return None
    url = (settings.teams_webhook_url or "").strip()
    return url or None


_runtime_deployment_override: str | None = None
_runtime_endpoint_override: str | None = None
_runtime_api_key_override: str | None = None
_runtime_deployment_lock = Lock()

# Runtime-selectable model deployments exposed by API
AVAILABLE_RUNTIME_MODELS: tuple[str, ...] = ("gpt-4.1-mini", "gpt-4.1")


def get_active_deployment() -> str:
    """Get active deployment: runtime override or .env default."""
    settings = get_settings()
    with _runtime_deployment_lock:
        current_override = _runtime_deployment_override

    deployment, endpoint, api_key = _fetch_active_model_from_registry(settings)
    if deployment:
        set_active_model_config(deployment, endpoint=endpoint, api_key=api_key)
        return deployment

    if current_override:
        return current_override

    return settings.azure_openai_deployment


def get_active_endpoint() -> str:
    """Get active Azure OpenAI endpoint: runtime override or .env default."""
    settings = get_settings()
    with _runtime_deployment_lock:
        return _runtime_endpoint_override or settings.azure_openai_endpoint


def get_active_api_key() -> str | None:
    """Get active Azure OpenAI API key: runtime override or .env default."""
    settings = get_settings()
    with _runtime_deployment_lock:
        return _runtime_api_key_override or settings.azure_openai_api_key


def get_available_runtime_models() -> list[str]:
    """List runtime-selectable deployment names."""
    return list(AVAILABLE_RUNTIME_MODELS)


def is_supported_runtime_model(deployment_name: str) -> bool:
    """Check if deployment can be selected through the runtime model API."""
    return deployment_name in AVAILABLE_RUNTIME_MODELS


def get_runtime_deployment_override() -> str | None:
    """Get runtime deployment override value, if set."""
    with _runtime_deployment_lock:
        return _runtime_deployment_override


def set_active_deployment(deployment_name: str) -> None:
    """Set runtime deployment override."""
    normalized = deployment_name.strip()
    if not normalized:
        raise ValueError("deployment_name cannot be empty")

    global _runtime_deployment_override
    with _runtime_deployment_lock:
        _runtime_deployment_override = normalized


def set_active_endpoint(endpoint: str) -> None:
    """Set runtime Azure OpenAI endpoint override."""
    normalized = endpoint.strip()
    if not normalized:
        raise ValueError("endpoint cannot be empty")

    global _runtime_endpoint_override
    with _runtime_deployment_lock:
        _runtime_endpoint_override = normalized


def set_active_api_key(api_key: str) -> None:
    """Set runtime Azure OpenAI API key override."""
    normalized = api_key.strip()
    if not normalized:
        raise ValueError("api_key cannot be empty")

    global _runtime_api_key_override
    with _runtime_deployment_lock:
        _runtime_api_key_override = normalized


def set_active_model_config(
    deployment_name: str,
    *,
    endpoint: str | None = None,
    api_key: str | None = None,
) -> None:
    """Set runtime Azure OpenAI deployment and optional endpoint/API key overrides."""
    set_active_deployment(deployment_name)
    if endpoint is not None and endpoint.strip():
        set_active_endpoint(endpoint)
    if api_key is not None and api_key.strip():
        set_active_api_key(api_key)


def clear_active_deployment_override() -> None:
    """Clear runtime deployment override and use .env default."""
    global _runtime_deployment_override
    with _runtime_deployment_lock:
        _runtime_deployment_override = None


def clear_active_endpoint_override() -> None:
    """Clear runtime endpoint override and use .env default."""
    global _runtime_endpoint_override
    with _runtime_deployment_lock:
        _runtime_endpoint_override = None


def clear_active_api_key_override() -> None:
    """Clear runtime API key override and use .env default."""
    global _runtime_api_key_override
    with _runtime_deployment_lock:
        _runtime_api_key_override = None


def _fetch_active_model_from_registry(
    settings: Settings,
) -> tuple[str | None, str | None, str | None]:
    base_url = (settings.non_kube_tools_base_url or "").strip()
    if not base_url:
        return None, None, None

    headers = {"accept": "application/json"}
    if settings.tools_api_key:
        headers["Authorization"] = f"Bearer {settings.tools_api_key}"

    url = f"{base_url.rstrip('/')}/chat-model"
    try:
        with httpx.Client(timeout=settings.model_registry_timeout_seconds) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError:
        return None, None, None

    if not isinstance(payload, dict):
        return None, None, None
    if payload.get("is_selected") is False:
        return None, None, None

    deployment = payload.get("azure_openai_deployment") or payload.get("model_name")
    if not deployment or not str(deployment).strip():
        return None, None, None

    endpoint = payload.get("azure_openai_endpoint")
    api_key = payload.get("azure_openai_api_key")

    return (
        str(deployment).strip(),
        str(endpoint).strip() if isinstance(endpoint, str) else None,
        str(api_key).strip() if isinstance(api_key, str) else None,
    )


# Deployment name prefixes that indicate reasoning models
_REASONING_MODEL_PREFIXES = ("o1", "o3", "gpt-5", "gpt-5.1", "gpt-5.2")


def is_reasoning_model(deployment_name: str) -> bool:
    """Check if the deployment name corresponds to a reasoning model."""
    name_lower = deployment_name.lower()
    return any(name_lower.startswith(prefix) for prefix in _REASONING_MODEL_PREFIXES)


def get_model_options(deployment: str | None = None) -> dict:
    """Build default_options dict with correct model parameters.

    Args:
        deployment: Optional deployment name override. If None, uses the
                    default azure_openai_deployment from settings.

    For reasoning models (o1, o3, gpt-5): uses reasoning_effort.
    For standard models: uses temperature and top_p.
    Always includes store=False for local message store compatibility.
    """
    settings = get_settings()
    active_default_deployment = get_active_deployment()

    # If an explicit deployment is provided, use it as-is (e.g. classifier).
    # Otherwise, fall back to get_active_deployment() (registry → runtime → .env).
    resolved_deployment = deployment or active_default_deployment

    options: dict = {"store": False}

    # Override model if different from the client's default deployment
    if deployment and deployment != active_default_deployment:
        options["model_id"] = deployment

    if is_reasoning_model(resolved_deployment):
        options["reasoning"] = {"effort": settings.agent_reasoning_effort}
    else:
        options["temperature"] = settings.agent_temperature
        options["top_p"] = settings.agent_top_p

    if settings.agent_max_tokens is not None:
        options["max_output_tokens"] = settings.agent_max_tokens

    return options
