"""Browser smoke test (needs Playwright; not part of the stdlib unittest suite).

    python tests/ui_smoke.py http://127.0.0.1:8765/
"""

import sys

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765/"


def main():
    failures = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge")
        page = browser.new_page(viewport={"width": 390, "height": 844})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(URL)

        # Text flow renders a report card with a verdict badge
        page.fill("#input", "Here you go ([source](https://example.com/?utm_source=chatgpt.com)). I hope this helps!")
        page.click("#go")
        page.wait_for_selector("#results .card .badge", timeout=15000)
        verdict = page.inner_text("#results .card .badge")
        if "OpenAI ChatGPT" not in verdict:
            failures.append(f"unexpected verdict: {verdict!r}")
        if page.is_disabled("#go"):
            failures.append("Reverse button stayed disabled after the run")

        # App-name flow lists library results or a clear error (network may be blocked)
        page.fill("#input", "cursor")
        page.click("#go")
        page.wait_for_selector("#results .card, #results .note", timeout=60000)

        # Switch toggles and is big enough to tap
        box = page.locator("#use-llm").bounding_box()
        if box["width"] < 32 or box["height"] < 32:
            failures.append(f"switch too small: {box}")
        page.click("#use-llm")
        if not page.is_checked("#use-llm"):
            failures.append("switch did not toggle")

        # File picker is reachable by keyboard
        page.focus("#file-label")
        if page.evaluate("document.activeElement.id") != "file-label":
            failures.append("file picker label is not focusable")

        # Phone: primary action spans the row
        go_width = page.locator("#go").bounding_box()["width"]
        if go_width < 300:
            failures.append(f"Reverse button not full width on phone: {go_width}px")

        if errors:
            failures.append(f"page errors: {errors}")
        page.screenshot(path=sys.argv[2] if len(sys.argv) > 2 else "ui_smoke.png", full_page=True)
        browser.close()

    print("UI SMOKE:", "PASS" if not failures else "FAIL")
    for failure in failures:
        print(" -", failure)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
