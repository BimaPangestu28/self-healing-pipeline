import logging
from typing import Any
from urllib.parse import quote

import httpx

from src.clients.kube_tools_api import KubeToolsClient, _get_tools_api_key
from src.config.settings import get_settings

logger = logging.getLogger(__name__)


class NonKubeToolsClient(KubeToolsClient):
    """HTTP client for non-kube tools API endpoints."""

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an HTTP request to the non-kube tools API."""
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
                    "NonKubeTools %s %s -> %s: %s",
                    method,
                    path,
                    response.status_code,
                    data,
                )
                return data
        except httpx.ConnectError:
            logger.error("NonKubeTools %s %s -> connection failed: %s", method, path, url)
            raise
        except httpx.HTTPStatusError as exc:
            logger.error(
                "NonKubeTools %s %s -> %s: %s",
                method,
                path,
                exc.response.status_code,
                exc.response.text,
            )
            raise

    async def search_elk(
        self, indices: str, q: str, size: int = 5, time_range: str = "5m"
    ) -> dict:
        """Search documents in Elasticsearch."""
        return await self._request(
            "GET",
            "/elk/search",
            params={
                "indices": indices,
                "q": q,
                "size": size,
                "time_range": time_range,
            },
        )

    async def list_elk_indices(self) -> dict:
        """List available Elasticsearch indices."""
        return await self._request("GET", "/elk/indices")

    async def get_elk_document(self, index: str, document_id: str) -> dict:
        """Fetch a single Elasticsearch document by index and document ID."""
        encoded_index = quote(index, safe="")
        encoded_document_id = quote(document_id, safe="")
        return await self._request(
            "GET",
            f"/elk/doc/{encoded_index}/{encoded_document_id}",
        )


_settings = get_settings()
non_kube_tools_client = NonKubeToolsClient(
    base_url=_settings.non_kube_tools_base_url,
    api_key=_get_tools_api_key(),
)
