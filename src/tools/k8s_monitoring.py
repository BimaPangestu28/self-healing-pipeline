"""Kubernetes monitoring tools backed by the KubeToolsClient API surface."""

from typing import Annotated

from agent_framework import ai_function

from src.clients.kube_tools_api import kube_tools_client
from src.tools.k8s_operations import (
    get_deployment_history,
    get_rollout_status,
)
from src.tools.node_management import get_node_temp_files
from src.tools.utils import format_tool_result


def _format_monitoring_result(
    description: str,
    result: dict,
    list_keys: list[str] | None = None,
    summary_fields: list[str] | None = None,
    max_items: int = 50,
    max_string_length: int = 6000,
) -> str:
    """Format monitoring results with consistent truncation rules."""
    return format_tool_result(
        description=description,
        result=result,
        list_keys=list_keys,
        summary_fields=summary_fields,
        max_items=max_items,
        max_string_length=max_string_length,
    )


@ai_function(
    name="list_pods",
    description="List pods in a namespace. Read-only operation.",
)
async def list_pods(
    namespace: Annotated[str, "Kubernetes namespace"] = "default",
) -> str:
    """List pods in a namespace."""
    result = await kube_tools_client.list_pods(namespace)
    return _format_monitoring_result(
        description=f"Pods in namespace '{namespace}':",
        result=result,
        list_keys=["pods", "items"],
        summary_fields=["count", "total", "running", "pending", "failed"],
    )


@ai_function(
    name="get_pod_complete_status",
    description="Get complete pod status in one call. Read-only operation.",
)
async def get_pod_complete_status(
    pod: Annotated[str, "Pod name"],
    namespace: Annotated[str, "Kubernetes namespace"] = "default",
) -> str:
    """Get complete status for a pod."""
    result = await kube_tools_client.get_pod_complete_status(pod, namespace)
    return _format_monitoring_result(
        description=f"Complete status for pod '{pod}' in namespace '{namespace}':",
        result=result,
        list_keys=["containers", "events", "volumes", "conditions"],
        summary_fields=["phase", "ready", "restart_count", "node_name"],
    )


@ai_function(
    name="list_deployments",
    description="List deployments in a namespace. Read-only operation.",
)
async def list_deployments(
    namespace: Annotated[str, "Kubernetes namespace"] = "default",
) -> str:
    """List deployments in a namespace."""
    result = await kube_tools_client.list_deployments(namespace)
    return _format_monitoring_result(
        description=f"Deployments in namespace '{namespace}':",
        result=result,
        list_keys=["deployments", "items"],
        summary_fields=["count", "total", "healthy", "degraded", "unhealthy"],
    )


@ai_function(
    name="get_deployment_details",
    description=(
        "Get comprehensive deployment details including pods, metrics, events, "
        "and status. Read-only operation."
    ),
)
async def get_deployment_details(
    deployment: Annotated[str, "Deployment name"],
    namespace: Annotated[str, "Kubernetes namespace"] = "default",
    demo: Annotated[
        str | None,
        "Optional demo scenario: high, critical, medium, 1, 2, or 3",
    ] = None,
) -> str:
    """Get comprehensive deployment details."""
    result = await kube_tools_client.get_deployment_details(deployment, namespace, demo)
    return _format_monitoring_result(
        description=f"Deployment details for '{deployment}' in namespace '{namespace}':",
        result=result,
        list_keys=["pods", "events", "containers"],
        summary_fields=["replicas", "available_replicas", "ready_replicas"],
    )


@ai_function(
    name="list_namespaces",
    description="List all namespaces in the cluster. Read-only operation.",
)
async def list_namespaces() -> str:
    """List all namespaces."""
    result = await kube_tools_client.list_namespaces()
    return _format_monitoring_result(
        description="Namespaces in the cluster:",
        result=result,
        list_keys=["namespaces", "items", "list"],
        summary_fields=["count", "total", "active"],
    )


@ai_function(
    name="get_namespace_overview",
    description="Get namespace health and resource overview. Read-only operation.",
)
async def get_namespace_overview(
    namespace: Annotated[str, "Kubernetes namespace"],
) -> str:
    """Get a namespace overview."""
    result = await kube_tools_client.get_namespace_overview(namespace)
    return _format_monitoring_result(
        description=f"Overview for namespace '{namespace}':",
        result=result,
        list_keys=["pods", "deployments", "services", "events", "hpas"],
        summary_fields=["health_status", "pod_count", "deployment_count"],
    )


@ai_function(
    name="get_cluster_resources",
    description=(
        "Get comprehensive cluster resource information. "
        "Returns nodes, HPA/VPA, quotas, and summary. Read-only operation."
    ),
)
async def get_cluster_resources() -> str:
    """Get comprehensive cluster resource information."""
    result = await kube_tools_client.get_cluster_resources()
    return _format_monitoring_result(
        description="Cluster resources overview:",
        result=result,
        list_keys=["nodes", "hpas", "vpas", "quotas", "namespaces"],
        summary_fields=["total_nodes", "total_hpas", "total_vpas"],
        max_items=100,
        max_string_length=10000,
    )


