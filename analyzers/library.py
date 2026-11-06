"""Search public GitHub collections of leaked system prompts, tool definitions and AI skills.

File lists are cached in ./cache for 24 h to stay inside GitHub's 60 requests/hour
anonymous limit. Set GITHUB_TOKEN for a higher limit.
"""

import json
import os
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote

REPOS = {
    "x1xhlol/system-prompts-and-models-of-ai-tools": "System prompts + tool definitions of AI coding agents & apps",
    "elder-plinius/CL4R1T4S": "System prompts of major AI assistants",
    "jujumilk3/leaked-system-prompts": "Leaked system prompts",
    "asgeirtj/system_prompts_leaks": "System prompts of ChatGPT, Claude, Gemini, Grok…",
    "anthropics/skills": "Anthropic's official Agent Skills",
}
TEXT_EXTENSIONS = {".txt", ".md", ".mdx", ".json", ".yaml", ".yml", ".xml", ".js", ".ts", ".py", ""}
CACHE_DIR = Path(__file__).resolve().parent.parent / "cache"
CACHE_SECONDS = 24 * 3600
MAX_FILE_BYTES = 600_000
MAX_TREE_BYTES = 30_000_000


def _get(url, limit=MAX_FILE_BYTES):
    headers = {"User-Agent": "Retrace", "Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token and "api.github.com" in url:
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=25) as response:
        return response.read(limit)


def repo_paths(repo):
    cache_file = CACHE_DIR / (repo.replace("/", "__") + ".json")
    fresh = cache_file.exists() and time.time() - cache_file.stat().st_mtime < CACHE_SECONDS
    if fresh:
        return json.loads(cache_file.read_text("utf-8"))
    try:
        tree = json.loads(_get(f"https://api.github.com/repos/{repo}/git/trees/HEAD?recursive=1", MAX_TREE_BYTES))
    except Exception:
        if cache_file.exists():  # stale cache beats nothing
            return json.loads(cache_file.read_text("utf-8"))
        raise
    paths = [item["path"] for item in tree.get("tree", [])
             if item.get("type") == "blob" and Path(item["path"]).suffix.lower() in TEXT_EXTENSIONS]
    CACHE_DIR.mkdir(exist_ok=True)
    cache_file.write_text(json.dumps(paths), "utf-8")
    return paths


def rank_matches(query, repo, paths):
    tokens = [token for token in re.findall(r"[a-z0-9]+", query.lower()) if len(token) > 1]
    matches = []
    for path in paths:
        compact = re.sub(r"[^a-z0-9]", "", path.lower())
        if tokens and all(token in compact for token in tokens):
            file_name = re.sub(r"[^a-z0-9]", "", path.rsplit("/", 1)[-1].lower())
            in_name = all(token in file_name for token in tokens)
            matches.append({
                "repo": repo,
                "path": path,
                "url": f"https://github.com/{repo}/blob/HEAD/{quote(path)}",
                "rank": (0 if in_name else 1, len(path)),
            })
    return matches


def search(query, limit=60):
    results, errors = [], []
    with ThreadPoolExecutor(max_workers=len(REPOS)) as pool:
        jobs = {repo: pool.submit(repo_paths, repo) for repo in REPOS}
    for repo, job in jobs.items():
        try:
            results += rank_matches(query, repo, job.result())
        except Exception as error:
            errors.append(f"{repo}: {error}")
    results.sort(key=lambda item: item["rank"])
    for item in results:
        item.pop("rank")
    return {"query": query, "results": results[:limit], "total": len(results), "errors": errors,
            "sources": REPOS}


def fetch_file(repo, path):
    if repo not in REPOS:
        raise ValueError("Unknown repository")
    if path not in repo_paths(repo):
        raise ValueError("File is not in that repository")
    raw_url = f"https://raw.githubusercontent.com/{repo}/HEAD/{quote(path)}"
    content = _get(raw_url).decode("utf-8", "replace")
    return {"repo": repo, "path": path, "url": f"https://github.com/{repo}/blob/HEAD/{quote(path)}",
            "content": content}
