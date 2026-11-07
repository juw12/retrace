"""Regenerate the public sample report (static/sample-report.pdf and docs/sample-report.pdf).

Prints the recorded demo website scan through the app's own "Print / save PDF" view,
so the sample is exactly what a user gets. Needs Playwright with Edge or Chromium.

    python scripts/build_pages.py      # records the demo scan into docs/
    python scripts/sample_report.py    # prints it to PDF
"""

import functools
import http.server
import shutil
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
PORT = 8793


def main():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(DOCS))
    handler.log_message = lambda *args: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    output = ROOT / "static" / "sample-report.pdf"
    try:
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(channel="msedge")
            except Exception:
                browser = playwright.chromium.launch()
            context = browser.new_context(viewport={"width": 1280, "height": 900}, service_workers="block")
            page = context.new_page()
            page.goto(f"http://127.0.0.1:{PORT}/?demo")
            page.click("[data-example=site]")
            page.wait_for_selector("#results .transparency", timeout=20000)
            page.evaluate("window.print = () => {}")
            page.click("text=Print / save PDF")
            page.emulate_media(media="print")
            page.pdf(path=str(output), format="A4", print_background=True)
            browser.close()
    finally:
        server.shutdown()
    shutil.copyfile(output, DOCS / "sample-report.pdf")
    print(f"wrote {output.relative_to(ROOT)} and docs/sample-report.pdf ({output.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
