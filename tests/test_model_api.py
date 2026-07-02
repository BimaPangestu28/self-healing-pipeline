"""Tests for model configuration API route helpers."""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

import src.api.routes as routes
from src.api.models import UpdateModelRequest
from src.config.settings import clear_active_deployment_override, set_active_deployment


@pytest.fixture(autouse=True)
def reset_runtime_model_override():
    clear_active_deployment_override()
    yield
    clear_active_deployment_override()


@pytest.mark.asyncio
async def test_get_model_config_includes_available_models(monkeypatch):
    mock_settings = MagicMock()
    mock_settings.azure_openai_deployment = "gpt-4.1-mini"
    monkeypatch.setattr(routes, "get_settings", lambda: mock_settings)
    set_active_deployment("gpt-4.1")

    response = await routes.get_model_config()

    assert response.active_model == "gpt-4.1"
    assert response.default_model == "gpt-4.1-mini"
    assert response.available_models == ["gpt-4.1-mini", "gpt-4.1"]


@pytest.mark.asyncio
async def test_update_model_config_rejects_unsupported_model():
    with pytest.raises(HTTPException) as exc:
        await routes.update_model_config(UpdateModelRequest(model_name="gpt-5-mini"))

    assert exc.value.status_code == 400
    assert "Supported models: gpt-4.1-mini, gpt-4.1" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_update_model_config_accepts_supported_model(monkeypatch):
    mock_settings = MagicMock()
    mock_settings.azure_openai_deployment = "gpt-4.1-mini"

    async def _fake_get_dispatcher():
        return object()

    monkeypatch.setattr(routes, "get_settings", lambda: mock_settings)
    monkeypatch.setattr(routes, "_get_dispatcher", _fake_get_dispatcher)
    monkeypatch.setattr(routes, "reset_chat_client", lambda: None)

    response = await routes.update_model_config(UpdateModelRequest(model_name="gpt-4.1"))

    assert response.active_model == "gpt-4.1"
    assert response.default_model == "gpt-4.1-mini"
    assert response.available_models == ["gpt-4.1-mini", "gpt-4.1"]
