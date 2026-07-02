"""CLI entry point for the self-healing pipeline against a local Kubernetes cluster.

Subcommands:
    setup    Apply the sample workload manifest (deploys the broken image on purpose).
    break    Re-introduce the bug by setting the deployment to the broken image tag.
    status   Print the current deployment image, availability, and endpoints.
    run      Execute the pipeline (detect -> classify -> fix -> validate -> report).

Example:
    uv run python run_pipeline.py setup
    uv run python run_pipeline.py run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import date

from src.notifications.adaptive_cards import build_pipeline_report_card
from src.notifications.teams import send_pipeline_report
from src.self_healing.config import PipelineConfig
from src.self_healing.kube import KubeClient, KubeError
from src.self_healing.orchestrator import SelfHealingPipeline


def _build_kube(config: PipelineConfig, context: str | None) -> KubeClient:
    """Construct a namespaced kube client for the configured workload."""
    return KubeClient(namespace=config.namespace, context=context)


def _today() -> str:
    """Return today's date as an ISO string for the report header."""
    return date.today().isoformat()


def command_setup(config: PipelineConfig, kube: KubeClient) -> int:
    """Apply the sample workload manifest to the cluster."""
    print(f"Applying manifest: {config.manifest_path}")
    kube.apply(config.manifest_path)
    print(f"Applied. Deployment '{config.deployment}' created in namespace '{config.namespace}'.")
    print("(It starts BROKEN on purpose — run 'run' to heal it.)")
    return 0


def command_break(config: PipelineConfig, kube: KubeClient) -> int:
    """Re-introduce the bug by resetting the deployment to the broken image."""
    print(f"Setting {config.deployment} image -> {config.broken_image}")
    kube.set_deployment_image(config.deployment, config.container, config.broken_image)
    print("Broken image applied. The deployment should now fail readiness.")
    return 0


def command_status(config: PipelineConfig, kube: KubeClient) -> int:
    """Print the current health of the sample workload."""
    image = kube.get_deployment_image(config.deployment, config.container)
    available = kube.available_replicas(config.deployment)
    endpoints = kube.ready_endpoint_count(config.service)
    print(f"deployment : {config.deployment}")
    print(f"image      : {image}")
    print(f"available  : {available}")
    print(f"endpoints  : {endpoints}")
    print(f"healthy    : {available >= 1 and endpoints >= 1}")
    return 0


def command_run(config: PipelineConfig, kube: KubeClient, *, deliver: bool) -> int:
    """Run the full pipeline and print / deliver the Adaptive Card report."""
    pipeline = SelfHealingPipeline(kube=kube, config=config)
    result = pipeline.run(run_date=_today())

    print("\n=== Phase log ===")
    for line in result.phase_log:
        print(f"  {line}")

    card = build_pipeline_report_card(result.report)
    print("\n=== Adaptive Card (Teams payload) ===")
    print(json.dumps(card, indent=2, ensure_ascii=False))

    if deliver:
        webhook_url = os.environ.get("TEAMS_WEBHOOK_URL")
        if webhook_url:
            delivered = asyncio.run(
                send_pipeline_report(result.report, webhook_url=webhook_url)
            )
            print(f"\nTeams delivery: {'sent' if delivered else 'failed (see logs)'}")
        else:
            print("\nTeams delivery: skipped (set TEAMS_WEBHOOK_URL to enable)")

    # Exit non-zero when the run did not end clean, so CI can gate on it.
    return 0 if result.report.status == "all_clear" else 1


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch to the selected subcommand."""
    parser = argparse.ArgumentParser(description="Self-healing pipeline for a local k8s workload.")
    parser.add_argument("command", choices=["setup", "break", "status", "run"])
    parser.add_argument("--context", default=None, help="kube context (default: current)")
    parser.add_argument("--namespace", default=None, help="override target namespace")
    parser.add_argument(
        "--no-deliver",
        action="store_true",
        help="do not attempt Teams delivery on 'run'",
    )
    args = parser.parse_args(argv)

    config = PipelineConfig()
    if args.namespace:
        config = PipelineConfig(namespace=args.namespace)
    kube = _build_kube(config, args.context)

    try:
        if args.command == "setup":
            return command_setup(config, kube)
        if args.command == "break":
            return command_break(config, kube)
        if args.command == "status":
            return command_status(config, kube)
        if args.command == "run":
            return command_run(config, kube, deliver=not args.no_deliver)
    except KubeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