@ai_function(
    name="get_logs",
    description="Get logs from a pod container. Read-only operation.",
)
async def get_logs(
    namespace: Annotated[str, "Kubernetes namespace"],
    pod: Annotated[str, "Pod name"],
    container: Annotated[str | None, "Container name"] = None,
    tail: Annotated[int, "Number of lines to return"] = 100,
) -> str:
    """Get pod logs."""
    result = await kube_tools_client.get_logs(namespace, pod, container, tail)
    return _format_monitoring_result(
        description=f"Logs for pod '{pod}' in namespace '{namespace}':",
        result=result,
        summary_fields=["pod", "namespace", "container"],
        max_string_length=8000,
    )


@ai_function(
    name="get_framework_logs",
    description="Get framework-aware logs for a deployment. Read-only operation.",
)
async def get_framework_logs(
    namespace: Annotated[str, "Kubernetes namespace"],
    deployment: Annotated[str, "Deployment name"],
    framework: Annotated[str, "Framework type"],
    pod: Annotated[str | None, "Specific pod name"] = None,
    tail: Annotated[int, "Number of lines to return"] = 100,
) -> str:
    """Get framework-aware logs."""
    result = await kube_tools_client.get_framework_logs(
        namespace, deployment, framework, pod, tail
    )
    return _format_monitoring_result(
        description=(
            f"Framework logs for deployment '{deployment}' in namespace '{namespace}':"
        ),
        result=result,
        summary_fields=["framework", "pod", "namespace", "log_path"],
        max_string_length=8000,
    )


@ai_function(
    name="describe_resource",
    description="Describe a Kubernetes resource. Read-only operation.",
)
async def describe_resource(
    namespace: Annotated[str, "Kubernetes namespace"],
    kind: Annotated[str, "Resource kind"],
    name: Annotated[str, "Resource name"],
) -> str:
    """Describe a Kubernetes resource."""
    result = await kube_tools_client.describe_resource(namespace, kind, name)
    return _format_monitoring_result(
        description=f"Description for {kind} '{name}' in namespace '{namespace}':",
        result=result,
        summary_fields=["kind", "name", "namespace"],
        max_string_length=8000,
    )


@ai_function(
    name="get_pod_health",
    description="Get pod health information. Read-only operation.",
)
async def get_pod_health(
    namespace: Annotated[str, "Kubernetes namespace"],
    pod: Annotated[str, "Pod name"],
) -> str:
    """Get pod health information."""
    result = await kube_tools_client.get_pod_health(namespace, pod)
    return _format_monitoring_result(
        description=f"Health for pod '{pod}' in namespace '{namespace}':",
        result=result,
        list_keys=["conditions", "containers"],
        summary_fields=["phase", "ready", "restart_count"],
    )


@ai_function(
    name="get_pod_metrics",
    description="Get pod CPU and memory metrics. Read-only operation.",
)
async def get_pod_metrics(
    namespace: Annotated[str, "Kubernetes namespace"],
    pod: Annotated[str, "Pod name"],
) -> str:
    """Get pod metrics."""
    result = await kube_tools_client.get_pod_metrics(namespace, pod)
    return _format_monitoring_result(
        description=f"Metrics for pod '{pod}' in namespace '{namespace}':",
        result=result,
        list_keys=["containers"],
        summary_fields=["cpu", "memory", "namespace", "pod"],
    )


@ai_function(
    name="get_pod_details",
    description="Get detailed pod information. Read-only operation.",
)
async def get_pod_details(
    namespace: Annotated[str, "Kubernetes namespace"],
    pod: Annotated[str, "Pod name"],
) -> str:
    """Get pod details."""
    result = await kube_tools_client.get_pod_details(namespace, pod)
    return _format_monitoring_result(
        description=f"Details for pod '{pod}' in namespace '{namespace}':",
        result=result,
        list_keys=["containers", "volumes", "conditions"],
        summary_fields=["phase", "node_name", "pod_ip"],
    )


@ai_function(
    name="get_events",
    description="Get namespace events, optionally filtered by resource. Read-only operation.",
)
async def get_events(
    namespace: Annotated[str, "Kubernetes namespace"],
    resource_type: Annotated[str | None, "Resource type filter"] = None,
    resource_name: Annotated[str | None, "Resource name filter"] = None,
) -> str:
    """Get namespace events."""
    result = await kube_tools_client.get_events(namespace, resource_type, resource_name)
    return _format_monitoring_result(
        description=f"Events in namespace '{namespace}':",
        result=result,
        list_keys=["events", "items"],
        summary_fields=["count", "warning_count", "normal_count"],
    )


