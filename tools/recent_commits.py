#!/usr/bin/env python3
"""Inject recent commit messages into README.md between marker comments.

Most profile READMEs show a streak counter, which proves only that you showed up.
The commit messages say what was actually decided, so those go in instead.
"""

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

USER = os.environ.get("PROFILE_USER", "OkayAnshul")
COUNT = int(os.environ.get("COMMIT_COUNT", "5"))
README = os.environ.get("README_PATH", "README.md")

START = "<!--RECENT_COMMITS:START-->"
END = "<!--RECENT_COMMITS:END-->"

# Merge/automation noise that says nothing about the work.
SKIP = re.compile(
    r"^(merge\b|initial commit$|update readme|generate profile|deploy|bump\b)",
    re.IGNORECASE,
)


def token() -> str:
    tok = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if tok:
        return tok
    # Local runs: fall back to whatever gh is already authenticated with.
    try:
        return subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        sys.exit("No GH_TOKEN / GITHUB_TOKEN and `gh auth token` unavailable.")


def fetch(url: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token()}",
            "Accept": "application/vnd.github+json",
            "User-Agent": f"{USER}-profile-readme",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def ago(iso: str) -> str:
    then = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    days = (datetime.now(timezone.utc) - then).days
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days < 30:
        return f"{days} days ago"
    months = days // 30
    return "1 month ago" if months == 1 else f"{months} months ago"


def collect() -> list[str]:
    """Newest public commits authored by USER, one line each."""
    url = (
        "https://api.github.com/search/commits"
        f"?q=author:{USER}+is:public&sort=author-date&order=desc"
        f"&per_page={COUNT * 4}"
    )
    try:
        items = fetch(url).get("items", [])
    except urllib.error.HTTPError as exc:
        print(f"search/commits failed ({exc.code}); leaving the block untouched.")
        return []

    lines, seen = [], set()
    for item in items:
        subject = item["commit"]["message"].split("\n", 1)[0].strip()
        if SKIP.match(subject) or subject in seen:
            continue
        seen.add(subject)
        repo = item["repository"]["name"]
        when = ago(item["commit"]["author"]["date"])
        subject = subject.replace("|", "\\|")
        lines.append(f"- **[{repo}]({item['html_url']})** — {subject} _· {when}_")
        if len(lines) == COUNT:
            break
    return lines


def main() -> None:
    lines = collect()
    if not lines:
        return

    with open(README, encoding="utf-8") as fh:
        content = fh.read()

    if START not in content or END not in content:
        sys.exit(f"Markers missing from {README}.")

    block = f"{START}\n" + "\n".join(lines) + f"\n{END}"
    updated = re.sub(
        re.escape(START) + r".*?" + re.escape(END), block, content, flags=re.DOTALL
    )

    if updated == content:
        print("No change.")
        return

    with open(README, "w", encoding="utf-8") as fh:
        fh.write(updated)
    print(f"Wrote {len(lines)} commits.")


if __name__ == "__main__":
    main()
