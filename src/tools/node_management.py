"""Node management tools for disk monitoring and cleanup operations."""

from typing import Annotated

from agent_framework import ai_function

from src.clients.kube_tools_api import kube_tools_client
from src.tools.utils import format_tool_result


@ai_function(
    name="get_node_temp_files",
    description=(
        "Get temporary files, disk usage, and Docker cleanup information for a node. "
        "Results limited to prevent context flooding. Read-only operation."
    ),
)
async def get_node_temp_files(
    node: Annotated[str, "Node name"],
    days: Annotated[int, "Files older than this many days (default: 30)"] = 30,
    paths: Annotated[
        str | None, "Comma-separated paths to check (default: /tmp,/var/log)"
    ] = None,
) -> str:
    """
    Get temporary files, disk usage, and Docker cleanup information for a node.

    Returns:
    - Old files list (older than specified days, limited to 100 files)
    - Disk usage info
    - Docker cleanup info:
        - Stopped containers (limited to 50)
        - Dangling images (limited to 50)
        - Unused images (limited to 50)
        - Reclaimable space

    Note: File and container lists are limited to prevent context flooding.
    """
    result = await kube_tools_client.get_node_temp_files(node, days, paths)

    # Format with proper limiting
    return format_tool_result(
        description=f"Node '{node}' temp files and disk info (files older than {days} days):",
        result=result,
        list_keys=[
            "files",
            "old_files",
            "containers",
            "images",
            "dangling_images",
            "unused_images",
        ],
        summary_fields=["disk_usage", "total_files", "total_size", "reclaimable_space"],
        max_items=100,  # Limit file lists
        max_string_length=6000,
    )


@ai_function(
    name="cleanup_node_disk",
    description=(
        "Cleanup old files and Docker resources on a node to free disk space. "
        "REQUIRES APPROVAL. WARNING: Removes ALL stopped containers and unused images."
    ),
    approval_mode="always_require",
)
async def cleanup_node_disk(
    node: Annotated[str, "Node name"],
    retention_days: Annotated[int, "Delete files older than this many days (default: 30)"] = 30,
    paths: Annotated[list[str] | None, "Paths to cleanup (default: /tmp, /var/log)"] = None,
    verify: Annotated[bool, "Verify disk usage after cleanup (default: true)"] = True,
    cleanup_docker: Annotated[bool, "Also cleanup unused Docker images (default: true)"] = True,
) -> str:
    """
    Cleanup old files and Docker resources on a node to free disk space.

    Requires explicit human approval before execution.

    WARNING: Docker cleanup removes ALL stopped containers and unused images.
    Uses `docker system prune -a -f` which removes images used by stopped containers.

    Returns:
    - Before/after disk usage
    - Deleted file count (limited to 100 files shown)
    - Docker cleanup details (limited to 50 items shown)

    Note: Lists are limited to prevent context flooding.
    """
    result = await kube_tools_client.cleanup_node_disk(
        node, retention_days, paths, verify, cleanup_docker
    )

    # Format with proper limiting
    return format_tool_result(
        description=f"Cleanup result for node '{node}':",
        result=result,
        list_keys=["deleted_files", "removed_containers", "removed_images"],
        summary_fields=["space_freed", "files_deleted", "before_disk_usage", "after_disk_usage"],
        max_items=100,
        max_string_length=6000,
    )


# Export all tools
node_management_tools = [
    get_node_temp_files,
    cleanup_node_disk,
]
