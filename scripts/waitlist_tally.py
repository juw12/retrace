"""Retrace Agency waitlist tally (standard library only).

Counts waitlist issues against the launch success line and keeps a public
tracking issue up to date. Runs in GitHub Actions and locally.

    python scripts/waitlist_tally.py                 # print the tally
    python scripts/waitlist_tally.py --update        # also rewrite the tracking issue
    python scripts/waitlist_tally.py --welcome 12    # thank the author of issue 12 (once)

Token: GITHUB_TOKEN, or `gh auth token` when run locally.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import date, datetime, timezone

REPO = os.environ.get("GITHUB_REPOSITORY", "juw12/retrace")
OWNER = REPO.split("/")[0]
WAITLIST_LABEL = "waitlist"
TRACKER_LABEL = "waitlist-tally"
TITLE_PREFIX = "retrace agency waitlist"
GOAL = 10
START = date(2026, 11, 8)
DEADLINE = date(2026, 11, 28)
WELCOME_MARKER = "<!-- retrace-waitlist-welcome -->"
WELCOME_TEXT = WELCOME_MARKER + """
Thanks for joining the Retrace Agency waitlist. You'll hear back here when the founding licence opens \
(EUR 15/month for life for the first 50 agencies, 30-day refund).

Meanwhile the free app already prints a dated evidence report for any single site: \
https://github.com/juw12/retrace#readme (sample: https://juw12.github.io/retrace/sample-report.pdf).
Technical evidence, not legal advice."""
ANSWERS = ("yes", "maybe", "no")


def parse_answer(body):
    """'yes' / 'maybe' / 'no' from the founding-offer question, or None if unanswered."""
    body = body or ""
    section = re.search(r"###[^\n]*founding offer[^\n]*\n+(.*?)(?=\n###|\Z)", body, re.I | re.S)
    if section:
        answer = section.group(1).strip().lower()  # "_No response_" when skipped
        return answer if answer in ANSWERS else None
    # Older free-text issues: "founding offer (...)? yes" - but the unedited prompt lists all three.
    line = re.search(r"founding offer[^\n]*", body, re.I)
    if line:
        tail = line.group(0).lower().rsplit("?", 1)[-1]
        found = [answer for answer in ANSWERS if re.search(rf"\b{answer}\b", tail)]
        if len(found) == 1:
            return found[0]
    return None


def is_waitlist_issue(issue):
    labels = {label["name"] if isinstance(label, dict) else label for label in issue.get("labels", [])}
    if TRACKER_LABEL in labels or issue.get("pull_request"):
        return False
    return WAITLIST_LABEL in labels or (issue.get("title") or "").lower().startswith(TITLE_PREFIX)


def tally(issues, owner=OWNER):
    """Count sign-ups by answer. The repo owner's own test issues are listed but not counted."""
    counts = {answer: 0 for answer in ANSWERS}
    counts["unanswered"] = 0
    entries = []
    for issue in issues:
        if not is_waitlist_issue(issue):
            continue
        author = (issue.get("user") or {}).get("login", "")
        answer = parse_answer(issue.get("body"))
        counted = author.lower() != owner.lower()
        if counted:
            counts[answer or "unanswered"] += 1
        entries.append({"number": issue["number"], "answer": answer or "unanswered",
                        "counted": counted, "state": issue.get("state", "open")})
    return {"counts": counts, "entries": sorted(entries, key=lambda entry: entry["number"])}


def decision(yes_count, today):
    if yes_count >= GOAL:
        return f"Success line met ({yes_count} yes of {GOAL}). Next: set up payments and build batch mode."
    if today <= DEADLINE:
        days_left = (DEADLINE - today).days
        return f"Running: {yes_count} of {GOAL} yes, {days_left} day(s) left (ends {DEADLINE.isoformat()})."
    if yes_count >= 3:
        return f"Missed ({yes_count} yes). Rework the offer (try the EUR 49 one-off pack) and run 21 more days."
    return f"Missed ({yes_count} yes). Stop the paid tier; keep Retrace free."


def render(result, today, now=None):
    counts = result["counts"]
    now = now or datetime.now(timezone.utc).replace(microsecond=0)
    lines = [
        "Live tally of the Retrace Agency waitlist, updated automatically by "
        "`.github/workflows/waitlist.yml`. Join: "
        "https://github.com/juw12/retrace/issues/new?template=agency-waitlist.yml",
        "",
        f"**{decision(counts['yes'], today)}**",
        "",
        "| answer | count |",
        "| --- | ---: |",
        f"| Yes | {counts['yes']} |",
        f"| Maybe | {counts['maybe']} |",
        f"| No | {counts['no']} |",
        f"| Unanswered | {counts['unanswered']} |",
        "",
        f"Success line: {GOAL} \"Yes\" between {START.isoformat()} and {DEADLINE.isoformat()}. "
        "3-9 means rework the offer; under 3 means stop the paid tier.",
        "",
    ]
    if result["entries"]:
        lines.append("Sign-ups: " + ", ".join(
            f"#{entry['number']} ({entry['answer']}{'' if entry['counted'] else ', test - not counted'})"
            for entry in result["entries"]))
        lines.append("")
    lines.append(f"_Updated {now.isoformat().replace('+00:00', 'Z')}._")
    return "\n".join(lines)


# ---------- GitHub API ----------
def token():
    value = os.environ.get("GITHUB_TOKEN")
    if value:
        return value
    return subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True).stdout.strip()


def api(method, path, payload=None):
    request = urllib.request.Request(
        f"https://api.github.com{path}",
        data=None if payload is None else json.dumps(payload).encode(),
        method=method,
        headers={"Authorization": f"Bearer {token()}", "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "retrace-waitlist"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read() or b"null")


def all_issues():
    issues, page = [], 1
    while True:
        batch = api("GET", f"/repos/{REPO}/issues?state=all&per_page=100&page={page}")
        issues += batch
        if len(batch) < 100:
            return issues
        page += 1


def welcome(number):
    comments = api("GET", f"/repos/{REPO}/issues/{number}/comments?per_page=100")
    if any(WELCOME_MARKER in (comment.get("body") or "") for comment in comments):
        return False
    api("POST", f"/repos/{REPO}/issues/{number}/comments", {"body": WELCOME_TEXT})
    return True


def update_tracker(body):
    trackers = api("GET", f"/repos/{REPO}/issues?labels={TRACKER_LABEL}&state=open")
    if trackers:
        api("PATCH", f"/repos/{REPO}/issues/{trackers[0]['number']}", {"body": body})
        return trackers[0]["number"]
    created = api("POST", f"/repos/{REPO}/issues",
                  {"title": "Retrace Agency waitlist: live tally", "body": body, "labels": [TRACKER_LABEL]})
    return created["number"]


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--update", action="store_true", help="rewrite the tracking issue")
    parser.add_argument("--welcome", type=int, help="thank the author of this issue number (once)")
    args = parser.parse_args()
    if args.welcome:
        issue = api("GET", f"/repos/{REPO}/issues/{args.welcome}")
        if is_waitlist_issue(issue):
            print("welcomed" if welcome(args.welcome) else "already welcomed", args.welcome)
    result = tally(all_issues())
    body = render(result, datetime.now(timezone.utc).date())
    print(body)
    if args.update:
        print("tracker issue:", update_tracker(body))
    return 0


if __name__ == "__main__":
    sys.exit(main())
