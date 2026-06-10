"""Streamlit UI のスクショ検証 (frontend-observation の代替: Playwright 直叩き).

- デスクトップ (1440x900) / モバイル (390x844) で各タブを撮影
- console エラー / 失敗リクエスト (自オリジン) を収集して最後に報告

実行: uv run --with playwright python .context/ui_screenshot_check.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://localhost:8501"
OUT = Path(".context/screenshots")
OUT.mkdir(parents=True, exist_ok=True)

console_errors: list[str] = []
failed_requests: list[str] = []


def watch(page) -> None:  # type: ignore[no-untyped-def]
    page.on(
        "console",
        lambda msg: console_errors.append(f"{msg.type}: {msg.text}")
        if msg.type in ("error",)
        else None,
    )
    page.on(
        "requestfailed",
        lambda req: failed_requests.append(f"{req.method} {req.url} :: {req.failure}")
        if "localhost" in req.url
        else None,
    )


def wait_app(page) -> None:  # type: ignore[no-untyped-def]
    page.wait_for_selector('[data-testid="stApp"]', timeout=30000)
    # Streamlit はスクリプト実行が落ち着くまで描画が動くので少し待つ
    page.wait_for_timeout(2500)


def click_tab(page, label: str) -> None:  # type: ignore[no-untyped-def]
    page.get_by_role("tab", name=label).click()
    page.wait_for_timeout(1200)


def run(viewport: dict, tag: str) -> None:  # type: ignore[type-arg, no-untyped-def]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport=viewport)
        watch(page)
        page.goto(BASE, wait_until="domcontentloaded")
        wait_app(page)

        # タブ 1: 取り込み (デフォルト表示)
        page.screenshot(path=str(OUT / f"{tag}-1-ingest.png"), full_page=True)

        # タブ 2: 検索 → クエリ実行して結果も撮る
        click_tab(page, "🔍 検索")
        page.screenshot(path=str(OUT / f"{tag}-2-search-empty.png"), full_page=True)
        try:
            page.get_by_label("検索クエリ").fill("quarterly revenue results")
            page.get_by_role("button", name="検索").click()
            # 結果カード or メッセージが出るまで待つ
            page.wait_for_timeout(4000)
            page.screenshot(path=str(OUT / f"{tag}-3-search-results.png"), full_page=True)
        except Exception as e:  # noqa: BLE001
            print(f"[{tag}] search interaction failed: {e}")

        # タブ 3: 質問 → キー未投入の 503 表示を確認
        click_tab(page, "💬 質問")
        try:
            page.get_by_test_id("stChatInput").locator("textarea").fill("この動画の要点は?")
            page.keyboard.press("Enter")
            page.wait_for_timeout(4000)
        except Exception as e:  # noqa: BLE001
            print(f"[{tag}] chat interaction failed: {e}")
        page.screenshot(path=str(OUT / f"{tag}-4-ask.png"), full_page=True)

        browser.close()


run({"width": 1440, "height": 900}, "desktop")
run({"width": 390, "height": 844}, "mobile")

print("--- console errors ---")
print("\n".join(console_errors) or "(none)")
print("--- failed requests (own origin) ---")
print("\n".join(failed_requests) or "(none)")
print(f"screenshots: {sorted(p.name for p in OUT.glob('*.png'))}")
sys.exit(0)
