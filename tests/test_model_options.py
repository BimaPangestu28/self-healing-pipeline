"""Tests for model-type-aware parameter configuration."""

from unittest.mock import MagicMock, patch

import pytest

from src.config.settings import (
    AVAILABLE_RUNTIME_MODELS,
    clear_active_deployment_override,
    get_active_deployment,
    get_available_runtime_models,
    get_model_options,
    is_supported_runtime_model,
    is_reasoning_model,
    set_active_deployment,
)


@pytest.fixture(autouse=True)
def reset_runtime_model_override():
    clear_active_deployment_override()
    yield
    clear_active_deployment_override()


class TestIsReasoningModel:
    """Tests for reasoning model detection."""

    def test_standard_models(self):
        assert is_reasoning_model("gpt-4.1-mini") is False
        assert is_reasoning_model("gpt-4o") is False
        assert is_reasoning_model("gpt-4.1") is False
        assert is_reasoning_model("gpt-4") is False

    def test_reasoning_models(self):
        assert is_reasoning_model("o1") is True
        assert is_reasoning_model("o1-preview") is True
        assert is_reasoning_model("o1-mini") is True
        assert is_reasoning_model("o3") is True
        assert is_reasoning_model("o3-mini") is True
        assert is_reasoning_model("gpt-5") is True
        assert is_reasoning_model("gpt-5-turbo") is True
        assert is_reasoning_model("gpt-5.1") is True
        assert is_reasoning_model("gpt-5.2") is True

    def test_case_insensitive(self):
        assert is_reasoning_model("O1-Preview") is True
        assert is_reasoning_model("O3-Mini") is True
        assert is_reasoning_model("GPT-5") is True

    def test_no_false_positives(self):
        assert is_reasoning_model("omni-1") is False
        assert is_reasoning_model("opt-3") is False
        assert is_reasoning_model("gpt-4.5") is False


class TestGetModelOptions:
    """Tests for model options builder."""

    def _mock_settings(self, **overrides):
        defaults = {
            "azure_openai_deployment": "gpt-4.1-mini",
            "agent_temperature": 0.8,
            "agent_top_p": 0.9,
            "agent_reasoning_effort": "medium",
            "agent_max_tokens": None,
        }
        defaults.update(overrides)
        mock = MagicMock()
        for k, v in defaults.items():
            setattr(mock, k, v)
        return mock

    @patch("src.config.settings.get_settings")
    def test_standard_model_returns_temperature_and_top_p(self, mock_get):
        mock_get.return_value = self._mock_settings()

        options = get_model_options()

        assert options["store"] is False
        assert options["temperature"] == 0.8
        assert options["top_p"] == 0.9
        assert "reasoning" not in options
        assert "model_id" not in options

    @patch("src.config.settings.get_settings")
    def test_reasoning_model_returns_effort(self, mock_get):
        mock_get.return_value = self._mock_settings(
            azure_openai_deployment="o3-mini",
            agent_reasoning_effort="high",
        )

        options = get_model_options()

        assert options["store"] is False
        assert options["reasoning"] == {"effort": "high"}
        assert "temperature" not in options
        assert "top_p" not in options

    @patch("src.config.settings.get_settings")
    def test_gpt5_is_reasoning_model(self, mock_get):
        mock_get.return_value = self._mock_settings(
            azure_openai_deployment="gpt-5",
            agent_reasoning_effort="low",
        )

        options = get_model_options()

        assert options["reasoning"] == {"effort": "low"}
        assert "temperature" not in options

    @patch("src.config.settings.get_settings")
    def test_max_tokens_included_when_set(self, mock_get):
        mock_get.return_value = self._mock_settings(agent_max_tokens=4096)

        options = get_model_options()

        assert options["max_output_tokens"] == 4096

    @patch("src.config.settings.get_settings")
    def test_max_tokens_excluded_when_none(self, mock_get):
        mock_get.return_value = self._mock_settings(agent_max_tokens=None)

        options = get_model_options()

        assert "max_output_tokens" not in options

    @patch("src.config.settings.get_settings")
    def test_store_always_false(self, mock_get):
        mock_get.return_value = self._mock_settings()
        assert get_model_options()["store"] is False

        mock_get.return_value = self._mock_settings(azure_openai_deployment="o1")
        assert get_model_options()["store"] is False


