import argparse
import json
import os
from typing import Any

import httpx

try:
    from .embed import _build_client, _load_env, _require_env, build_vector_field_name
except ImportError:  # pragma: no cover - supports running as a script
    from embed import _build_client, _load_env, _require_env, build_vector_field_name

DEFAULT_MIN_SIMILARITY = 0.8

def _build_search_query_url(api_version: str | None = None) -> str:
    _load_env()
    service_name = _require_env("AZURE_AI_SEARCH_SERVICE_NAME")
    index_name = _require_env("AZURE_AI_SEARCH_INDEX_NAME")
    selected_api_version = api_version or os.getenv("AZURE_AI_SEARCH_API_VERSION", "2024-07-01")
    return (
        f"https://{service_name}.search.windows.net/"
        f"indexes/{index_name}/docs/search?api-version={selected_api_version}"
    )


def _extract_similarity_score(item: dict[str, Any]) -> float | None:
    for key in ("similarity", "@search.score", "score"):
        value = item.get(key)
        if isinstance(value, int | float):
            return float(value)
    return None


def extract_ranked_matches(
    result: dict[str, Any],
    k: int = 1,
    min_similarity: float | None = DEFAULT_MIN_SIMILARITY,
) -> list[dict[str, Any]]:
    values = result.get("value")
    if not isinstance(values, list):
        return []

    matches: list[dict[str, Any]] = []
    for item in values:
        if not isinstance(item, dict):
            continue
        similarity = _extract_similarity_score(item)
        if similarity is None:
            continue
        if min_similarity is not None and similarity <= min_similarity:
            continue
        matches.append({**item, "similarity": similarity})
        if len(matches) >= k:
            break
    return matches


def query_similar_docs(
    text: str,
    k: int = 1,
    vector_field: str | None = None,
    key: str | None = "error",
    select: str | None = "id, app, error, severity, category, explanation",
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    resolved_vector_field = vector_field or build_vector_field_name(key or "")
    client, deployment = _build_client()
    embedding_response = client.embeddings.create(input=[text], model=deployment)
    embedding = embedding_response.data[0].embedding

    _load_env()
    api_key = os.getenv("AZURE_SEARCH_API_KEY") or os.getenv("AZURE_AI_SEARCH_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Missing required environment variable: AZURE_SEARCH_API_KEY "
            "(or AZURE_AI_SEARCH_API_KEY)"
        )

    url = _build_search_query_url()
    headers = {"Content-Type": "application/json", "api-key": api_key}
   
    payload: dict[str, Any] = {
        "search": "*",
        "vectorQueries": [
            {
                "kind": "vector",
                "vector": embedding,
                "fields": resolved_vector_field,
                "k": k,
            }
        ],
        "top": k,
    }
    if select:
        payload["select"] = select

    with httpx.Client(timeout=timeout_seconds) as http_client:
        response = http_client.post(url, headers=headers, json=payload)
        if response.is_error:
            detail = response.text.strip()
            raise RuntimeError(
                "Azure AI Search query failed "
                f"(status={response.status_code}, k={k}, vector_field={resolved_vector_field}): {detail}"
            )
        return response.json()


def main() -> None:
    parser = argparse.ArgumentParser(description="Query Azure AI Search for similar documents.")
    parser.add_argument("text", help="Input text to embed and search")
    parser.add_argument("--k", type=int, default=1, help="Number of similar docs to return")
    parser.add_argument(
        "--min-similarity",
        type=float,
        default=DEFAULT_MIN_SIMILARITY,
        help="Only keep matches with similarity strictly greater than this threshold.",
    )
    parser.add_argument(
        "--vector-field",
        default=None,
        help="Explicit vector field name in the search index (overrides --key)",
    )
    parser.add_argument(
        "--key",
        default="error",
        help="Source field used to build the vector field name, e.g. error -> vector_error",
    )
    parser.add_argument(
        "--select",
        default="id, app, error, severity, category, explanation",
        help="Fields to return (comma-separated). Use empty string to return all fields.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Request timeout in seconds",
    )
    args = parser.parse_args()

    select = args.select if args.select.strip() else None
    result = query_similar_docs(
        text=args.text,
        k=args.k,
        vector_field=args.vector_field,
        key=args.key,
        select=select,
        timeout_seconds=args.timeout,
    )
    filtered_result = {
        **result,
        "value": extract_ranked_matches(result, args.k, min_similarity=args.min_similarity),
    }
    print(json.dumps(filtered_result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