@ai_function(
    name="list_services",
    description="List services in a namespace. Read-only operation.",
)
async def list_services(
    namespace: Annotated[str, "Kubernetes namespace"] = "default",
) -> str:
    """List services in a namespace."""
    result = await kube_tools_client.list_services(namespace)
    return _format_monitoring_result(
        description=f"Services in namespace '{namespace}':",
        result=result,
        list_keys=["services", "items"],
        summary_fields=["count", "total", "loadBalancer", "nodePort", "clusterIP"],
    )


@ai_function(
    name="list_configmaps",
    description="List configmaps in a namespace. Read-only operation.",
)
async def list_configmaps(
    namespace: Annotated[str, "Kubernetes namespace"] = "default",
) -> str:
    """List configmaps in a namespace."""
    result = await kube_tools_client.list_configmaps(namespace)
    return _format_monitoring_result(
        description=f"ConfigMaps in namespace '{namespace}':",
        result=result,
        list_keys=["configmaps", "items"],
        summary_fields=["count", "total"],
    )


@ai_function(
    name="list_secrets",
    description="List secrets in a namespace. Read-only operation.",
)
async def list_secrets(
    namespace: Annotated[str, "Kubernetes namespace"] = "default",
) -> str:
    """List secrets in a namespace."""
    result = await kube_tools_client.list_secrets(namespace)
    return _format_monitoring_result(
        description=f"Secrets in namespace '{namespace}':",
        result=result,
        list_keys=["secrets", "items"],
        summary_fields=["count", "total"],
    )


@ai_function(
    name="list_ingresses",
    description="List ingresses in a namespace. Read-only operation.",
)
async def list_ingresses(
    namespace: Annotated[str, "Kubernetes namespace"] = "default",
) -> str:
    """List ingresses in a namespace."""
    result = await kube_tools_client.list_ingresses(namespace)
    return _format_monitoring_result(
        description=f"Ingresses in namespace '{namespace}':",
        result=result,
        list_keys=["ingresses", "items"],
        summary_fields=["count", "total"],
    )


@ai_function(
    name="list_cronjobs",
    description="List cronjobs in a namespace. Read-only operation.",
)
async def list_cronjobs(
    namespace: Annotated[str, "Kubernetes namespace"] = "default",
) -> str:
    """List cronjobs in a namespace."""
    result = await kube_tools_client.list_cronjobs(namespace)
    return _format_monitoring_result(
        description=f"CronJobs in namespace '{namespace}':",
        result=result,
        list_keys=["cronjobs", "items"],
        summary_fields=["count", "total"],
    )


@ai_function(
    name="list_pvcs",
    description="List PVCs in a namespace. Read-only operation.",
)
async def list_pvcs(
    namespace: Annotated[str, "Kubernetes namespace"] = "default",
) -> str:
    """List PVCs in a namespace."""
    result = await kube_tools_client.list_pvcs(namespace)
    return _format_monitoring_result(
        description=f"PVCs in namespace '{namespace}':",
        result=result,
        list_keys=["pvcs", "items"],
        summary_fields=["count", "total"],
    )


@ai_function(
    name="list_service_accounts",
    description="List service accounts in a namespace. Read-only operation.",
)
async def list_service_accounts(
    namespace: Annotated[str, "Kubernetes namespace"] = "default",
) -> str:
    """List service accounts in a namespace."""
    result = await kube_tools_client.list_service_accounts(namespace)
    return _format_monitoring_result(
        description=f"Service accounts in namespace '{namespace}':",
        result=result,
        list_keys=["service_accounts", "items"],
        summary_fields=["count", "total"],
    )


@ai_function(
    name="get_hpa_status",
    description="Get HPA status for a namespace. Read-only operation.",
)
async def get_hpa_status(
    namespace: Annotated[str, "Kubernetes namespace"],
    name: Annotated[str | None, "HPA name"] = None,
) -> str:
    """Get HPA status."""
    result = await kube_tools_client.get_hpa_status(namespace, name)
    return _format_monitoring_result(
        description=f"HPA status in namespace '{namespace}':",
        result=result,
        list_keys=["hpas", "items"],
        summary_fields=["count", "total"],
    )


@ai_function(
    name="list_nodes",
    description="List nodes with enriched status and metrics. Read-only operation.",
)
async def list_nodes() -> str:
    """List nodes in the cluster."""
    result = await kube_tools_client.list_nodes()
    return _format_monitoring_result(
        description="Cluster nodes:",
        result=result,
        list_keys=["nodes", "items"],
        summary_fields=["count", "total_nodes", "healthyNodes", "readyNodes"],
        max_items=100,
    )


@ai_function(
    name="get_node_metrics",
    description="Get node CPU and memory metrics. Read-only operation.",
)
async def get_node_metrics() -> str:
    """Get node metrics."""
    result = await kube_tools_client.get_node_metrics()
    return _format_monitoring_result(
        description="Node metrics:",
        result=result,
        list_keys=["nodes", "items"],
        summary_fields=["count", "total"],
        max_items=100,
    )


