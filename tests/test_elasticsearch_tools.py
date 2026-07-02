import pytest

from src.clients.non_kube_tools_api import NonKubeToolsClient
from src.tools.elasticsearch import (
    _extract_elk_messages,
    _normalize_elk_indices,
    _sanitize_elk_query,
)


def test_normalize_elk_indices_replaces_date_suffixes_with_wildcards():
    indices = "aka-be-obe-stg-2026.03.10, kem-be-asrama-stg-2026.03.10"

    assert _normalize_elk_indices(indices) == "aka-be-obe-stg-*,kem-be-asrama-stg-*"


def test_normalize_elk_indices_deduplicates_after_normalization():
    indices = "aka-be-obe-stg-2026.03.10,aka-be-obe-stg-*"

    assert _normalize_elk_indices(indices) == "aka-be-obe-stg-*"


def test_sanitize_elk_query_keeps_only_severity_for_multi_clause_queries():
    query = 'severity:ERROR AND kubernetes.namespace:"staging"'

    assert _sanitize_elk_query(query) == "severity:ERROR"


def test_extract_elk_messages_collects_hit_messages():
    result = {
        "total": 1,
        "hits": [
            {
                "_index": "aka-be-obe-stg-2026.03.26",
                "_id": "mG4xKJ0BIyRFmPybH7UI",
                "_source": {
                    "message": "Testing Prisma Invalid Query Error - { stack: [ null ] }",
                },
            }
        ],
    }

    messages = _extract_elk_messages(result)

    assert messages == ["Testing Prisma Invalid Query Error - { stack: [ null ] }"]


@pytest.mark.asyncio
async def test_non_kube_search_elk_adds_default_time_range():
    captured: dict[str, object] = {}

    async def fake_request(method: str, path: str, params=None, json_data=None):
        captured["method"] = method
        captured["path"] = path
        captured["params"] = params
        captured["json_data"] = json_data
        return {"ok": True}

    client = NonKubeToolsClient(base_url="http://example.com", api_key=None)
    client._request = fake_request  # type: ignore[method-assign]

    await client.search_elk("filebeat-*", "severity:ERROR")

    assert captured["method"] == "GET"
    assert captured["path"] == "/elk/search"
    assert captured["json_data"] is None
    assert captured["params"] == {
        "indices": "filebeat-*",
        "q": "severity:ERROR",
        "size": 10,
        "time_range": "5m",
    }


@pytest.mark.asyncio
async def test_non_kube_search_elk_allows_overriding_time_range():
    captured: dict[str, object] = {}

    async def fake_request(method: str, path: str, params=None, json_data=None):
        captured["params"] = params
        return {"ok": True}

    client = NonKubeToolsClient(base_url="http://example.com", api_key=None)
    client._request = fake_request  # type: ignore[method-assign]

    await client.search_elk("filebeat-*", "severity:ERROR", size=10, time_range="15m")

    assert captured["params"] == {
        "indices": "filebeat-*",
        "q": "severity:ERROR",
        "size": 10,
        "time_range": "15m",
    }
