"""Launch the approval-driven self-healing demo server.

    export PYTHONPATH=$PWD
    .venv/bin/python run_demo.py
    # open http://127.0.0.1:8080
"""

from __future__ import annotations

import uvicorn


def main() -> None:
    """Run the demo FastAPI app."""
    uvicorn.run("demo.app:app", host="127.0.0.1", port=8080, reload=False)


if __name__ == "__main__":
    main()