@ai_function(
    name="get_all_nodes_disk_usage",
    description="Get disk usage for all nodes. Read-only operation.",
)
async def get_all_nodes_disk_usage() -> str:
    """Get disk usage for all nodes."""
    result = await kube_tools_client.get_all_nodes_disk_usage()
    return _format_monitoring_result(
        description="Disk usage across all nodes:",
        result=result,
        list_keys=["nodes", "items"],
        summary_fields=["count", "cluster_summary"],
        max_items=100,
    )


@ai_function(
    name="get_node_disk_usage",
    description="Get detailed disk usage for a node. Read-only operation.",
)
async def get_node_disk_usage(
    node: Annotated[str, "Node name"],
) -> str:
    """Get disk usage for a node."""
    result = await kube_tools_client.get_node_disk_usage(node)
    return _format_monitoring_result(
        description=f"Disk usage for node '{node}':",
        result=result,
        list_keys=["filesystems", "mounts"],
        summary_fields=["node", "summary"],
    )


@ai_function(
    name="get_resource_quota",
    description="Get resource quota for a namespace. Read-only operation.",
)
async def get_resource_quota(
    namespace: Annotated[str, "Kubernetes namespace"],
) -> str:
    """Get resource quota for a namespace."""
    result = await kube_tools_client.get_resource_quota(namespace)
    return _format_monitoring_result(
        description=f"Resource quota for namespace '{namespace}':",
        result=result,
        list_keys=["quotas", "items"],
        summary_fields=["count", "total"],
    )


@ai_function(
    name="list_network_policies",
    description="List network policies in a namespace. Read-only operation.",
)
async def list_network_policies(
    namespace: Annotated[str, "Kubernetes namespace"] = "default",
) -> str:
    """List network policies."""
    result = await kube_tools_client.list_network_policies(namespace)
    return _format_monitoring_result(
        description=f"Network policies in namespace '{namespace}':",
        result=result,
        list_keys=["network_policies", "items"],
        summary_fields=["count", "total"],
    )


@ai_function(
    name="list_pdbs",
    description="List Pod Disruption Budgets in a namespace. Read-only operation.",
)
async def list_pdbs(
    namespace: Annotated[str, "Kubernetes namespace"] = "default",
) -> str:
    """List Pod Disruption Budgets."""
    result = await kube_tools_client.list_pdbs(namespace)
    return _format_monitoring_result(
        description=f"Pod Disruption Budgets in namespace '{namespace}':",
        result=result,
        list_keys=["pdbs", "items"],
        summary_fields=["count", "total"],
    )


@ai_function(
    name="get_pod_security",
    description="Get pod security context details. Read-only operation.",
)
async def get_pod_security(
    namespace: Annotated[str, "Kubernetes namespace"],
    pod: Annotated[str, "Pod name"],
) -> str:
    """Get pod security details."""
    result = await kube_tools_client.get_pod_security(namespace, pod)
    return _format_monitoring_result(
        description=f"Security details for pod '{pod}' in namespace '{namespace}':",
        result=result,
        list_keys=["containers", "capabilities", "volumes"],
        summary_fields=["namespace", "pod", "service_account"],
    )


@ai_function(
    name="get_namespace_limits",
    description="Get LimitRange configuration for a namespace. Read-only operation.",
)
async def get_namespace_limits(
    namespace: Annotated[str, "Kubernetes namespace"],
) -> str:
    """Get namespace limits."""
    result = await kube_tools_client.get_namespace_limits(namespace)
    return _format_monitoring_result(
        description=f"LimitRange configuration for namespace '{namespace}':",
        result=result,
        list_keys=["limits", "items"],
        summary_fields=["count", "total"],
    )


@ai_function(
    name="list_roles",
    description="List roles in a namespace. Read-only operation.",
)
async def list_roles(
    namespace: Annotated[str, "Kubernetes namespace"] = "default",
) -> str:
    """List roles in a namespace."""
    result = await kube_tools_client.list_roles(namespace)
    return _format_monitoring_result(
        description=f"Roles in namespace '{namespace}':",
        result=result,
        list_keys=["roles", "items"],
        summary_fields=["count", "total"],
    )


@ai_function(
    name="list_rolebindings",
    description="List role bindings in a namespace. Read-only operation.",
)
async def list_rolebindings(
    namespace: Annotated[str, "Kubernetes namespace"] = "default",
) -> str:
    """List role bindings in a namespace."""
    result = await kube_tools_client.list_rolebindings(namespace)
    return _format_monitoring_result(
        description=f"Role bindings in namespace '{namespace}':",
        result=result,
        list_keys=["rolebindings", "items"],
        summary_fields=["count", "total"],
    )


