"""Demo use cases beyond a single memory-restart.

Each scenario induces a real fault on the target deployment, detects it, and (for
remediation scenarios) fixes it on the real cluster — returning before/after cards.
Diagnostics scenarios only inspect and report.

Scenarios reuse the same ``memory-app`` deployment; each resets the relevant aspect
so they can be run in any order.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable

from src.approvals.cards import build_incident_card, build_scenario_result_card
from src.approvals.service import DemoService
from src.self_healing.config import PipelineConfig
from src.self_healing.kube import KubeClient

logger = logging.getLogger(__name__)

_DRIFT_IMAGE = "self-healing-memory-app:v9.9.9-drift"  # not present -> ImagePull error


@dataclass(frozen=True)
class Scenario:
    """A demo use case shown in the sidebar."""

    id: str
    title: str
    category: str  # "Remediation" | "Diagnostics"
    description: str


SCENARIOS: list[Scenario] = [
    Scenario("high_memory", "High memory usage", "Remediation",
             "Pod memory crosses the threshold → restart to reclaim it."),
    Scenario("image_drift", "Image drift", "Remediation",
             "Deployment drifts to an off-policy image tag → reset to known-good."),
    Scenario("scaled_to_zero", "Service outage (0 replicas)", "Remediation",
             "Deployment scaled to zero (no endpoints) → scale back up."),
    Scenario("capacity_report", "Capacity report", "Diagnostics",
             "Read-only: replicas, readiness, and live memory from the cluster."),
]


def list_scenarios() -> list[dict]:
    """Return scenarios as plain dicts for the API/UI."""
    return [
        {"id": s.id, "title": s.title, "category": s.category, "description": s.description}
        for s in SCENARIOS
    ]


def _host(kube: KubeClient, config: PipelineConfig) -> tuple[str, str | None]:
    identity = kube.pod_identity(config.deployment)
    return identity.get("node") or config.namespace, identity.get("pod")


def run_scenario(scenario_id: str, kube: KubeClient, config: PipelineConfig, service: DemoService) -> dict:
    """Run a scenario by id and return {cards, note}."""
    handler = _HANDLERS.get(scenario_id)
    if handler is None:
        return {"cards": [], "note": f"Unknown scenario: {scenario_id}"}
    logger.info("scenario: running '%s'", scenario_id)
    return handler(kube, config, service)


# --- Remediation: high memory (reuses the approval service) ----------------


def _run_high_memory(kube: KubeClient, config: PipelineConfig, service: DemoService) -> dict:
    from demo.app import _analysis_text  # local import to avoid cycles
    from src.approvals.cards import build_healthcheck_card, build_result_card

    result = service.autonomous_remediate()
    before = result["before"]
    cards = [build_healthcheck_card(before, _analysis_text(before))]
    if result["acted"]:
        cards.append(build_result_card(result["request"]))
    return {"cards": cards, "note": "Autonomous: high memory → rollout restart → verified."}


# --- Remediation: image drift ----------------------------------------------


def _run_image_drift(kube: KubeClient, config: PipelineConfig, service: DemoService) -> dict:
    kube.set_deployment_image(config.deployment, config.container, _DRIFT_IMAGE)  # induce
    drifted = kube.get_deployment_image(config.deployment, config.container)
    host, pod = _host(kube, config)
    cards = [
        build_incident_card(
            title="Deployment image check", application=config.deployment, host=host, pod=pod,
            healthy=False,
            services=[("Image tag", False, f"Drifted to {drifted} (off-policy)"),
                      ("Rollout", False, "New pods cannot pull the image")],
            analysis=(f"Root Cause: image drifted to {drifted}, which is not a known-good tag.\n"
                      f"Recommendation: reset the deployment image to {config.good_image}."),
        )
    ]
    started = time.time()
    kube.set_deployment_image(config.deployment, config.container, config.good_image)  # remediate
    ok = kube.wait_rollout(config.deployment, timeout=config.rollout_timeout_seconds)
    cards.append(
        build_scenario_result_card(
            title="✅ Image drift remediated" if ok else "❌ Remediation failed",
            healthy=ok, action=f"set image → {config.good_image}", tool="kubernetes",
            duration_seconds=round(time.time() - started, 3), host=host,
            services=[("Image tag", ok, f"Reset to {config.good_image}"),
                      ("Rollout", ok, "Completed" if ok else "Timed out")],
        )
    )
    return {"cards": cards, "note": "Autonomous: image drift → reset to known-good → verified."}


# --- Remediation: scaled to zero -------------------------------------------


def _run_scaled_to_zero(kube: KubeClient, config: PipelineConfig, service: DemoService) -> dict:
    kube.scale_deployment(config.deployment, 0)  # induce outage
    kube.wait_rollout(config.deployment, timeout=30)
    available = kube.available_replicas(config.deployment)
    endpoints = kube.ready_endpoint_count(config.service)
    host, pod = _host(kube, config)
    cards = [
        build_incident_card(
            title="Availability check", application=config.deployment, host=host, pod=pod,
            healthy=False,
            services=[("Replicas", False, f"available={available} (scaled to 0)"),
                      ("Endpoints", False, f"{endpoints} ready — service has no backends")],
            analysis=("Root Cause: the deployment has 0 available replicas — a full outage.\n"
                      "Recommendation: scale the deployment back up to restore service."),
        )
    ]
    started = time.time()
    kube.scale_deployment(config.deployment, 1)  # remediate
    ok = kube.wait_rollout(config.deployment, timeout=config.rollout_timeout_seconds)
    available = kube.available_replicas(config.deployment)
    endpoints = kube.ready_endpoint_count(config.service)
    cards.append(
        build_scenario_result_card(
            title="✅ Service restored" if ok else "❌ Remediation failed",
            healthy=ok, action="scale deployment → 1", tool="kubernetes",
            duration_seconds=round(time.time() - started, 3), host=host,
            services=[("Replicas", ok, f"available={available}"),
                      ("Endpoints", ok, f"{endpoints} ready")],
        )
    )
    return {"cards": cards, "note": "Autonomous: 0 replicas (outage) → scale up → verified."}


# --- Diagnostics: capacity report (read-only) ------------------------------


def _run_capacity_report(kube: KubeClient, config: PipelineConfig, service: DemoService) -> dict:
    available = kube.available_replicas(config.deployment)
    desired = kube.desired_replicas(config.deployment)
    endpoints = kube.ready_endpoint_count(config.service)
    memory = kube.pod_memory_percent(config.deployment)
    host, pod = _host(kube, config)
    healthy = available >= 1 and endpoints >= 1
    card = build_incident_card(
        title="Capacity & health report", application=config.deployment, host=host, pod=pod,
        healthy=healthy,
        services=[("Replicas", available >= 1, f"available={available}/{desired}"),
                  ("Endpoints", endpoints >= 1, f"{endpoints} ready"),
                  ("Memory", (memory or 0) < 80, f"{memory}% of limit" if memory is not None else "n/a")],
        analysis="Read-only diagnostics — no action taken.",
    )
    return {"cards": [card], "note": "Diagnostics: read-only capacity/health report (no change)."}


_HANDLERS: dict[str, Callable[[KubeClient, PipelineConfig, DemoService], dict]] = {
    "high_memory": _run_high_memory,
    "image_drift": _run_image_drift,
    "scaled_to_zero": _run_scaled_to_zero,
    "capacity_report": _run_capacity_report,
}