class TestPerAgentDeploymentOverride:
    """Tests for per-agent deployment override via get_model_options(deployment)."""

    def _mock_settings(self, **overrides):
        defaults = {
            "azure_openai_deployment": "gpt-4.1-mini",
            "agent_temperature": 0.8,
            "agent_top_p": 0.9,
            "agent_reasoning_effort": "high",
            "agent_max_tokens": None,
        }
        defaults.update(overrides)
        mock = MagicMock()
        for k, v in defaults.items():
            setattr(mock, k, v)
        return mock

    @patch("src.config.settings.get_settings")
    def test_none_deployment_uses_default(self, mock_get):
        """When deployment is None, use the default and no model_id override."""
        mock_get.return_value = self._mock_settings()

        options = get_model_options(None)

        assert "model_id" not in options
        assert options["temperature"] == 0.8

    @patch("src.config.settings.get_settings")
    def test_same_deployment_as_default_no_model_id(self, mock_get):
        """When deployment matches default, no model_id override needed."""
        mock_get.return_value = self._mock_settings()

        options = get_model_options("gpt-4.1-mini")

        assert "model_id" not in options
        assert options["temperature"] == 0.8

    @patch("src.config.settings.get_settings")
    def test_different_standard_deployment_sets_model_id(self, mock_get):
        """When deployment differs from default, model_id is set."""
        mock_get.return_value = self._mock_settings()

        options = get_model_options("gpt-4.1")

        assert options["model_id"] == "gpt-4.1"
        assert options["temperature"] == 0.8
        assert "reasoning" not in options

    @patch("src.config.settings.get_settings")
    def test_reasoning_deployment_override(self, mock_get):
        """Orchestrator on gpt-5 while default is gpt-4.1-mini."""
        mock_get.return_value = self._mock_settings()

        options = get_model_options("gpt-5")

        assert options["model_id"] == "gpt-5"
        assert options["reasoning"] == {"effort": "high"}
        assert "temperature" not in options
        assert "top_p" not in options

    @patch("src.config.settings.get_settings")
    def test_standard_override_when_default_is_reasoning(self, mock_get):
        """Sub-agent on gpt-4.1 while default is o3."""
        mock_get.return_value = self._mock_settings(azure_openai_deployment="o3")

        options = get_model_options("gpt-4.1")

        assert options["model_id"] == "gpt-4.1"
        assert options["temperature"] == 0.8
        assert options["top_p"] == 0.9
        assert "reasoning" not in options

    @patch("src.config.settings.get_settings")
    def test_fallback_when_default_is_reasoning_and_no_override(self, mock_get):
        """All agents use reasoning when default is o3 and no override."""
        mock_get.return_value = self._mock_settings(azure_openai_deployment="o3")

        options = get_model_options(None)

        assert "model_id" not in options
        assert options["reasoning"] == {"effort": "high"}
        assert "temperature" not in options


class TestActiveDeploymentOverride:
    """Tests for runtime active deployment override."""

    def _mock_settings(self, **overrides):
        defaults = {
            "azure_openai_deployment": "gpt-4.1-mini",
            "agent_temperature": 0.8,
            "agent_top_p": 0.9,
            "agent_reasoning_effort": "medium",
            "agent_max_tokens": None,
        }
        defaults.update(overrides)
        mock = MagicMock()
        for k, v in defaults.items():
            setattr(mock, k, v)
        return mock

    @patch("src.config.settings.get_settings")
    def test_get_active_deployment_falls_back_to_env_default(self, mock_get):
        mock_get.return_value = self._mock_settings(azure_openai_deployment="gpt-4.1")

        assert get_active_deployment() == "gpt-4.1"

    @patch("src.config.settings.get_settings")
    def test_set_active_deployment_overrides_default(self, mock_get):
        mock_get.return_value = self._mock_settings(azure_openai_deployment="gpt-4.1")
        set_active_deployment("gpt-4.1")

        assert get_active_deployment() == "gpt-4.1"

    @patch("src.config.settings.get_settings")
    def test_get_model_options_uses_active_deployment(self, mock_get):
        mock_get.return_value = self._mock_settings(azure_openai_deployment="gpt-4.1")
        set_active_deployment("o3-mini")

        options = get_model_options()

        assert "model_id" not in options
        assert options["reasoning"] == {"effort": "medium"}
        assert "temperature" not in options

    @patch("src.config.settings.get_settings")
    def test_runtime_override_ignores_per_agent_deployment(self, mock_get):
        mock_get.return_value = self._mock_settings(azure_openai_deployment="gpt-4.1")
        set_active_deployment("gpt-4.1")

        options = get_model_options("gpt-4.1")

        assert "model_id" not in options
        assert options["temperature"] == 0.8
        assert options["top_p"] == 0.9


class TestRuntimeModelAllowlist:
    """Tests for runtime model selection allowlist helpers."""

    def test_available_runtime_models_matches_expected_values(self):
        assert get_available_runtime_models() == list(AVAILABLE_RUNTIME_MODELS)
        assert get_available_runtime_models() == ["gpt-4.1-mini", "gpt-4.1"]

    def test_is_supported_runtime_model(self):
        assert is_supported_runtime_model("gpt-4.1-mini") is True
        assert is_supported_runtime_model("gpt-4.1") is True
        assert is_supported_runtime_model("gpt-5-mini") is False
        assert is_supported_runtime_model("gpt-5") is False
