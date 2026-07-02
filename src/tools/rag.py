"""RAG tools for error severity lookup."""

from __future__ import annotations

import json
from typing import Annotated, Any

from agent_framework import ai_function

from rag.query import extract_ranked_matches, query_similar_docs


def _extract_matches(result: dict[str, Any], k: int) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for item in extract_ranked_matches(result, k=k):
        matches.append(
            {
                "id": item.get("id"),
                "app": item.get("app"),
                "error": item.get("error"),
                "severity": item.get("severity"),
                "category": item.get("category"),
                "explanation": item.get("explanation"),
                "similarity": item.get("similarity"),
            }
        )
    return matches


@ai_function(
    name="rag_error_severity",
    description=(
        "Find the single most similar error message in the RAG index when its "
        "similarity is greater than 80%, and return its id, app, error text, "
        "severity, category, and explanation."
    ),
)
async def rag_error_severity(
    error_message: Annotated[str, "Error message or stack trace to classify"],
    k: Annotated[int, "Number of similar errors to return (default: 1)"] = 1,
) -> str:
    result = query_similar_docs(
        text=error_message,
        k=1 if k < 1 else min(k, 1),
        key="error",
        select="id, app, error, severity, category, explanation",
    )
    matches = _extract_matches(result, 1)
    payload = {"matches": matches}
    return json.dumps(payload, ensure_ascii=False, indent=2)


rag_tools = [
    rag_error_severity,
]
