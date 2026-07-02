"""Kubernetes operations tools for scaling, restarting, and managing deployments."""

from typing import Annotated

from agent_framework import ai_function

from src.clients.kube_tools_api import kube_tools_client
from src.tools.utils import format_tool_result, truncate_string


# ==================== Write Operations (Approval Required) ====================


@ai_function(
    name="scale_deployment",
    description="Scale a deployment to specified number of replicas. REQUIRES APPROVAL.",
    approval_mode="always_require",
)
async def scale_deployment(
    namespace: Annotated[str, "Kubernetes namespace"],
    name: Annotated[str, "Deployment name"],
    replicas: Annotated[int, "Number of replicas to scale to"],
) -> str:
    """
    Scale a deployment to specified number of replicas.
    Requires explicit human approval before execution.
    """
    result = await kube_tools_client.scale_deployment(namespace, name, replicas)
    return (
        f"Scaled deployment '{name}' in namespace '{namespace}' to {replicas} replicas. "
        f"Result: {result}"
    )


@ai_function(
    name="restart_deployment",
    description="Restart a deployment by setting restartedAt annotation. REQUIRES APPROVAL.",
    approval_mode="always_require",
)
async def restart_deployment(
    namespace: Annotated[str, "Kubernetes namespace"],
    name: Annotated[str, "Deployment name"],
) -> str:
    """
    Restart a deployment by setting restartedAt annotation.
    Requires explicit human approval before execution.
    """
    result = await kube_tools_client.restart_deployment(namespace, name)
    return f"Restarted deployment '{name}' in namespace '{namespace}'. Result: {result}"


@ai_function(
    name="exec_command",
    description=(
        "Execute command in a pod. Output limited to prevent context flooding. REQUIRES APPROVAL."
    ),
    approval_mode="always_require",
)
async def exec_command(
    namespace: Annotated[str, "Kubernetes namespace"],
    pod: Annotated[str, "Pod name"],
    command: Annotated[str, "Command to execute as string"],
) -> str:
    """
    Execute command in a pod.
    Requires explicit human approval before execution.

    Note: Command output is limited to 5000 characters to prevent context flooding.
    """
    result = await kube_tools_client.exec_command(namespace, pod, command)

    # Handle different result formats
    if isinstance(result, dict):
        # Format with proper limiting if it's a dict
        return format_tool_result(
            description=f"Executed command '{command}' in pod '{pod}' (namespace: {namespace}):",
            result=result,
            list_keys=["stdout_lines", "stderr_lines"],
            summary_fields=["exit_code", "status"],
            max_items=200,  # Limit output lines
            max_string_length=5000,
        )
    else:
        # If it's a string, truncate it
        result_str = str(result)
        truncated = truncate_string(result_str, 5000)
        return (
            f"Executed command '{command}' in pod '{pod}' (namespace: {namespace}). "
            f"Result: {truncated}"
        )


@ai_function(
    name="update_deployment_image",
    description="Update deployment container image and trigger rollout. REQUIRES APPROVAL.",
    approval_mode="always_require",
)
async def update_deployment_image(
    deployment: Annotated[str, "Deployment name"],
    namespace: Annotated[str, "Kubernetes namespace"],
    image: Annotated[str, "New container image (e.g., nginx:1.21.0)"],
    container: Annotated[str | None, "Container name (optional, uses first container if not specified)"] = None,
) -> str:
    """
    Update deployment container image and trigger rollout.
    Requires explicit human approval before execution.
    """
    result = await kube_tools_client.update_deployment_image(
        deployment, namespace, image, container
    )
    return (
        f"Updated deployment '{deployment}' image to '{image}'. "
        f"Result: {result}"
    )


@ai_function(
    name="rollback_deployment",
    description="Rollback deployment to previous or specific revision. REQUIRES APPROVAL.",
    approval_mode="always_require",
)
async def rollback_deployment(
    deployment: Annotated[str, "Deployment name"],
    namespace: Annotated[str, "Kubernetes namespace"],
    revision: Annotated[int | None, "Revision number (optional, defaults to previous)"] = None,
) -> str:
    """
    Rollback deployment to previous or specific revision.
    Requires explicit human approval before execution.
    """
    result = await kube_tools_client.rollback_deployment(deployment, namespace, revision)
    rev_info = f"revision {revision}" if revision else "previous revision"
    return f"Rolled back deployment '{deployment}' to {rev_info}. Result: {result}"


# ==================== Read Operations (No Approval Required) ====================


@ai_function(
    name="get_rollout_status",
    description="Get deployment rollout status. Read-only operation.",
)
async def get_rollout_status(
    deployment: Annotated[str, "Deployment name"],
    namespace: Annotated[str, "Kubernetes namespace"],
) -> str:
    """Get deployment rollout status."""
    result = await kube_tools_client.get_rollout_status(deployment, namespace)
    return f"Rollout status for deployment '{deployment}' in namespace '{namespace}': {result}"


@ai_function(
    name="get_deployment_history",
    description=(
        "Get deployment rollout history. Results limited to prevent context flooding. "
        "Read-only operation."
    ),
)
async def get_deployment_history(
    deployment: Annotated[str, "Deployment name"],
    namespace: Annotated[str, "Kubernetes namespace"],
) -> str:
    """
    Get deployment rollout history.

    Note: History is limited to 50 revisions to prevent context flooding.
    """
    result = await kube_tools_client.get_deployment_history(deployment, namespace)

    # Format with proper limiting
    return format_tool_result(
        description=f"Deployment history for '{deployment}' in namespace '{namespace}':",
        result=result,
        list_keys=["revisions", "history"],
        summary_fields=["current_revision", "total_revisions"],
        max_items=50,  # Limit history entries
        max_string_length=5000,
    )


# Export all tools
k8s_operations_tools = [
    scale_deployment,
    restart_deployment,
    exec_command,
    update_deployment_image,
    rollback_deployment,
    get_rollout_status,
    get_deployment_history,
]
