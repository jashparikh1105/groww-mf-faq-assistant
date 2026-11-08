"""Phase 2 — Scrape ONLY the 5 configured Groww pages and save raw HTML.

Run:  python -m src.phase2_scrape
Out:  data/raw/<doc_id>.html  +  data/raw/manifest.json
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone

import requests

from src.config import get_config, path, sources


def _headers(cfg: dict) -> dict:
    return {
        "User-Agent": cfg["scraping"]["user_agent"],
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-IN,en;q=0.9",
        "Cache-Control": "no-cache",
    }


def fetch_with_requests(url: str, cfg: dict) -> tuple[int, str]:
    sc = cfg["scraping"]
    last_err = None
    for attempt in range(1, sc["retries"] + 1):
        try:
            r = requests.get(url, headers=_headers(cfg), timeout=sc["timeout_seconds"])
            return r.status_code, r.text
        except requests.RequestException as e:  # network error -> retry
            last_err = e
            print(f"   attempt {attempt} failed: {e}")
            time.sleep(2 * attempt)
    raise RuntimeError(f"requests failed for {url}: {last_err}")


def fetch_with_playwright(url: str, cfg: dict) -> tuple[int, str]:
    """Optional fallback: headless Chromium renders the page like a real browser."""
    from playwright.sync_api import sync_playwright  # imported lazily (optional dependency)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=cfg["scraping"]["user_agent"])
        resp = page.goto(url, wait_until="networkidle", timeout=cfg["scraping"]["timeout_seconds"] * 1000)
        html = page.content()
        status = resp.status if resp else 0
        browser.close()
    return status, html


def scrape() -> list[dict]:
    cfg = get_config()
    raw_dir = path("raw_dir")
    raw_dir.mkdir(parents=True, exist_ok=True)
    manifest = []

    for i, src in enumerate(sources(), 1):
        url = src["url"]
        print(f"[{i}/{len(sources())}] {src['doc_id']}  ->  {url}")
        method = "requests"
        status, html = 0, ""
        try:
            status, html = fetch_with_requests(url, cfg)
        except RuntimeError as e:
            print(f"   {e}")

        too_small = len(html.encode("utf-8")) < cfg["scraping"]["min_valid_bytes"]
        if (status != 200 or too_small) and cfg["scraping"].get("use_playwright_fallback"):
            try:
                print("   requests result not usable -> trying Playwright fallback")
                status, html = fetch_with_playwright(url, cfg)
                method = "playwright"
            except ImportError:
                print("   Playwright not installed (pip install playwright && playwright install chromium)")
            except Exception as e:  # noqa: BLE001
                print(f"   Playwright failed: {e}")

        ok = status == 200 and len(html) > 0
        out_file = raw_dir / f"{src['doc_id']}.html"
        if ok:
            out_file.write_text(html, encoding="utf-8")
        entry = {
            "doc_id": src["doc_id"],
            "url": url,
            "status": status,
            "ok": ok,
            "method": method,
            "bytes": len(html.encode("utf-8")),
            "sha256": hashlib.sha256(html.encode("utf-8")).hexdigest() if ok else None,
            "file": str(out_file.relative_to(raw_dir.parent.parent)) if ok else None,
            "scraped_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        manifest.append(entry)
        print(f"   status={status} bytes={entry['bytes']} ok={ok}")
        time.sleep(cfg["scraping"]["delay_between_requests_seconds"])

    (raw_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    good = sum(m["ok"] for m in manifest)
    print(f"\nPhase 2 complete: {good}/{len(manifest)} pages saved to {raw_dir}")
    if good < len(manifest):
        print("WARNING: some pages failed. Re-run, or enable the Playwright fallback (see README).")
    return manifest


if __name__ == "__main__":
    scrape()
