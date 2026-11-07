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


# Words people add to an app name that file names in the collections don't contain ("cursor app").
FILLER = {"app", "apps", "ai", "the", "an", "and", "for", "of", "prompt", "prompts", "system", "leak", "leaked",
          "agent", "agents", "tool", "tools", "assistant", "chatbot", "bot", "model", "models", "ide", "desktop"}


def query_tokens(query):
    """Lower-case words of the query, minus filler. Single digits stay ("GPT 5" -> gpt, 5)."""
    tokens = [token for token in re.findall(r"[a-z0-9]+", query.lower()) if len(token) > 1 or token.isdigit()]
    meaningful = [token for token in tokens if token not in FILLER]
    return meaningful or tokens


def path_words(path):
    """Words of a path, split on punctuation, camelCase and letter/digit changes: ChatGPT-4o -> chat gpt 4 o."""
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", path)
    spaced = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", spaced)
    spaced = re.sub(r"([A-Za-z])(?=[0-9])|([0-9])(?=[A-Za-z])", r"\1\2 ", spaced)
    return re.findall(r"[a-z0-9]+", spaced.lower())


def word_match(token, words):
    """True if the token is one whole word or a run of whole words ("chatgpt" = chat|gpt, "gpt5" = gpt|5)."""
    for start in range(len(words)):
        joined = ""
        for word in words[start:]:
            joined += word
            if joined == token:
                return True
            if not token.startswith(joined):
                break
    return False


def match_tier(tokens, path):
    """1 = every word matches whole words, 2 = every word appears inside the path, 3 = some word matches."""
    words = path_words(path)
    if all(word_match(token, words) for token in tokens):
        return 1
    if len(tokens) > 1 and word_match("".join(tokens), words):
        return 1
    compact = re.sub(r"[^a-z0-9]", "", path.lower())
    if all(token in compact for token in tokens):
        return 2
    if any(word_match(token, words) for token in tokens):
        return 3
    return None


def rank_matches(query, repo, paths, tiers=(1,)):
    """Files whose path matches the query in one of the given tiers (see match_tier)."""
    tokens = query_tokens(query)
    if not tokens:
        return []
    matches = []
    for path in paths:
        tier = match_tier(tokens, path)
        if tier not in tiers:
            continue
        words = path_words(path)
        name_words = path_words(path.rsplit("/", 1)[-1])
        top_words = words if "/" not in path else path_words(path.split("/", 1)[0])
        hits = sum(word_match(token, words) for token in tokens)
        phrase = len(tokens) > 1 and word_match("".join(tokens), words)
        if all(word_match(token, name_words) for token in tokens):
            place = 0
        elif all(word_match(token, top_words) for token in tokens):
            place = 1
        else:
            place = 2
        matches.append({
            "repo": repo,
            "path": path,
            "url": f"https://github.com/{repo}/blob/HEAD/{quote(path)}",
            "rank": (tier, 0 if phrase else 1, -hits, place, len(path)),
        })
    return matches


def rank_by_rarity(matches, tokens, all_paths):
    """Closest matches: a file matching a rare word ("dia") beats one matching a common word ("browser")."""
    counts = {token: sum(word_match(token, path_words(path)) for path in all_paths) for token in tokens}
    for match in matches:
        words = path_words(match["path"])
        rarity = sum(1 / counts[token] for token in tokens if counts[token] and word_match(token, words))
        tier, *rest = match["rank"]
        match["rank"] = (tier, -round(rarity, 6), *rest)


def search(query, limit=60):
    errors, trees = [], {}
    with ThreadPoolExecutor(max_workers=len(REPOS)) as pool:
        jobs = {repo: pool.submit(repo_paths, repo) for repo in REPOS}
    for repo, job in jobs.items():
        try:
            trees[repo] = job.result()
        except Exception as error:
            errors.append(f"{repo}: {error}")
    results = [match for repo, paths in trees.items() for match in rank_matches(query, repo, paths)]
    partial = False
    if not results:  # no whole-word match: show the closest ones and say so
        results = [match for repo, paths in trees.items()
                   for match in rank_matches(query, repo, paths, tiers=(2, 3))]
        partial = bool(results)
        rank_by_rarity(results, query_tokens(query), [path for paths in trees.values() for path in paths])
    results.sort(key=lambda item: item["rank"])
    for item in results:
        item.pop("rank")
    return {"query": query, "results": results[:limit], "total": len(results), "errors": errors,
            "partial": partial, "sources": REPOS}


def fetch_file(repo, path):
    if repo not in REPOS:
        raise ValueError("Unknown repository")
    if path not in repo_paths(repo):
        raise ValueError("File is not in that repository")
    raw_url = f"https://raw.githubusercontent.com/{repo}/HEAD/{quote(path)}"
    content = _get(raw_url).decode("utf-8", "replace")
    return {"repo": repo, "path": path, "url": f"https://github.com/{repo}/blob/HEAD/{quote(path)}",
            "content": content}