@ai_function(
    name="list_cluster_roles",
    description="List cluster roles. Read-only operation.",
)
async def list_cluster_roles() -> str:
    """List cluster roles."""
    result = await kube_tools_client.list_cluster_roles()
    return _format_monitoring_result(
        description="Cluster roles:",
        result=result,
        list_keys=["cluster_roles", "items"],
        summary_fields=["count", "total"],
    )


@ai_function(
    name="list_cluster_rolebindings",
    description="List cluster role bindings. Read-only operation.",
)
async def list_cluster_rolebindings() -> str:
    """List cluster role bindings."""
    result = await kube_tools_client.list_cluster_rolebindings()
    return _format_monitoring_result(
        description="Cluster role bindings:",
        result=result,
        list_keys=["cluster_rolebindings", "items"],
        summary_fields=["count", "total"],
    )


@ai_function(
    name="list_crds",
    description="List Custom Resource Definitions. Read-only operation.",
)
async def list_crds() -> str:
    """List Custom Resource Definitions."""
    result = await kube_tools_client.list_crds()
    return _format_monitoring_result(
        description="Custom Resource Definitions:",
        result=result,
        list_keys=["crds", "items"],
        summary_fields=["count", "total"],
    )


@ai_function(
    name="check_template_hash",
    description="Check deployment pod template hash alignment. Read-only operation.",
)
async def check_template_hash(
    namespace: Annotated[str, "Kubernetes namespace"],
    deployment: Annotated[str, "Deployment name"],
) -> str:
    """Check a deployment template hash."""
    result = await kube_tools_client.check_template_hash(namespace, deployment)
    return _format_monitoring_result(
        description=(
            f"Template hash check for deployment '{deployment}' in namespace '{namespace}':"
        ),
        result=result,
        summary_fields=["matches", "deployment", "namespace"],
    )


@ai_function(
    name="list_vpas",
    description="List VerticalPodAutoscalers in a namespace. Read-only operation.",
)
async def list_vpas(
    namespace: Annotated[str, "Kubernetes namespace"] = "default",
) -> str:
    """List VPAs in a namespace."""
    result = await kube_tools_client.list_vpas(namespace)
    return _format_monitoring_result(
        description=f"VPAs in namespace '{namespace}':",
        result=result,
        list_keys=["vpas", "items"],
        summary_fields=["count", "total"],
    )


@ai_function(
    name="list_volume_snapshots",
    description="List volume snapshots in a namespace. Read-only operation.",
)
async def list_volume_snapshots(
    namespace: Annotated[str, "Kubernetes namespace"] = "default",
) -> str:
    """List volume snapshots."""
    result = await kube_tools_client.list_volume_snapshots(namespace)
    return _format_monitoring_result(
        description=f"Volume snapshots in namespace '{namespace}':",
        result=result,
        list_keys=["volume_snapshots", "items"],
        summary_fields=["count", "total"],
    )


@ai_function(
    name="check_service_mesh",
    description="Check whether a pod participates in a service mesh. Read-only operation.",
)
async def check_service_mesh(
    namespace: Annotated[str, "Kubernetes namespace"],
    pod: Annotated[str, "Pod name"],
) -> str:
    """Check service mesh membership."""
    result = await kube_tools_client.check_service_mesh(namespace, pod)
    return _format_monitoring_result(
        description=f"Service mesh details for pod '{pod}' in namespace '{namespace}':",
        result=result,
        summary_fields=["mesh_enabled", "namespace", "pod", "sidecar"],
    )


@ai_function(
    name="get_resource_contention",
    description="Get resource contention for one node or all nodes. Read-only operation.",
)
async def get_resource_contention(
    node_name: Annotated[str | None, "Node name"] = None,
) -> str:
    """Get resource contention details."""
    result = await kube_tools_client.get_resource_contention(node_name)
    target = node_name or "all nodes"
    return _format_monitoring_result(
        description=f"Resource contention for {target}:",
        result=result,
        list_keys=["nodes", "items"],
        summary_fields=["count", "high_contention", "medium_contention"],
        max_items=100,
    )


@ai_function(
    name="get_pod_network",
    description="Get network statistics for a pod. Read-only operation.",
)
async def get_pod_network(
    namespace: Annotated[str, "Kubernetes namespace"],
    pod: Annotated[str, "Pod name"],
) -> str:
    """Get pod network statistics."""
    result = await kube_tools_client.get_pod_network(namespace, pod)
    return _format_monitoring_result(
        description=f"Network statistics for pod '{pod}' in namespace '{namespace}':",
        result=result,
        summary_fields=["namespace", "pod", "ip"],
    )


@ai_function(
    name="detect_framework",
    description="Detect the application framework for a deployment. Read-only operation.",
)
async def detect_framework(
    namespace: Annotated[str, "Kubernetes namespace"],
    deployment: Annotated[str, "Deployment name"],
) -> str:
    """Detect application framework."""
    result = await kube_tools_client.detect_framework(namespace, deployment)
    return _format_monitoring_result(
        description=(
            f"Framework detection for deployment '{deployment}' in namespace '{namespace}':"
        ),
        result=result,
        list_keys=["detection_sources", "log_locations", "process_names", "config_files"],
        summary_fields=["framework", "confidence"],
    )


