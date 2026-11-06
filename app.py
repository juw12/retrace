"""Retrace — find the AI, prompt, model, tools and settings behind an image, text,
website or chatbot API. Local app, Python standard library only.

    python app.py                 # opens Retrace in its own app window (Edge/Chrome app mode)
    python app.py --browser       # open in a normal browser tab instead
    python app.py --no-browser    # server only (http://127.0.0.1:8765)
    python app.py --install       # add a Start-menu shortcut (Windows)
"""

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from analyzers import image, library, llm, probe, site, text

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
MAX_BODY_BYTES = 40 * 1024 * 1024
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".webmanifest": "application/manifest+json",
    ".png": "image/png",
    ".ico": "image/x-icon",
}
BROWSER_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]


def handle_image(body):
    data = base64.b64decode(body["data"])
    report = image.analyze_image(data, body.get("filename", ""))
    if body.get("use_llm"):
        try:
            report["llm"] = llm.reverse_image(body.get("llm") or {}, data, body.get("mime"))
        except Exception as error:
            report["llm_error"] = str(error)
    return report


def handle_text(body):
    content = body.get("text", "")
    if not content.strip():
        raise ValueError("No text given")
    report = text.analyze_text(content)
    if body.get("use_llm"):
        try:
            report["llm"] = llm.reverse_text(body.get("llm") or {}, content)
        except Exception as error:
            report["llm_error"] = str(error)
    return report


def handle_site(body):
    return site.analyze_site(body.get("url", ""))


def handle_probe(body):
    if not body.get("authorized"):
        raise PermissionError("Confirm that you own or are authorized to test this endpoint.")
    return probe.run_probe(body.get("llm") or {}, body.get("system_prompt", ""))


POST_ROUTES = {
    "/api/image": handle_image,
    "/api/text": handle_text,
    "/api/site": handle_site,
    "/api/probe": handle_probe,
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        query = {key: values[0] for key, values in parse_qs(url.query).items()}
        if url.path == "/api/library/search":
            self._run(library.search, query.get("q", ""))
        elif url.path == "/api/library/file":
            self._run(library.fetch_file, query.get("repo", ""), query.get("path", ""))
        else:
            self._static(url.path)

    def do_POST(self):
        route = POST_ROUTES.get(urlparse(self.path).path)
        length = int(self.headers.get("Content-Length") or 0)
        if not route:
            self._json(404, {"error": "Not found"})
        elif length > MAX_BODY_BYTES:
            self._json(413, {"error": "Upload too large (40 MB max)"})
        else:
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                self._json(400, {"error": "Invalid JSON"})
                return
            self._run(route, body)

    def _static(self, path):
        relative = "index.html" if path in ("", "/") else path.lstrip("/")
        target = (STATIC_DIR / relative).resolve()
        if STATIC_DIR not in target.parents or not target.is_file() or target.suffix not in CONTENT_TYPES:
            self._json(404, {"error": "Not found"})
            return
        self._send(200, target.read_bytes(), CONTENT_TYPES[target.suffix])

    def _run(self, function, *args):
        try:
            self._json(200, function(*args))
        except (ValueError, PermissionError, RuntimeError) as error:
            self._json(400, {"error": str(error)})
        except Exception as error:
            traceback.print_exc()
            self._json(500, {"error": f"{type(error).__name__}: {error}"})

    def _json(self, status, payload):
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json")

    def _send(self, status, data, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        if sys.stderr:
            sys.stderr.write(f"  {self.command} {self.path.split('?')[0]} -> {args[1] if len(args) > 1 else ''}\n")


def find_app_browser():
    for candidate in BROWSER_CANDIDATES:
        if candidate and Path(candidate).exists():
            return candidate
    return shutil.which("msedge") or shutil.which("chrome")


def open_app_window(address):
    """Open Retrace chromeless in its own browser profile; returns the process (None if no browser)."""
    browser = find_app_browser()
    if not browser:
        return None
    profile = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Retrace" / "window-profile"
    profile.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen([
        browser,
        f"--app={address}",
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--no-default-browser-check",
        "--window-size=1200,900",
    ])


def install_shortcut():
    """Create a Start-menu shortcut that starts Retrace without a console window."""
    if os.name != "nt":
        sys.exit("--install is Windows-only; on other systems run `python app.py`.")
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    runner = pythonw if pythonw.exists() else Path(sys.executable)
    programs = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    shortcut = programs / "Retrace.lnk"
    script = (
        "$shell = New-Object -ComObject WScript.Shell; "
        f"$link = $shell.CreateShortcut('{shortcut}'); "
        f"$link.TargetPath = '{runner}'; "
        f"$link.Arguments = '\"{APP_DIR / 'app.py'}\"'; "
        f"$link.WorkingDirectory = '{APP_DIR}'; "
        f"$link.IconLocation = '{STATIC_DIR / 'icons' / 'retrace.ico'}'; "
        "$link.Description = 'Find the AI behind anything'; "
        "$link.Save()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True)
    print(f"Start-menu shortcut created: {shortcut}")


def start_server(port):
    for candidate in range(port, port + 10):
        try:
            return ThreadingHTTPServer(("127.0.0.1", candidate), Handler)
        except OSError:
            continue
    sys.exit(f"No free port between {port} and {port + 9}")


def main():
    parser = argparse.ArgumentParser(description="Retrace — find the AI behind anything")
    parser.add_argument("--port", type=int, default=8765)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--browser", action="store_true", help="open in a normal browser tab")
    mode.add_argument("--no-browser", action="store_true", help="only run the server")
    mode.add_argument("--install", action="store_true", help="add a Start-menu shortcut and exit")
    options = parser.parse_args()

    if options.install:
        install_shortcut()
        return

    server = start_server(options.port)
    address = f"http://127.0.0.1:{server.server_port}/"
    print(f"Retrace running at {address}  (Ctrl+C to stop)")

    window = None
    if not options.no_browser and not options.browser:
        window = open_app_window(address)
    if window is None and not options.no_browser:
        webbrowser.open(address)

    if window is None:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("Stopped.")
        return

    # App-window mode: the app quits when its window is closed.
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        window.wait()
    except KeyboardInterrupt:
        pass
    server.shutdown()


if __name__ == "__main__":
    main()
