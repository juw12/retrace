"""Browser smoke test (needs Playwright; not part of the stdlib unittest suite).

    python tests/ui_smoke.py http://127.0.0.1:8765/ [screenshot-folder]
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765/"
SHOTS = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".")


def check_phone(browser, failures):
    page = browser.new_page(viewport={"width": 390, "height": 844})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(URL)

    # Empty state: the action is disabled and says what to do
    if not page.is_disabled("#go"):
        failures.append("Analyze button should be disabled before any input")

    # Detection updates the button label as the user types
    page.fill("#input", "https://example.com")
    if page.inner_text("#go").strip() != "Scan website":
        failures.append(f"URL not detected: button says {page.inner_text('#go')!r}")
    page.fill("#input", "cursor")
    if page.inner_text("#go").strip() != "Search library":
        failures.append("app name not detected")

    # Example chip runs a full text analysis
    page.click("[data-example=text]")
    page.wait_for_selector("#results .result .verdict", timeout=15000)
    verdict = page.inner_text("#results .result .verdict")
    if "OpenAI ChatGPT" not in verdict:
        failures.append(f"unexpected verdict: {verdict!r}")
    if page.is_disabled("#go"):
        failures.append("button stayed disabled after the run")
    if not page.is_hidden("#how"):
        failures.append("intro cards should hide once results show")
    page.screenshot(path=str(SHOTS / "smoke_phone_result.png"), full_page=True)

    # Switch is a comfortable target and toggles
    box = page.locator("#use-llm").bounding_box()
    if box["width"] < 32 or box["height"] < 32:
        failures.append(f"switch too small: {box}")
    page.click("#use-llm")
    if not page.is_checked("#use-llm"):
        failures.append("switch did not toggle")

    # Keyboard-reachable file picker, comfortable primary action
    page.focus("#file-label")
    if page.evaluate("document.activeElement.id") != "file-label":
        failures.append("Add image is not focusable")
    go_box = page.locator("#go").bounding_box()
    if go_box["height"] < 44 or go_box["width"] < 140:
        failures.append(f"Analyze button too small on phone: {go_box}")

    # Tabs switch panels; settings save gives feedback
    page.click("#tab-btn-settings")
    if page.is_hidden("#tab-settings") or not page.is_hidden("#tab-analyze"):
        failures.append("tab switching failed")
    page.click("#set-save")
    if page.inner_text("#set-status").strip() != "Saved":
        failures.append("settings save gave no feedback")
    if errors:
        failures.append(f"page errors: {errors}")
    page.close()


def check_dark(browser, failures):
    page = browser.new_page(viewport={"width": 1280, "height": 900}, color_scheme="dark")
    page.goto(URL)
    background = page.evaluate("getComputedStyle(document.body).backgroundColor")
    if background in ("rgb(255, 255, 255)", "rgb(245, 246, 248)"):
        failures.append(f"dark mode not applied: {background}")
    page.screenshot(path=str(SHOTS / "smoke_dark_1280.png"))
    page.close()


def main():
    failures = []
    SHOTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge")
        check_phone(browser, failures)
        check_dark(browser, failures)
        browser.close()
    print("UI SMOKE:", "PASS" if not failures else "FAIL")
    for failure in failures:
        print(" -", failure)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
