"""Langfuse OpenTelemetry integration for agent observability."""

import base64
import io
import logging
import os
import sys

from agent_framework.observability import configure_otel_providers
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import SpanProcessor

from src.config.settings import get_settings

logger = logging.getLogger(__name__)


class _SuppressOutput(io.StringIO):
    """Suppress stdout/stderr output."""

    def write(self, s):
        pass

    def flush(self):
        pass


def setup_langfuse_otel() -> bool:
    """Configure Langfuse OTLP exporter for agent observability.

    Returns:
        True if OTEL was configured successfully, False otherwise.
    """
    settings = get_settings()

    if not settings.enable_otel:
        logger.info("OpenTelemetry disabled via ENABLE_OTEL; skipping setup.")
        return False

    # Force-disable noisy console exporters from agent_framework
    os.environ.setdefault("OTEL_METRICS_EXPORTER", "none")
    os.environ.setdefault("OTEL_LOGS_EXPORTER", "none")
    os.environ.setdefault("OTEL_PYTHON_LOG_LEVEL", "ERROR")
    os.environ.setdefault("OTEL_LOG_LEVEL", "ERROR")

    # Set environment attribute for Langfuse
    env_value = settings.environment
    existing_resource_attrs = os.getenv("OTEL_RESOURCE_ATTRIBUTES")
    env_attr = f"langfuse.environment={env_value}"
    dep_env_attr = f"deployment.environment={env_value}"

    if existing_resource_attrs:
        if "langfuse.environment" not in existing_resource_attrs:
            existing_resource_attrs = f"{existing_resource_attrs},{env_attr}"
        if "deployment.environment" not in existing_resource_attrs:
            existing_resource_attrs = f"{existing_resource_attrs},{dep_env_attr}"
        os.environ["OTEL_RESOURCE_ATTRIBUTES"] = existing_resource_attrs
    else:
        os.environ["OTEL_RESOURCE_ATTRIBUTES"] = f"{env_attr},{dep_env_attr}"

    # Validate Langfuse credentials
    if not all([settings.langfuse_public_key, settings.langfuse_secret_key, settings.langfuse_host]):
        logger.warning(
            "Langfuse OTEL setup skipped: missing "
            "LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, or LANGFUSE_HOST"
        )
        return False

    # Create OTLP exporter with Langfuse authentication
    auth_string = f"{settings.langfuse_public_key}:{settings.langfuse_secret_key}"
    b64_auth = base64.b64encode(auth_string.encode()).decode()
    headers = {"Authorization": f"Basic {b64_auth}"}

    try:
        otel_exporter = OTLPSpanExporter(
            endpoint=f"{settings.langfuse_host}/api/public/otel/v1/traces",
            headers=headers,
        )
    except Exception:
        logger.warning(
            "Failed to configure Langfuse OTEL exporter; observability disabled",
            exc_info=True,
        )
        return False

    # Suppress console output from agent_framework OTEL setup
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    try:
        sys.stdout = _SuppressOutput()
        sys.stderr = _SuppressOutput()
        configure_otel_providers(
            exporters=[otel_exporter],
            enable_sensitive_data=settings.otel_enable_sensitive_data,
        )
    finally:
        sys.stdout = original_stdout
        sys.stderr = original_stderr

    # Add span processor to stamp environment attributes on every span
    class _EnvironmentSpanProcessor(SpanProcessor):
        def __init__(self, env: str) -> None:
            self._env = env

        def on_start(self, span, parent_context=None):
            if span.is_recording():
                span.set_attribute("langfuse.environment", self._env)
                span.set_attribute("deployment.environment", self._env)

        def on_end(self, span):
            pass

    try:
        provider = trace.get_tracer_provider()
        if hasattr(provider, "add_span_processor"):
            provider.add_span_processor(_EnvironmentSpanProcessor(env_value))
    except Exception:
        logger.warning(
            "Failed to add environment span processor; spans may show default env",
            exc_info=True,
        )

    logger.info(f"Langfuse OTEL configured successfully (environment: {env_value})")
    return True


def get_langfuse_trace_link() -> str | None:
    """Extract trace link from current OpenTelemetry context.

    Returns:
        Langfuse trace URL if available, None otherwise.
    """
    settings = get_settings()
    current_span = trace.get_current_span()

    if current_span and current_span.get_span_context().is_valid:
        trace_id = format(current_span.get_span_context().trace_id, "032x")
        langfuse_host = settings.langfuse_host or "https://cloud.langfuse.com"
        return f"{langfuse_host}/trace/{trace_id}"

    return None
