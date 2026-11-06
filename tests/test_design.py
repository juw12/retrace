"""Design guards requested by the owner: no emoji and no purple anywhere in the UI."""

import colorsys
import re
import unittest
import unicodedata
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "static"
UI_FILES = [STATIC / "index.html", STATIC / "manifest.webmanifest"]
EMOJI_RANGES = [(0x1F000, 0x1FAFF), (0x2600, 0x27BF), (0x2190, 0x21FF), (0x2B00, 0x2BFF), (0xFE0F, 0xFE0F)]


def is_purple(hex_color):
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(ch * 2 for ch in hex_color)
    red, green, blue = (int(hex_color[i:i + 2], 16) / 255 for i in (0, 2, 4))
    hue, lightness, saturation = colorsys.rgb_to_hls(red, green, blue)
    return 250 <= hue * 360 <= 320 and saturation > 0.25 and 0.08 < lightness < 0.95


class DesignGuards(unittest.TestCase):
    def test_no_emoji_or_pictographs(self):
        for path in UI_FILES:
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                for character in line:
                    code = ord(character)
                    pictograph = unicodedata.category(character) == "So"
                    in_range = any(start <= code <= end for start, end in EMOJI_RANGES)
                    self.assertFalse(pictograph or in_range,
                                     f"{path.name}:{line_number} contains {character!r} (U+{code:04X})")

    def test_no_purple_colours(self):
        for path in UI_FILES:
            text = path.read_text(encoding="utf-8")
            for match in re.finditer(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b", text):
                self.assertFalse(is_purple(match.group()), f"{path.name}: purple colour {match.group()}")
            for match in re.finditer(r"rgba?\((\d+),\s*(\d+),\s*(\d+)", text):
                red, green, blue = (int(value) for value in match.groups())
                self.assertFalse(is_purple(f"#{red:02x}{green:02x}{blue:02x}"), f"{path.name}: purple {match.group()}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
