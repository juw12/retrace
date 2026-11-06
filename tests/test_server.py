"""HTTP-level tests: static app shell, PWA files, path safety and API routes."""

import base64
import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import app  # noqa: E402
from test_analyzers import make_png  # noqa: E402

DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = app.start_server(8890)
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def get(self, path):
        try:
            with DIRECT.open(self.base + path) as response:
                return response.status, response.headers.get("Content-Type"), response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.headers.get("Content-Type"), error.read()

    def post(self, path, body):
        request = urllib.request.Request(self.base + path, data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"})
        try:
            with DIRECT.open(request) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def test_app_shell_and_pwa_files(self):
        status, content_type, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", content_type)
        self.assertIn(b'rel="manifest"', body)
        status, content_type, body = self.get("/manifest.webmanifest")
        self.assertEqual(status, 200)
        manifest = json.loads(body)
        self.assertEqual(manifest["display"], "standalone")
        for icon in manifest["icons"]:
            self.assertEqual(self.get("/" + icon["src"].lstrip("./"))[0], 200)
        self.assertEqual(self.get("/sw.js")[0], 200)

    def test_no_path_traversal(self):
        self.assertEqual(self.get("/../app.py")[0], 404)
        self.assertEqual(self.get("/%2e%2e/app.py")[0], 404)
        self.assertEqual(self.get("/missing.html")[0], 404)

    def test_image_and_text_routes(self):
        png = make_png(512, 512, [("parameters", "a fox\nSteps: 20, Sampler: Euler, Seed: 1, Model: sd15")])
        status, report = self.post("/api/image", {"filename": "fox.png", "data": base64.b64encode(png).decode()})
        self.assertEqual(status, 200)
        self.assertEqual(report["prompt"]["positive"], "a fox")
        status, report = self.post("/api/text", {"text": "see https://a.b/?utm_source=chatgpt.com"})
        self.assertEqual(report["verdict"]["label"], "OpenAI ChatGPT")
        status, report = self.post("/api/text", {"text": "   "})
        self.assertEqual(status, 400)

    def test_probe_requires_authorization(self):
        status, report = self.post("/api/probe", {"llm": {"model": "x"}})
        self.assertEqual(status, 400)
        self.assertIn("authorized", report["error"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
