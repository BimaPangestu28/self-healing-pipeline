import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from openai import AzureOpenAI


def _load_env() -> None:
    """Load .env from repo root so this script works from any cwd."""
    repo_root = Path(__file__).resolve().parents[1]
    load_dotenv(repo_root / ".env")


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _fetch_active_embedding_model() -> str | None:
    _load_env()
    base_url = os.getenv("NON_KUBE_TOOLS_BASE_URL", "").strip()
    if not base_url:
        return None

    headers = {"accept": "application/json"}
    token = os.getenv("TOOLS_API_KEY")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"{base_url.rstrip('/')}/embedding-model"
    timeout_seconds = float(os.getenv("MODEL_REGISTRY_TIMEOUT_SECONDS", "5.0"))
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError:
        return None

    if not isinstance(payload, dict):
        return None

    model_name = payload.get("model_name")
    if not model_name or not str(model_name).strip():
        return None

    return str(model_name).strip()


def _build_client() -> tuple[AzureOpenAI, str]:
    _load_env()
    endpoint = _require_env("AZURE_OPENAI_ENDPOINT")
    api_key = _require_env("AZURE_OPENAI_API_KEY")
    deployment = _fetch_active_embedding_model() or _require_env(
        "AZURE_OPENAI_EMBEDDING_MODEL_NAME"
    )
    api_version = _require_env("AZURE_OPENAI_EMBEDDING_MODEL_VERSION")
    client = AzureOpenAI(
        api_key=api_key,
        azure_endpoint=endpoint,
        api_version=api_version,
    )
    return client, deployment


def _build_search_upload_url(api_version: str | None = None) -> str:
    _load_env()
    service_name = _require_env("AZURE_AI_SEARCH_SERVICE_NAME")
    index_name = _require_env("AZURE_AI_SEARCH_INDEX_NAME")
    selected_api_version = api_version or os.getenv("AZURE_AI_SEARCH_API_VERSION", "2024-07-01")
    return (
        f"https://{service_name}.search.windows.net/"
        f"indexes/{index_name}/docs/index?api-version={selected_api_version}"
    )


def build_vector_field_name(key: str) -> str:
    """Build a stable Azure Search vector field name from a source key."""
    normalized = re.sub(r"[^0-9A-Za-z_]+", "_", key.strip()).strip("_").lower()
    if not normalized:
        raise ValueError("Embedding key must contain at least one alphanumeric character.")
    return f"vector_{normalized}"


def vectorize_json_dataset(input_path: str | Path, key: str) -> Path:
    """
    Read a JSON array dataset, embed values from `key`, add a derived vector field
    like `vector_error` per row, and write the output to `vectorized_{filename}.json`
    in the same directory.
    """
    src_path = Path(input_path).expanduser().resolve()
    if not src_path.exists():
        raise FileNotFoundError(f"Input file not found: {src_path}")

    with src_path.open("r", encoding="utf-8") as f:
        dataset: Any = json.load(f)

    if not isinstance(dataset, list):
        raise ValueError("Input JSON must be an array of objects.")

    texts: list[str] = []
    for idx, row in enumerate(dataset):
        if not isinstance(row, dict):
            raise ValueError(f"Row at index {idx} is not an object.")
        if key not in row:
            raise KeyError(f"Missing key '{key}' in row at index {idx}.")
        value = row[key]
        texts.append("" if value is None else str(value))

    client, deployment = _build_client()
    response = client.embeddings.create(input=texts, model=deployment)
    vector_field = build_vector_field_name(key)

    rows_with_vectors = []
    for item in response.data:
        row = dict(dataset[item.index])
        row[vector_field] = item.embedding
        rows_with_vectors.append(row)

    output_name = f"vectorized_{src_path.stem}.json"
    output_path = src_path.with_name(output_name)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(rows_with_vectors, f, ensure_ascii=False, indent=2)

    return output_path


def upload(
    input_path: str | Path,
    timeout_seconds: float = 60.0,
    batch_size: int = 5,
) -> dict[str, Any]:
    """
    Read a JSON array dataset, add `@search.action: upload` per row,
    wrap rows as {"value": [...]}, and post to Azure AI Search index API.
    """
    src_path = Path(input_path).expanduser().resolve()
    if not src_path.exists():
        raise FileNotFoundError(f"Input file not found: {src_path}")

    with src_path.open("r", encoding="utf-8") as f:
        dataset: Any = json.load(f)

    if not isinstance(dataset, list):
        raise ValueError("Input JSON must be an array of objects.")

    if batch_size < 1 or batch_size > 1000:
        raise ValueError("batch_size must be between 1 and 1000.")

    payload_rows: list[dict[str, Any]] = []
    for idx, row in enumerate(dataset):
        if not isinstance(row, dict):
            raise ValueError(f"Row at index {idx} is not an object.")
        payload_row = dict(row)
        if "id" in payload_row and payload_row["id"] is not None:
            payload_row["id"] = str(payload_row["id"])
        payload_row["@search.action"] = "upload"
        payload_rows.append(payload_row)

    _load_env()
    api_key = os.getenv("AZURE_SEARCH_API_KEY") or os.getenv("AZURE_AI_SEARCH_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Missing required environment variable: AZURE_SEARCH_API_KEY "
            "(or AZURE_AI_SEARCH_API_KEY)"
        )

    api_version = os.getenv("AZURE_AI_SEARCH_API_VERSION", "2024-07-01")
    url = _build_search_upload_url(api_version=api_version)
    headers = {"Content-Type": "application/json", "api-key": api_key}

    with httpx.Client(timeout=timeout_seconds) as client:
        all_results: list[Any] = []
        for start in range(0, len(payload_rows), batch_size):
            batch_docs = payload_rows[start : start + batch_size]
            payload = {"value": batch_docs}
            response = client.post(url, headers=headers, json=payload)
            if response.is_error:
                detail = response.text.strip()
                raise RuntimeError(
                    "Azure AI Search upload failed "
                    f"(status={response.status_code}, api_version={api_version}, "
                    f"batch_start={start}, batch_size={len(batch_docs)}): {detail}"
                )
            batch_result = response.json()
            if isinstance(batch_result, dict) and isinstance(batch_result.get("value"), list):
                all_results.extend(batch_result["value"])

        return {"value": all_results, "count": len(all_results), "api_version": api_version}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Embed a JSON dataset key and write vectorized output."
    )
    parser.add_argument("input_json", help="Path to input JSON dataset (array of objects)")
    parser.add_argument("key", help="JSON key to embed")
    args = parser.parse_args()

    output_path = vectorize_json_dataset(args.input_json, args.key)
    print(f"Wrote vectorized dataset: {output_path}")


if __name__ == "__main__":
    main()