@ai_function(
    name="check_angular_health",
    description="Check Angular deployment health. Read-only operation.",
)
async def check_angular_health(
    namespace: Annotated[str, "Kubernetes namespace"],
    deployment: Annotated[str, "Deployment name"],
    pod: Annotated[str | None, "Specific pod name"] = None,
) -> str:
    """Check Angular deployment health."""
    result = await kube_tools_client.check_angular_health(namespace, deployment, pod)
    return _format_monitoring_result(
        description=f"Angular health for deployment '{deployment}' in namespace '{namespace}':",
        result=result,
        summary_fields=["framework", "health_status"],
    )


@ai_function(
    name="check_nodejs_health",
    description="Check Node.js deployment health. Read-only operation.",
)
async def check_nodejs_health(
    namespace: Annotated[str, "Kubernetes namespace"],
    deployment: Annotated[str, "Deployment name"],
    pod: Annotated[str | None, "Specific pod name"] = None,
) -> str:
    """Check Node.js deployment health."""
    result = await kube_tools_client.check_nodejs_health(namespace, deployment, pod)
    return _format_monitoring_result(
        description=f"Node.js health for deployment '{deployment}' in namespace '{namespace}':",
        result=result,
        summary_fields=["framework", "health_status"],
    )


@ai_function(
    name="check_nginx_health",
    description="Check Nginx deployment health. Read-only operation.",
)
async def check_nginx_health(
    namespace: Annotated[str, "Kubernetes namespace"],
    deployment: Annotated[str, "Deployment name"],
    pod: Annotated[str | None, "Specific pod name"] = None,
) -> str:
    """Check Nginx deployment health."""
    result = await kube_tools_client.check_nginx_health(namespace, deployment, pod)
    return _format_monitoring_result(
        description=f"Nginx health for deployment '{deployment}' in namespace '{namespace}':",
        result=result,
        summary_fields=["framework", "health_status"],
    )


@ai_function(
    name="check_phpfpm_health",
    description="Check PHP-FPM deployment health. Read-only operation.",
)
async def check_phpfpm_health(
    namespace: Annotated[str, "Kubernetes namespace"],
    deployment: Annotated[str, "Deployment name"],
    pod: Annotated[str | None, "Specific pod name"] = None,
) -> str:
    """Check PHP-FPM deployment health."""
    result = await kube_tools_client.check_phpfpm_health(namespace, deployment, pod)
    return _format_monitoring_result(
        description=f"PHP-FPM health for deployment '{deployment}' in namespace '{namespace}':",
        result=result,
        summary_fields=["framework", "health_status"],
    )


@ai_function(
    name="check_laravel_health",
    description="Check Laravel deployment health. Read-only operation.",
)
async def check_laravel_health(
    namespace: Annotated[str, "Kubernetes namespace"],
    deployment: Annotated[str, "Deployment name"],
    pod: Annotated[str | None, "Specific pod name"] = None,
) -> str:
    """Check Laravel deployment health."""
    result = await kube_tools_client.check_laravel_health(namespace, deployment, pod)
    return _format_monitoring_result(
        description=f"Laravel health for deployment '{deployment}' in namespace '{namespace}':",
        result=result,
        summary_fields=["framework", "health_status"],
    )


@ai_function(
    name="get_staging_overview",
    description="Get staging environment overview. Read-only operation.",
)
async def get_staging_overview() -> str:
    """Get staging environment overview."""
    result = await kube_tools_client.get_staging_overview()
    return _format_monitoring_result(
        description="Staging environment overview:",
        result=result,
        list_keys=["deployments", "namespaces", "active", "all"],
        summary_fields=["summary", "cluster_info"],
        max_items=100,
    )


@ai_function(
    name="lookup_by_domain",
    description="Look up a deployment by domain. Read-only operation.",
)
async def lookup_by_domain(
    domain: Annotated[str, "Domain or URL to search"],
) -> str:
    """Look up a deployment by domain."""
    result = await kube_tools_client.lookup_by_domain(domain)
    return _format_monitoring_result(
        description=f"Domain lookup result for '{domain}':",
        result=result,
        summary_fields=["domain", "found"],
    )


@ai_function(
    name="get_angular_metrics",
    description="Get Angular performance metrics. Read-only operation.",
)
async def get_angular_metrics(
    namespace: Annotated[str, "Kubernetes namespace"],
    deployment: Annotated[str, "Deployment name"],
    pod: Annotated[str | None, "Specific pod name"] = None,
) -> str:
    """Get Angular metrics."""
    result = await kube_tools_client.get_angular_metrics(namespace, deployment, pod)
    return _format_monitoring_result(
        description=f"Angular metrics for deployment '{deployment}' in namespace '{namespace}':",
        result=result,
        list_keys=["files", "bundles", "recommendations"],
        summary_fields=["framework", "performance_score"],
    )


