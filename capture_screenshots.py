"""Capture dashboard screenshots from the running Streamlit app."""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent / "assets" / "figures"
OUT.mkdir(parents=True, exist_ok=True)
BASE = "http://127.0.0.1:8501"

PAGES = [
    ("overview", "app_01_overview.png", 9000),
    ("analytics", "app_02_analytics.png", 11000),
    ("alerts", "app_03_alerts.png", 8000),
    ("explorer", "app_04_explorer.png", 8000),
]


def main() -> int:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            channel="chrome", headless=True,
            args=["--disable-gpu", "--force-color-profile=srgb"],
        )
        context = browser.new_context(
            viewport={"width": 1600, "height": 1000},
            device_scale_factor=2,
            locale="en-US",
        )
        page = context.new_page()
        for name, filename, wait_ms in PAGES:
            url = f"{BASE}/?page={name}"
            print(f"capturing {url} ...", flush=True)
            page.goto(url, wait_until="load", timeout=60000)
            page.wait_for_timeout(wait_ms)
            try:
                page.get_by_text("Control Tower", exact=False).first.wait_for(timeout=15000)
            except Exception:
                pass
            page.wait_for_timeout(1500)
            target = OUT / filename
            page.screenshot(path=str(target), full_page=False)
            print(f"   saved {target} ({target.stat().st_size/1024:.0f} kB)", flush=True)
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
