import argparse
import json

try:
    from .embed import upload
except ImportError:  # pragma: no cover - supports running as a script
    from embed import upload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Upload a vectorized JSON dataset to Azure AI Search."
    )
    parser.add_argument("input_json", help="Path to vectorized JSON dataset")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5,
        help="Number of documents to upload per batch",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Request timeout in seconds",
    )
    args = parser.parse_args()

    result = upload(
        args.input_json,
        timeout_seconds=args.timeout,
        batch_size=args.batch_size,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
