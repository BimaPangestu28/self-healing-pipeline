"""Fetch active model configuration from remote registry."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from src.clients.azure_openai import reset_chat_client
from src.config.settings import (
    get_active_api_key,
    get_active_endpoint,
    get_runtime_deployment_override,
    get_settings,
    set_active_model_config,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RegistryModelConfig:
    deployment: str
    endpoint: str | None
    api_key: str | None


def _coerce_config(payload: dict) -> RegistryModelConfig | None:
    deployment = payload.get("azure_openai_deployment") or payload.get("model_name")
    if not deployment or not str(deployment).strip():
        return None

    endpoint = payload.get("azure_openai_endpoint")
    api_key = payload.get("azure_openai_api_key")
    return RegistryModelConfig(
        deployment=str(deployment).strip(),
        endpoint=str(endpoint).strip() if isinstance(endpoint, str) else None,
        api_key=str(api_key).strip() if isinstance(api_key, str) else None,
    )


async def refresh_runtime_model_from_registry() -> bool:
    """Fetch active model config from registry and apply runtime overrides."""
    settings = get_settings()
    current_deployment = get_runtime_deployment_override() or settings.azure_openai_deployment
    current_endpoint = get_active_endpoint()
    current_api_key = get_active_api_key()

    base_url = (settings.non_kube_tools_base_url or "").strip()
    if not base_url:
        logger.info("NON_KUBE_TOOLS_BASE_URL not configured; skipping refresh.")
        return False

    headers = {"accept": "application/json"}
    if settings.tools_api_key:
        headers["Authorization"] = f"Bearer {settings.tools_api_key}"

    url = f"{base_url.rstrip('/')}/chat-model"
    timeout = settings.model_registry_timeout_seconds
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        logger.warning("Model registry fetch failed: %s", exc)
        return False

    if isinstance(payload, dict) and payload.get("is_selected") is False:
        logger.warning("Model registry returned inactive model; skipping update.")
        return False

    config = _coerce_config(payload if isinstance(payload, dict) else {})
    if config is None:
        logger.warning("Model registry payload missing deployment name; skipping update.")
        return False

    endpoint = config.endpoint or current_endpoint
    api_key = config.api_key or current_api_key

    if (
        config.deployment == current_deployment
        and endpoint == current_endpoint
        and api_key == current_api_key
    ):
        return False

    set_active_model_config(config.deployment, endpoint=endpoint, api_key=api_key)
    reset_chat_client()
    logger.info("Runtime model updated from registry: %s", config.deployment)
    return True