@ai_function(
    name="get_nodejs_metrics",
    description="Get Node.js performance metrics. Read-only operation.",
)
async def get_nodejs_metrics(
    namespace: Annotated[str, "Kubernetes namespace"],
    deployment: Annotated[str, "Deployment name"],
    pod: Annotated[str | None, "Specific pod name"] = None,
) -> str:
    """Get Node.js metrics."""
    result = await kube_tools_client.get_nodejs_metrics(namespace, deployment, pod)
    return _format_monitoring_result(
        description=f"Node.js metrics for deployment '{deployment}' in namespace '{namespace}':",
        result=result,
        list_keys=["recommendations", "warnings"],
        summary_fields=["framework", "health", "process"],
    )


@ai_function(
    name="get_nginx_metrics",
    description="Get Nginx performance metrics. Read-only operation.",
)
async def get_nginx_metrics(
    namespace: Annotated[str, "Kubernetes namespace"],
    deployment: Annotated[str, "Deployment name"],
    pod: Annotated[str | None, "Specific pod name"] = None,
) -> str:
    """Get Nginx metrics."""
    result = await kube_tools_client.get_nginx_metrics(namespace, deployment, pod)
    return _format_monitoring_result(
        description=f"Nginx metrics for deployment '{deployment}' in namespace '{namespace}':",
        result=result,
        summary_fields=["framework", "connections", "workers"],
    )


@ai_function(
    name="get_phpfpm_metrics",
    description="Get PHP-FPM performance metrics. Read-only operation.",
)
async def get_phpfpm_metrics(
    namespace: Annotated[str, "Kubernetes namespace"],
    deployment: Annotated[str, "Deployment name"],
    pod: Annotated[str | None, "Specific pod name"] = None,
) -> str:
    """Get PHP-FPM metrics."""
    result = await kube_tools_client.get_phpfpm_metrics(namespace, deployment, pod)
    return _format_monitoring_result(
        description=f"PHP-FPM metrics for deployment '{deployment}' in namespace '{namespace}':",
        result=result,
        summary_fields=["framework", "pool", "health"],
    )


@ai_function(
    name="get_laravel_metrics",
    description="Get Laravel performance metrics. Read-only operation.",
)
async def get_laravel_metrics(
    namespace: Annotated[str, "Kubernetes namespace"],
    deployment: Annotated[str, "Deployment name"],
    pod: Annotated[str | None, "Specific pod name"] = None,
) -> str:
    """Get Laravel metrics."""
    result = await kube_tools_client.get_laravel_metrics(namespace, deployment, pod)
    return _format_monitoring_result(
        description=f"Laravel metrics for deployment '{deployment}' in namespace '{namespace}':",
        result=result,
        list_keys=["recommendations"],
        summary_fields=["framework", "health", "application"],
    )


@ai_function(
    name="get_topology",
    description="Get application topology for a namespace. Read-only operation.",
)
async def get_topology(
    namespace: Annotated[str, "Kubernetes namespace"],
) -> str:
    """Get namespace topology."""
    result = await kube_tools_client.get_topology(namespace)
    return _format_monitoring_result(
        description=f"Application topology for namespace '{namespace}':",
        result=result,
        list_keys=["nodes", "edges"],
        summary_fields=["namespace"],
        max_items=100,
    )


@ai_function(
    name="get_cluster_topology",
    description="Get cluster-wide application topology. Read-only operation.",
)
async def get_cluster_topology() -> str:
    """Get cluster-wide topology."""
    result = await kube_tools_client.get_cluster_topology()
    return _format_monitoring_result(
        description="Cluster topology:",
        result=result,
        list_keys=["nodes", "edges", "namespaces"],
        summary_fields=["cluster"],
        max_items=100,
        max_string_length=10000,
    )


@ai_function(
    name="analyze_dependencies",
    description="Analyze dependencies and restart impact for a deployment. Read-only operation.",
)
async def analyze_dependencies(
    namespace: Annotated[str, "Kubernetes namespace"],
    deployment: Annotated[str, "Deployment name"],
) -> str:
    """Analyze deployment dependencies."""
    result = await kube_tools_client.analyze_dependencies(namespace, deployment)
    return _format_monitoring_result(
        description=(
            f"Dependency analysis for deployment '{deployment}' in namespace '{namespace}':"
        ),
        result=result,
        list_keys=["dependencies", "dependents", "recommendations"],
        summary_fields=["deployment", "framework", "tier"],
    )


