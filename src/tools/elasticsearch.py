"""Elasticsearch tools for log search and analysis."""

from typing import Annotated, Any
import re

from agent_framework import ai_function

from src.clients.non_kube_tools_api import non_kube_tools_client
from src.tools.utils import format_tool_result


@ai_function(
    name="list_elk_indices",
    description=(
        "List available Elasticsearch indices. "
        "Use this to discover exact index names before searching or fetching documents."
    ),
)
async def list_elk_indices() -> str:
    """List available Elasticsearch indices."""
    result = await non_kube_tools_client.list_elk_indices()

    return format_tool_result(
        description="Available ELK indices:",
        result=result,
        list_keys=["indices", "items", "results"],
        summary_fields=["total", "count", "indices"],
        max_items=200,
        max_string_length=8000,
    )


@ai_function(
    name="search_elk",
    description=(
        "Smart search across Elasticsearch indices with auto-detection. "
        "Supports exact ID matching, field:value term queries, and full-text search. "
        "Applies a timestamp filter based on the time_range parameter (default: 5m). "
        "Always pass time_range explicitly when the caller specifies a different window. "
        "Returns up to 10 results by default to prevent context flooding."
    ),
)
async def search_elk(
    indices: Annotated[str, "Comma-separated index names or wildcard patterns (e.g., 'transaction-service-*', 'filebeat-*', 'transaction-service-*,auth-service-*')"],
    q: Annotated[str, "Smart query string with auto-detected type. Supports: ID prefixes for exact match (TXN-, CORR-, TRACE-, SPAN-, USER-, SESSION-), field:value syntax for term queries (e.g., 'status:failed', 'operation:transfer'), or plain text for full-text search (e.g., 'timeout error')"],
    size: Annotated[int, "Maximum number of results to return (default: 5, max: 10000)"] = 10,
    time_range: Annotated[str, "Last recent time (default: 5m)"] = "5m",
) -> str:
    """
    Smart search across Elasticsearch indices with auto-detection.

    Smart Query Detection:
    - ID Patterns (TXN-, CORR-, USER-, etc.) -> Exact match on keyword fields
    - field:value syntax -> Term query on specific field
    - Plain text -> Full-text search with relevance scoring

    Supported ID Prefixes (auto-detected for exact match):
    - TXN-      -> transactionId
    - CORR-     -> correlationId
    - TRACE-    -> traceId
    - SPAN-     -> spanId
    - USER-     -> user.userId
    - SESSION-  -> user.sessionId

    Supported indices:
    - ai-ops-api-*
    - aiops-service
    - demo-transaction-banking
    - filebeat-*
    - metricbeat-*
    - transaction-service-*
    - aka-fe-obe-stg-* 
    - aka-be-obe-stg-* 
    - kem-fe-asrama-stg-* 
    - kem-be-asrama-stg-*
    - logstash-*    

    Query examples:
    - Exact ID:      q="TXN-1763167645151-QE9FJCK"
    - Correlation:   q="CORR-1763167636425-K6W1QJJO5M"
    - User lookup:   q="USER-01642"
    - Field filter:  q="severity:error"
    - Operation:     q="operation:transfer"
    - Full-text:     q="timeout error"

    Default time filter:
    - Defaults to 5m if time_range is not provided. Pass time_range explicitly when needed (e.g. "1d", "1h").

    Note: Results are limited to prevent context flooding.
    """
    indices = _normalize_elk_indices(indices)
    q = _sanitize_elk_query(q)
    result = await non_kube_tools_client.search_elk(indices, q, size, time_range)
    extracted_messages = _extract_elk_messages(result)
    if extracted_messages:
        result = result.copy()
        if extracted_messages:
            result["messages"] = extracted_messages

    # Format with proper limiting - limit hits/results to prevent flooding
    effective_max_items = max(10, min(size, 200))
    return format_tool_result(
        description=f"ELK search results for indices '{indices}' with query '{q}':",
        result=result,
        list_keys=[
            "hits",
            "results",
            "documents",
            "messages",
        ],  # Common Elasticsearch response keys
        summary_fields=[
            "total",
            "took",
            "hits",
            "query_type",
            "searched_indices",
            "messages",
        ],
        max_items=effective_max_items,
        max_string_length=20000,  # Allow longer strings for log content
    )


def _normalize_elk_indices(indices: str) -> str:
    if not indices:
        return indices

    normalized: list[str] = []
    seen: set[str] = set()

    for raw_index in indices.split(","):
        index = raw_index.strip()
        if not index:
            continue

        # Normalize concrete daily indices to wildcard patterns so alert-driven
        # searches query the service stream rather than a single day.
        index = re.sub(r"-\d{4}\.\d{2}\.\d{2}$", "-*", index)

        if index not in seen:
            normalized.append(index)
            seen.add(index)

    return ",".join(normalized)


def _sanitize_elk_query(q: str) -> str:
    if not q:
        return q

    q = q.strip()
    if not q:
        return q

    has_severity = re.search(r"\bseverity\s*:", q, flags=re.IGNORECASE)
    has_k8s_namespace = re.search(r"\bkubernetes\.namespace\b", q, flags=re.IGNORECASE)
    has_nest_app = re.search(r"\bnest_app\b", q, flags=re.IGNORECASE)
    has_boolean = re.search(r"\s+(AND|OR)\s+", q, flags=re.IGNORECASE)

    if has_severity and (has_k8s_namespace or has_nest_app or has_boolean):
        severity_match = re.search(
            r"\bseverity\s*:\s*(\"[^\"]+\"|\S+)", q, flags=re.IGNORECASE
        )
        if severity_match:
            return severity_match.group(0).strip()

    return q


_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
def _clean_log_text(text: str) -> str:
    if not text:
        return ""
    cleaned = _ANSI_ESCAPE_RE.sub("", text)
    cleaned = cleaned.replace("\\n", "\n")
    return cleaned.strip()


def _extract_elk_messages(result: dict[str, Any]) -> list[str]:
    hits: list[dict[str, Any]] = []
    if isinstance(result.get("hits"), dict):
        hits = result.get("hits", {}).get("hits", []) or []
    elif isinstance(result.get("hits"), list):
        hits = result.get("hits", []) or []
    elif isinstance(result.get("results"), list):
        hits = result.get("results", []) or []
    elif isinstance(result.get("documents"), list):
        hits = result.get("documents", []) or []

    messages: list[str] = []
    for hit in hits:
        source = hit.get("_source") or {}
        message = source.get("message")
        if isinstance(message, str) and message.strip():
            messages.append(_clean_log_text(message))

    return messages[:50]


@ai_function(
    name="get_elk_document",
    description=(
        "Fetch a single Elasticsearch document by exact index and document ID. "
        "Use this when you already know the target document identifier."
    ),
)
async def get_elk_document(
    index: Annotated[str, "Exact Elasticsearch index name containing the document"],
    document_id: Annotated[str, "Exact Elasticsearch document ID (_id) to retrieve"],
) -> str:
    """
    Fetch a single Elasticsearch document by exact index and document ID.

    Query examples:
    - index="transaction-service-2026.03.03", document_id="TXN-1763167645151-QE9FJCK"
    - index="filebeat-2026.03.03", document_id="AVx123example"
    """
    result = await non_kube_tools_client.get_elk_document(index, document_id)

    return format_tool_result(
        description=f"ELK document from index '{index}' with ID '{document_id}':",
        result=result,
        summary_fields=["_index", "_id", "found", "result"],
        max_items=20,
        max_string_length=8000,
    )


# Export all tools
elasticsearch_tools = [
    list_elk_indices,
    search_elk,
    get_elk_document,
]
