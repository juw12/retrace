import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from analyzers import site  # noqa: E402


class PublishedLlmsTxtTests(unittest.TestCase):
    def test_layout(self):
        text_value = (ROOT / "static" / "llms.txt").read_text(encoding="utf-8")
        lines = text_value.splitlines()
        self.assertEqual(lines[0], "# Retrace")
        self.assertTrue(any(line.startswith("> ") for line in lines[:4]), "needs a blockquote summary")
        self.assertIn("## Links", text_value)
        self.assertIn("https://github.com/juw12/retrace", text_value)

    def test_own_scanner_accepts_it(self):
        text_value = (ROOT / "static" / "llms.txt").read_text(encoding="utf-8")
        result = {"status": 200, "headers": {"content-type": "text/plain; charset=utf-8"}, "text": text_value}
        self.assertTrue(site._is_text_file(result))


if __name__ == "__main__":
    unittest.main()