@ai_function(
    name="search_elasticsearch_logs",
    description="Search Kubernetes logs in Elasticsearch. Read-only operation.",
)
async def search_elasticsearch_logs(
    namespace: Annotated[str, "Kubernetes namespace"],
    deployment: Annotated[str | None, "Deployment name"] = None,
    query: Annotated[str | None, "Search query"] = None,
    time_range: Annotated[str, "Time range such as 5m, 1h, or 1d"] = "1h",
    max_results: Annotated[int, "Maximum number of log entries"] = 50,
    pod: Annotated[str | None, "Pod name"] = None,
    log_level: Annotated[str | None, "Log level filter"] = None,
) -> str:
    """Search logs in Elasticsearch."""
    result = await kube_tools_client.search_elasticsearch_logs(
        namespace=namespace,
        deployment=deployment,
        query=query,
        time_range=time_range,
        max_results=max_results,
        pod=pod,
        log_level=log_level,
    )
    return _format_monitoring_result(
        description=f"Elasticsearch log search results for namespace '{namespace}':",
        result=result,
        list_keys=["logs", "hits"],
        summary_fields=["total", "time_range", "source"],
        max_items=max_results,
        max_string_length=10000,
    )


@ai_function(
    name="get_framework_errors",
    description="Get framework-specific errors from Elasticsearch. Read-only operation.",
)
async def get_framework_errors(
    namespace: Annotated[str, "Kubernetes namespace"],
    deployment: Annotated[str, "Deployment name"],
    framework: Annotated[str, "Framework type"],
    time_range: Annotated[str, "Time range such as 5m, 1h, or 1d"] = "5m",
    max_results: Annotated[int, "Maximum number of errors"] = 50,
) -> str:
    """Get framework-specific errors."""
    result = await kube_tools_client.get_framework_errors(
        namespace, deployment, framework, time_range, max_results
    )
    return _format_monitoring_result(
        description=(
            f"Framework errors for deployment '{deployment}' in namespace '{namespace}':"
        ),
        result=result,
        list_keys=["logs", "errors"],
        summary_fields=["total", "framework", "error_types"],
        max_items=max_results,
        max_string_length=10000,
    )


@ai_function(
    name="get_log_statistics",
    description="Get Elasticsearch log statistics for a deployment. Read-only operation.",
)
async def get_log_statistics(
    namespace: Annotated[str, "Kubernetes namespace"],
    deployment: Annotated[str, "Deployment name"],
    time_range: Annotated[str, "Time range such as 5m, 1h, or 1d"] = "1h",
) -> str:
    """Get log statistics."""
    result = await kube_tools_client.get_log_statistics(namespace, deployment, time_range)
    return _format_monitoring_result(
        description=f"Log statistics for deployment '{deployment}' in namespace '{namespace}':",
        result=result,
        list_keys=["top_errors", "timeline"],
        summary_fields=["total_logs", "error_rate_percent", "log_levels"],
        max_items=100,
    )


@ai_function(
    name="test_elasticsearch_connection",
    description="Test Elasticsearch connectivity. Read-only operation.",
)
async def test_elasticsearch_connection() -> str:
    """Test Elasticsearch connectivity."""
    result = await kube_tools_client.test_elasticsearch_connection()
    return _format_monitoring_result(
        description="Elasticsearch connection test:",
        result=result,
        summary_fields=["connected", "cluster_name", "version", "configured_url"],
    )


k8s_monitoring_tools = [
    list_pods,
    get_pod_complete_status,
    list_deployments,
    get_deployment_details,
    list_namespaces,
    get_namespace_overview,
    get_cluster_resources,
    get_rollout_status,
    get_deployment_history,
    get_logs,
    get_framework_logs,
    describe_resource,
    get_pod_health,
    get_pod_metrics,
    get_pod_details,
    get_events,
    list_services,
    list_configmaps,
    list_secrets,
    list_ingresses,
    list_cronjobs,
    list_pvcs,
    list_service_accounts,
    get_hpa_status,
    list_nodes,
    get_node_metrics,
    get_all_nodes_disk_usage,
    get_node_disk_usage,
    get_resource_quota,
    list_network_policies,
    list_pdbs,
    get_pod_security,
    get_namespace_limits,
    list_roles,
    list_rolebindings,
    list_cluster_roles,
    list_cluster_rolebindings,
    list_crds,
    check_template_hash,
    list_vpas,
    list_volume_snapshots,
    check_service_mesh,
    get_resource_contention,
    get_pod_network,
    get_node_temp_files,
    detect_framework,
    check_angular_health,
    check_nodejs_health,
    check_nginx_health,
    check_phpfpm_health,
    check_laravel_health,
    get_staging_overview,
    lookup_by_domain,
    get_angular_metrics,
    get_nodejs_metrics,
    get_nginx_metrics,
    get_phpfpm_metrics,
    get_laravel_metrics,
    get_topology,
    get_cluster_topology,
    analyze_dependencies,
    search_elasticsearch_logs,
    get_framework_errors,
    get_log_statistics,
    test_elasticsearch_connection,
]
