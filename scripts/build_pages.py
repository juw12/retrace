"""Build the GitHub Pages demo in docs/.

Copies the app shell from static/ and records the three example results by running
the real analyzers, so the online demo shows genuine output (no invented data).

    python scripts/build_pages.py
"""

import json
import re
from datetime import date
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from analyzers import library, site, text  # noqa: E402

STATIC = ROOT / "static"
DOCS = ROOT / "docs"


def example_values():
    """Read the example inputs straight from the UI so demo and app never drift apart."""
    page = (STATIC / "index.html").read_text(encoding="utf-8")
    block = re.search(r"const EXAMPLES = \{(.*?)\};", page, re.S).group(1)
    return dict(re.findall(r'(\w+): "((?:[^"\\]|\\.)*)"', block))


def main():
    examples = example_values()
    if DOCS.exists():
        shutil.rmtree(DOCS)
    shutil.copytree(STATIC, DOCS)
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")
    demo = DOCS / "demo"
    demo.mkdir()

    recordings = {
        "text.json": text.analyze_text(examples["text"]),
        "site.json": site.analyze_site(examples["site"]),
        "library.json": library.search(examples["app"]),
    }
    for name, payload in recordings.items():
        (demo / name).write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"recorded docs/demo/{name}")
    if recordings["library.json"]["errors"]:
        sys.exit(f"library search had errors: {recordings['library.json']['errors']}")

    # File lists of every collection, so the demo still works when GitHub's
    # 60-lookups-per-hour anonymous limit is used up (common on shared office networks).
    trees = {repo: library.repo_paths(repo) for repo in library.REPOS}
    empty = [repo for repo, paths in trees.items() if not paths]
    if empty:
        sys.exit(f"empty file list for: {empty}")
    index = {"built": date.today().isoformat(), "trees": trees}
    (demo / "library-index.json").write_text(json.dumps(index, separators=(",", ":")), encoding="utf-8")
    print(f"saved docs/demo/library-index.json ({sum(len(paths) for paths in trees.values())} files)")
    print("docs/ ready")


if __name__ == "__main__":
    main()
