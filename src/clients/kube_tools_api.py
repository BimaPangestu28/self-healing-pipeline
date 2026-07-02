import logging
from typing import Any
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

from src.config.settings import get_settings


class KubeToolsClient:
    """HTTP client for kube tools API endpoints."""

    def __init__(self, base_url: str, api_key: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers: dict[str, str] = {}
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an HTTP request to the kube tools API."""
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=self.headers,
                    params=params,
                    json=json_data,
                    timeout=60.0,
                )
                response.raise_for_status()
                data = response.json()
                logger.info(
                    "KubeTools %s %s -> %s: %s",
                    method,
                    path,
                    response.status_code,
                    data,
                )
                return data
        except httpx.ConnectError:
            logger.error("KubeTools %s %s -> connection failed: %s", method, path, url)
            raise
        except httpx.HTTPStatusError as exc:
            logger.error(
                "KubeTools %s %s -> %s: %s",
                method,
                path,
                exc.response.status_code,
                exc.response.text,
            )
            raise

    @staticmethod
    def _clean_params(**params: Any) -> dict[str, Any]:
        """Drop None values so optional query params are omitted."""
        return {key: value for key, value in params.items() if value is not None}

    @staticmethod
    def _encode_path(value: str) -> str:
        """Encode dynamic path segments safely."""
        return quote(value, safe="")

    async def list_pods(self, namespace: str = "default") -> dict[str, Any]:
        """List pods in a namespace."""
        return await self._request("GET", "/k8s/pods", params={"namespace": namespace})

    async def get_pod_complete_status(
        self, pod: str, namespace: str = "default"
    ) -> dict[str, Any]:
        """Get complete pod status in a single call."""
        return await self._request(
            "GET",
            f"/k8s/pods/{self._encode_path(pod)}/complete-status",
            params={"namespace": namespace},
        )

    async def list_deployments(self, namespace: str = "default") -> dict[str, Any]:
        """List deployments in a namespace."""
        return await self._request(
            "GET", "/k8s/deployments", params={"namespace": namespace}
        )

    async def get_rollout_status(
        self, deployment: str, namespace: str
    ) -> dict[str, Any]:
        """Get deployment rollout status."""
        return await self._request(
            "GET",
            f"/k8s/deployments/{self._encode_path(deployment)}/rollout-status",
            params={"namespace": namespace},
        )

    async def get_deployment_history(
        self, deployment: str, namespace: str
    ) -> dict[str, Any]:
        """Get deployment rollout history."""
        return await self._request(
            "GET",
            f"/k8s/deployments/{self._encode_path(deployment)}/history",
            params={"namespace": namespace},
        )

    async def get_deployment_details(
        self,
        deployment: str,
        namespace: str = "default",
        demo: str | None = None,
    ) -> dict[str, Any]:
        """Get deployment details including pods, metrics, and events."""
        return await self._request(
            "GET",
            f"/k8s/deployments/{self._encode_path(deployment)}/details",
            params=self._clean_params(namespace=namespace, demo=demo),
        )

    async def list_namespaces(self) -> dict[str, Any]:
        """List namespaces in the cluster."""
        return await self._request("GET", "/k8s/namespaces")

    async def get_namespace_overview(self, namespace: str) -> dict[str, Any]:
        """Get namespace overview."""
        return await self._request(
            "GET",
            f"/k8s/namespaces/{self._encode_path(namespace)}/overview",
        )

    async def get_cluster_resources(self) -> dict[str, Any]:
        """Get cluster resource information."""
        return await self._request("GET", "/k8s/cluster/resources")

    async def restart_deployment(
        self, namespace: str, name: str, wait: bool = True
    ) -> dict[str, Any]:
        """Restart a deployment."""
        return await self._request(
            "POST",
            "/k8s/restart",
            params={"namespace": namespace, "name": name, "wait": wait},
        )

    async def get_logs(
        self,
        namespace: str,
        pod: str,
        container: str | None = None,
        tail: int = 100,
    ) -> dict[str, Any]:
        """Get pod logs."""
        return await self._request(
            "GET",
            "/k8s/logs",
            params=self._clean_params(
                namespace=namespace, pod=pod, container=container, tail=tail
            ),
        )

    async def get_framework_logs(
        self,
        namespace: str,
        deployment: str,
        framework: str,
        pod: str | None = None,
        tail: int = 100,
    ) -> dict[str, Any]:
        """Get framework-aware logs."""
        return await self._request(
            "GET",
            "/k8s/logs/framework",
            params=self._clean_params(
                namespace=namespace,
                deployment=deployment,
                framework=framework,
                pod=pod,
                tail=tail,
            ),
        )

    async def describe_resource(
        self, namespace: str, kind: str, name: str
    ) -> dict[str, Any]:
        """Describe a Kubernetes resource."""
        return await self._request(
            "GET",
            "/k8s/describe",
            params={"namespace": namespace, "kind": kind, "name": name},
        )

    async def get_pod_health(self, namespace: str, pod: str) -> dict[str, Any]:
        """Get pod health."""
        return await self._request(
            "GET",
            f"/k8s/pods/{self._encode_path(pod)}/health",
            params={"namespace": namespace},
        )

    async def get_pod_metrics(self, namespace: str, pod: str) -> dict[str, Any]:
        """Get pod metrics."""
        return await self._request(
            "GET",
            f"/k8s/pods/{self._encode_path(pod)}/metrics",
            params={"namespace": namespace},
        )

    async def get_pod_details(self, namespace: str, pod: str) -> dict[str, Any]:
        """Get pod details."""
        return await self._request(
            "GET",
            f"/k8s/pods/{self._encode_path(pod)}/details",
            params={"namespace": namespace},
        )

    async def get_events(
        self,
        namespace: str,
        resource_type: str | None = None,
        resource_name: str | None = None,
    ) -> dict[str, Any]:
        """Get namespace events, optionally filtered by resource."""
        return await self._request(
            "GET",
            "/k8s/events",
            params=self._clean_params(
                namespace=namespace,
                resource_type=resource_type,
                resource_name=resource_name,
            ),
        )

    async def list_services(self, namespace: str = "default") -> dict[str, Any]:
        """List services in a namespace."""
        return await self._request(
            "GET", "/k8s/services", params={"namespace": namespace}
        )

    async def list_configmaps(self, namespace: str = "default") -> dict[str, Any]:
        """List configmaps in a namespace."""
        return await self._request(
            "GET", "/k8s/configmaps", params={"namespace": namespace}
        )

    async def list_secrets(self, namespace: str = "default") -> dict[str, Any]:
        """List secrets in a namespace."""
        return await self._request(
            "GET", "/k8s/secrets", params={"namespace": namespace}
        )

    async def list_ingresses(self, namespace: str = "default") -> dict[str, Any]:
        """List ingresses in a namespace."""
        return await self._request(
            "GET", "/k8s/ingresses", params={"namespace": namespace}
        )

    async def list_cronjobs(self, namespace: str = "default") -> dict[str, Any]:
        """List cronjobs in a namespace."""
        return await self._request(
            "GET", "/k8s/cronjobs", params={"namespace": namespace}
        )

    async def list_pvcs(self, namespace: str = "default") -> dict[str, Any]:
        """List PVCs in a namespace."""
        return await self._request("GET", "/k8s/pvcs", params={"namespace": namespace})

    async def list_service_accounts(
        self, namespace: str = "default"
    ) -> dict[str, Any]:
        """List service accounts in a namespace."""
        return await self._request(
            "GET", "/k8s/service-accounts", params={"namespace": namespace}
        )

    async def get_hpa_status(
        self, namespace: str, name: str | None = None
    ) -> dict[str, Any]:
        """Get HPA status."""
        return await self._request(
            "GET",
            "/k8s/hpa",
            params=self._clean_params(namespace=namespace, name=name),
        )

    async def list_nodes(self) -> dict[str, Any]:
        """List nodes with enriched details."""
        return await self._request("GET", "/k8s/nodes")

    async def get_node_metrics(self) -> dict[str, Any]:
        """Get node metrics."""
        return await self._request("GET", "/k8s/nodes/metrics")

    async def get_all_nodes_disk_usage(self) -> dict[str, Any]:
        """Get disk usage for all nodes."""
        return await self._request("GET", "/k8s/nodes/disk-usage")

    async def get_node_disk_usage(self, node: str) -> dict[str, Any]:
        """Get disk usage for a specific node."""
        return await self._request(
            "GET", f"/k8s/nodes/{self._encode_path(node)}/disk-usage"
        )

    async def get_resource_quota(self, namespace: str) -> dict[str, Any]:
        """Get resource quota for a namespace."""
        return await self._request(
            "GET", "/k8s/resource-quota", params={"namespace": namespace}
        )

    async def list_network_policies(
        self, namespace: str = "default"
    ) -> dict[str, Any]:
        """List network policies."""
        return await self._request(
            "GET", "/k8s/network-policies", params={"namespace": namespace}
        )

    async def list_pdbs(self, namespace: str = "default") -> dict[str, Any]:
        """List pod disruption budgets."""
        return await self._request("GET", "/k8s/pdbs", params={"namespace": namespace})

    async def get_pod_security(self, namespace: str, pod: str) -> dict[str, Any]:
        """Get pod security details."""
        return await self._request(
            "GET",
            f"/k8s/pods/{self._encode_path(pod)}/security",
            params={"namespace": namespace},
        )

    async def get_namespace_limits(self, namespace: str) -> dict[str, Any]:
        """Get namespace LimitRange configuration."""
        return await self._request(
            "GET", "/k8s/namespace-limits", params={"namespace": namespace}
        )

    async def list_roles(self, namespace: str = "default") -> dict[str, Any]:
        """List roles in a namespace."""
        return await self._request("GET", "/k8s/roles", params={"namespace": namespace})

    async def list_rolebindings(self, namespace: str = "default") -> dict[str, Any]:
        """List rolebindings in a namespace."""
        return await self._request(
            "GET", "/k8s/rolebindings", params={"namespace": namespace}
        )

    async def list_cluster_roles(self) -> dict[str, Any]:
        """List cluster roles."""
        return await self._request("GET", "/k8s/cluster-roles")

    async def list_cluster_rolebindings(self) -> dict[str, Any]:
        """List cluster rolebindings."""
        return await self._request("GET", "/k8s/cluster-rolebindings")

    async def list_crds(self) -> dict[str, Any]:
        """List CRDs."""
        return await self._request("GET", "/k8s/crds")

    async def check_template_hash(
        self, namespace: str, deployment: str
    ) -> dict[str, Any]:
        """Check deployment template hash."""
        return await self._request(
            "GET",
            f"/k8s/deployments/{self._encode_path(deployment)}/template-hash",
            params={"namespace": namespace},
        )

    async def list_vpas(self, namespace: str = "default") -> dict[str, Any]:
        """List VPAs in a namespace."""
        return await self._request("GET", "/k8s/vpas", params={"namespace": namespace})

    async def list_volume_snapshots(
        self, namespace: str = "default"
    ) -> dict[str, Any]:
        """List volume snapshots in a namespace."""
        return await self._request(
            "GET", "/k8s/volume-snapshots", params={"namespace": namespace}
        )

    async def check_service_mesh(self, namespace: str, pod: str) -> dict[str, Any]:
        """Check whether a pod participates in a service mesh."""
        return await self._request(
            "GET",
            f"/k8s/pods/{self._encode_path(pod)}/service-mesh",
            params={"namespace": namespace},
        )

    async def get_resource_contention(
        self, node_name: str | None = None
    ) -> dict[str, Any]:
        """Get node resource contention."""
        return await self._request(
            "GET",
            "/k8s/nodes/contention",
            params=self._clean_params(node_name=node_name),
        )

    async def get_pod_network(self, namespace: str, pod: str) -> dict[str, Any]:
        """Get pod network statistics."""
        return await self._request(
            "GET",
            f"/k8s/pods/{self._encode_path(pod)}/network",
            params={"namespace": namespace},
        )

    async def get_node_temp_files(
        self,
        node: str,
        days: int = 30,
        paths: str | None = None,
    ) -> dict[str, Any]:
        """Get temp files, disk usage, and Docker cleanup information for a node."""
        params: dict[str, Any] = {"days": days}
        if paths:
            params["paths"] = paths
        return await self._request(
            "GET",
            f"/k8s/nodes/{self._encode_path(node)}/temp-files",
            params=params,
        )

    async def detect_framework(
        self, namespace: str, deployment: str
    ) -> dict[str, Any]:
        """Detect application framework for a deployment."""
        return await self._request(
            "GET",
            "/k8s/detect-framework",
            params={"namespace": namespace, "deployment": deployment},
        )

    async def check_angular_health(
        self, namespace: str, deployment: str, pod: str | None = None
    ) -> dict[str, Any]:
        """Check Angular deployment health."""
        return await self._request(
            "GET",
            "/k8s/health/angular",
            params=self._clean_params(
                namespace=namespace, deployment=deployment, pod=pod
            ),
        )

    async def check_nodejs_health(
        self, namespace: str, deployment: str, pod: str | None = None
    ) -> dict[str, Any]:
        """Check Node.js deployment health."""
        return await self._request(
            "GET",
            "/k8s/health/nodejs",
            params=self._clean_params(
                namespace=namespace, deployment=deployment, pod=pod
            ),
        )

    async def check_nginx_health(
        self, namespace: str, deployment: str, pod: str | None = None
    ) -> dict[str, Any]:
        """Check Nginx deployment health."""
        return await self._request(
            "GET",
            "/k8s/health/nginx",
            params=self._clean_params(
                namespace=namespace, deployment=deployment, pod=pod
            ),
        )

    async def check_phpfpm_health(
        self, namespace: str, deployment: str, pod: str | None = None
    ) -> dict[str, Any]:
        """Check PHP-FPM deployment health."""
        return await self._request(
            "GET",
            "/k8s/health/php-fpm",
            params=self._clean_params(
                namespace=namespace, deployment=deployment, pod=pod
            ),
        )

    async def check_laravel_health(
        self, namespace: str, deployment: str, pod: str | None = None
    ) -> dict[str, Any]:
        """Check Laravel deployment health."""
        return await self._request(
            "GET",
            "/k8s/health/laravel",
            params=self._clean_params(
                namespace=namespace, deployment=deployment, pod=pod
            ),
        )

    async def get_staging_overview(self) -> dict[str, Any]:
        """Get staging environment overview."""
        return await self._request("GET", "/k8s/staging-overview")

    async def lookup_by_domain(self, domain: str) -> dict[str, Any]:
        """Look up a deployment by domain."""
        return await self._request(
            "GET", "/k8s/lookup/domain", params={"domain": domain}
        )

    async def get_angular_metrics(
        self, namespace: str, deployment: str, pod: str | None = None
    ) -> dict[str, Any]:
        """Get Angular performance metrics."""
        return await self._request(
            "GET",
            "/k8s/metrics/angular",
            params=self._clean_params(
                namespace=namespace, deployment=deployment, pod=pod
            ),
        )

    async def get_nodejs_metrics(
        self, namespace: str, deployment: str, pod: str | None = None
    ) -> dict[str, Any]:
        """Get Node.js performance metrics."""
        return await self._request(
            "GET",
            "/k8s/metrics/nodejs",
            params=self._clean_params(
                namespace=namespace, deployment=deployment, pod=pod
            ),
        )

    async def get_nginx_metrics(
        self, namespace: str, deployment: str, pod: str | None = None
    ) -> dict[str, Any]:
        """Get Nginx performance metrics."""
        return await self._request(
            "GET",
            "/k8s/metrics/nginx",
            params=self._clean_params(
                namespace=namespace, deployment=deployment, pod=pod
            ),
        )

    async def get_phpfpm_metrics(
        self, namespace: str, deployment: str, pod: str | None = None
    ) -> dict[str, Any]:
        """Get PHP-FPM performance metrics."""
        return await self._request(
            "GET",
            "/k8s/metrics/php-fpm",
            params=self._clean_params(
                namespace=namespace, deployment=deployment, pod=pod
            ),
        )

    async def get_laravel_metrics(
        self, namespace: str, deployment: str, pod: str | None = None
    ) -> dict[str, Any]:
        """Get Laravel performance metrics."""
        return await self._request(
            "GET",
            "/k8s/metrics/laravel",
            params=self._clean_params(
                namespace=namespace, deployment=deployment, pod=pod
            ),
        )

    async def get_topology(self, namespace: str) -> dict[str, Any]:
        """Get namespace application topology."""
        return await self._request(
            "GET", "/k8s/topology", params={"namespace": namespace}
        )

    async def get_cluster_topology(self) -> dict[str, Any]:
        """Get cluster-wide topology."""
        return await self._request("GET", "/k8s/topology/cluster")

    async def analyze_dependencies(
        self, namespace: str, deployment: str
    ) -> dict[str, Any]:
        """Analyze deployment dependencies."""
        return await self._request(
            "GET",
            "/k8s/topology/analyze",
            params={"namespace": namespace, "deployment": deployment},
        )

    async def search_elasticsearch_logs(
        self,
        namespace: str,
        deployment: str | None = None,
        query: str | None = None,
        time_range: str = "1h",
        max_results: int = 50,
        pod: str | None = None,
        log_level: str | None = None,
    ) -> dict[str, Any]:
        """Search logs via Elasticsearch."""
        return await self._request(
            "POST",
            "/k8s/logs/elasticsearch",
            json_data=self._clean_params(
                namespace=namespace,
                deployment=deployment,
                pod=pod,
                query=query,
                time_range=time_range,
                max_results=max_results,
                log_level=log_level,
            ),
        )

    async def get_framework_errors(
        self,
        namespace: str,
        deployment: str,
        framework: str,
        time_range: str = "5m",
        max_results: int = 50,
    ) -> dict[str, Any]:
        """Get framework-specific errors from Elasticsearch."""
        return await self._request(
            "GET",
            "/k8s/logs/errors",
            params={
                "namespace": namespace,
                "deployment": deployment,
                "framework": framework,
                "time_range": time_range,
                "max_results": max_results,
            },
        )

    async def get_log_statistics(
        self, namespace: str, deployment: str, time_range: str = "1h"
    ) -> dict[str, Any]:
        """Get Elasticsearch log statistics."""
        return await self._request(
            "GET",
            "/k8s/logs/statistics",
            params={
                "namespace": namespace,
                "deployment": deployment,
                "time_range": time_range,
            },
        )

    async def test_elasticsearch_connection(self) -> dict[str, Any]:
        """Test Elasticsearch connectivity."""
        return await self._request("GET", "/k8s/logs/elasticsearch/test")

    async def scale_deployment(
        self, namespace: str, name: str, replicas: int, wait: bool = True
    ) -> dict[str, Any]:
        """Scale a deployment via the optional write endpoint."""
        return await self._request(
            "POST",
            "/k8s/scale",
            json_data={
                "namespace": namespace,
                "name": name,
                "replicas": replicas,
                "wait": wait,
            },
        )

    async def exec_command(
        self, namespace: str, pod: str, command: str
    ) -> dict[str, Any]:
        """Execute a command in a pod via the optional write endpoint."""
        return await self._request(
            "POST",
            "/k8s/exec",
            json_data={
                "namespace": namespace,
                "pod": pod,
                "command": command,
            },
        )

    async def update_deployment_image(
        self,
        deployment: str,
        namespace: str,
        image: str,
        container: str | None = None,
        wait: bool = True,
    ) -> dict[str, Any]:
        """Update deployment image via the optional write endpoint."""
        return await self._request(
            "POST",
            f"/k8s/deployments/{self._encode_path(deployment)}/update-image",
            json_data=self._clean_params(
                namespace=namespace,
                image=image,
                container=container,
                wait=wait,
            ),
        )

def _get_tools_api_key() -> str | None:
    """Resolve shared tools API key, with backward compatibility support."""
    settings = get_settings()
    return settings.tools_api_key or settings.kube_tools_api_key


_settings = get_settings()
kube_tools_client = KubeToolsClient(
    base_url=_settings.kube_tools_base_url,
    api_key=_get_tools_api_key(),
)
