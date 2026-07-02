"""Capture screenshots of the demo UI with Playwright.

Starts the demo server, drives the full flow (Start scenario -> Approve), captures
the alert+approval and approved-result states into docs/screenshots/, then stops
the server. Requires a reachable cluster (Approve performs a real rollout restart).

    make screenshots      # or: python scripts/screenshots.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "screenshots"
URL = "http://127.0.0.1:8080"


def _wait_until_up(url: str, attempts: int = 30) -> bool:
    """Poll a URL until it responds or attempts run out."""
    for _ in range(attempts):
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except Exception:
            time.sleep(1)
    return False


def _capture() -> None:
    """Drive the UI and write the screenshots."""
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 820, "height": 1200}, device_scale_factor=2)
        page.goto(URL, wait_until="networkidle")

        page.click("#btn-start")
        page.wait_for_selector("text=Action Approval Required", timeout=30000)
        page.wait_for_timeout(1800)
        page.screenshot(path=str(OUT / "01-alert-and-approval.png"), full_page=True)
        print("wrote", OUT / "01-alert-and-approval.png")

        page.get_by_role("button", name="Approve").click()
        page.wait_for_selector("text=Completed Successfully", timeout=90000)
        page.wait_for_timeout(1500)
        page.screenshot(path=str(OUT / "02-approved-result.png"), full_page=True)
        print("wrote", OUT / "02-approved-result.png")

        browser.close()


def main() -> int:
    """Start the server, capture screenshots, and stop the server."""
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    server = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "demo.app:app",
            "--host", "127.0.0.1", "--port", "8080", "--app-dir", str(ROOT),
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        if not _wait_until_up(URL):
            print("ERROR: demo server did not come up on :8080", file=sys.stderr)
            return 1
        _capture()
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
