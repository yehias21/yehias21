#!/usr/bin/env python3
"""Render assets/github-stats.svg and assets/top-langs.svg from the GitHub API.

The README used to hotlink a public github-readme-stats deployment
(github-readme-stats-sigma-five.vercel.app). That instance has no PAT configured,
so both cards render as "Maximum retries exceeded / Please add an env variable
called PAT_1". Rather than depend on someone else's quota, we query the GraphQL
API ourselves and commit the SVGs, the same way refresh_spy.py handles the chart.

The stats, the language split and the rank formula follow anuraghazra's
github-readme-stats (MIT); the rank is a reimplementation of its calculateRank.js
so the letter stays comparable to what the card used to show.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os
import pathlib
import sys
import urllib.error
import urllib.request

USER = "yehias21"
COUNT_PRIVATE = True          # include private contributions when the token can see them
# "learning" is vendored course material (Spark and friends): 51 MB of Scala/Java that
# buries everything you actually write. "jupyternotebookrepo" is inherited from the old
# card's exclude_repo param. Names are lowercase.
EXCLUDE_REPOS = {"jupyternotebookrepo", "learning"}
HIDE_LANGS = {"jupyter notebook", "less", "scss"}
LANGS_COUNT = 8

STATS_ASSET = pathlib.Path("assets/github-stats.svg")
LANGS_ASSET = pathlib.Path("assets/top-langs.svg")

# radical theme, so the cards look like the ones they replace
BG = "#141321"
TITLE = "#fe428e"
ICON = "#f8d847"
TEXT = "#a9fef7"
BORDER = "#2c2a42"

FONT = "'Segoe UI',Ubuntu,Sans-Serif"
API = "https://api.github.com/graphql"

# octicons (MIT), 16x16 viewbox paths
ICONS = {
    "star": "M8 .25a.75.75 0 01.673.418l1.882 3.815 4.21.612a.75.75 0 01.416 1.279l-3.046 2.97.719 4.192a.75.75 0 01-1.088.791L8 12.347l-3.766 1.98a.75.75 0 01-1.088-.79l.72-4.194L.818 6.374a.75.75 0 01.416-1.28l4.21-.611L7.327.668A.75.75 0 018 .25z",
    "commit": "M10.5 7.75a2.5 2.5 0 11-5 0 2.5 2.5 0 015 0zm1.43.75a4.002 4.002 0 01-7.86 0H.75a.75.75 0 110-1.5h3.32a4.002 4.002 0 017.86 0h3.32a.75.75 0 110 1.5h-3.32z",
    "pr": "M7.177 3.073L9.573.677A.25.25 0 0110 .854v4.792a.25.25 0 01-.427.177L7.177 3.427a.25.25 0 010-.354zM3.75 2.5a.75.75 0 100 1.5.75.75 0 000-1.5zm-2.25.75a2.25 2.25 0 113 2.122v5.256a2.251 2.251 0 11-1.5 0V5.372A2.25 2.25 0 011.5 3.25zM11 2.5h-1V4h1a1 1 0 011 1v5.628a2.251 2.251 0 101.5 0V5A2.5 2.5 0 0011 2.5zm1 10.25a.75.75 0 111.5 0 .75.75 0 01-1.5 0zM3.75 12a.75.75 0 100 1.5.75.75 0 000-1.5z",
    "issue": "M8 9.5a1.5 1.5 0 100-3 1.5 1.5 0 000 3z M8 0a8 8 0 100 16A8 8 0 008 0zM1.5 8a6.5 6.5 0 1113 0 6.5 6.5 0 01-13 0z",
    "repo": "M2 2.5A2.5 2.5 0 014.5 0h8.75a.75.75 0 01.75.75v12.5a.75.75 0 01-.75.75h-2.5a.75.75 0 110-1.5h1.75v-2h-8a1 1 0 00-.714 1.7.75.75 0 01-1.072 1.05A2.495 2.495 0 012 11.5v-9zm10.5-1V9h-8c-.356 0-.694.074-1 .208V2.5a1 1 0 011-1h8zM5 12.25v3.25a.25.25 0 00.4.2l1.45-1.087a.25.25 0 01.3 0L8.6 15.7a.25.25 0 00.4-.2v-3.25a.25.25 0 00-.25-.25h-3.5a.25.25 0 00-.25.25z",
}

RANK_LEVELS = ["S", "A+", "A", "A-", "B+", "B", "B-", "C+", "C"]
RANK_THRESHOLDS = [1, 12.5, 25, 37.5, 50, 62.5, 75, 87.5, 100]


def gql(query: str, variables: dict) -> dict:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("GH_TOKEN (or GITHUB_TOKEN) is required")
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        API,
        data=body,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": f"refresh_stats.py (github.com/{USER})",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"GitHub API {exc.code}: {exc.read()[:400]!r}") from exc
    if "errors" in payload:
        raise RuntimeError(f"GraphQL errors: {payload['errors']}")
    return payload["data"]


PROFILE_QUERY = """
query($login: String!, $after: String) {
  user(login: $login) {
    name
    login
    createdAt
    followers { totalCount }
    pullRequests { totalCount }
    issues { totalCount }
    repositories(first: 100, after: $after, ownerAffiliations: OWNER, isFork: false,
                 orderBy: {field: STARGAZERS, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        name
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""

CONTRIB_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      restrictedContributionsCount
      totalPullRequestReviewContributions
      totalRepositoriesWithContributedCommits
    }
  }
}
"""


def fetch() -> dict:
    repos, after = [], None
    while True:
        user = gql(PROFILE_QUERY, {"login": USER, "after": after})["user"]
        repos.extend(user["repositories"]["nodes"])
        page = user["repositories"]["pageInfo"]
        if not page["hasNextPage"]:
            break
        after = page["endCursor"]

    created = dt.datetime.strptime(user["createdAt"], "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=dt.timezone.utc
    )
    now = dt.datetime.now(dt.timezone.utc)
    commits = reviews = 0
    contributed_to = 0
    # contributionsCollection spans at most one year, so walk year by year
    start = created
    while start < now:
        end = min(start.replace(year=start.year + 1), now)
        c = gql(
            CONTRIB_QUERY,
            {"login": USER, "from": start.isoformat(), "to": end.isoformat()},
        )["user"]["contributionsCollection"]
        commits += c["totalCommitContributions"]
        if COUNT_PRIVATE:
            commits += c["restrictedContributionsCount"]
        reviews += c["totalPullRequestReviewContributions"]
        # the label says "last year", so keep the most recent window, not the max
        contributed_to = c["totalRepositoriesWithContributedCommits"]
        start = end

    stars = sum(r["stargazerCount"] for r in repos)
    langs: dict[str, dict] = {}
    for repo in repos:
        if repo["name"].lower() in EXCLUDE_REPOS:
            continue
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            if name.lower() in HIDE_LANGS:
                continue
            entry = langs.setdefault(name, {"size": 0, "color": edge["node"]["color"] or "#858585"})
            entry["size"] += edge["size"]

    return {
        "name": user["name"] or user["login"],
        "stars": stars,
        "commits": commits,
        "prs": user["pullRequests"]["totalCount"],
        "issues": user["issues"]["totalCount"],
        "reviews": reviews,
        "followers": user["followers"]["totalCount"],
        "contributed_to": contributed_to,
        "langs": sorted(langs.items(), key=lambda kv: kv[1]["size"], reverse=True),
    }


def rank(s: dict) -> tuple[str, float]:
    """Reimplementation of github-readme-stats' calculateRank.js."""
    exp_cdf = lambda x: 1 - 2 ** -x                      # noqa: E731
    log_normal_cdf = lambda x: x / (1 + x)               # noqa: E731
    medians = {"commits": 1000, "prs": 50, "issues": 25, "reviews": 2, "stars": 50, "followers": 10}
    weights = {"commits": 2, "prs": 3, "issues": 1, "reviews": 1, "stars": 4, "followers": 1}
    total = sum(weights.values())
    score = (
        weights["commits"] * exp_cdf(s["commits"] / medians["commits"])
        + weights["prs"] * exp_cdf(s["prs"] / medians["prs"])
        + weights["issues"] * exp_cdf(s["issues"] / medians["issues"])
        + weights["reviews"] * exp_cdf(s["reviews"] / medians["reviews"])
        + weights["stars"] * log_normal_cdf(s["stars"] / medians["stars"])
        + weights["followers"] * log_normal_cdf(s["followers"] / medians["followers"])
    ) / total
    percentile = (1 - score) * 100
    level = next(
        RANK_LEVELS[i] for i, t in enumerate(RANK_THRESHOLDS) if percentile <= t
    )
    return level, percentile


def esc(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def card(width: int, height: int, title: str, body: str) -> str:
    """Frame shared by both cards. Presentation attributes only, no <style>:
    GitHub sanitises SVGs it serves, and inline CSS/animation does not survive."""
    return f"""<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" \
xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{esc(title)}">
  <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="4.5" fill="{BG}" stroke="{BORDER}"/>
  <text x="25" y="35" fill="{TITLE}" font-family="{FONT}" font-size="18" font-weight="600">{esc(title)}</text>
{body}
</svg>
"""


def render_stats(s: dict) -> str:
    level, percentile = rank(s)
    rows = [
        ("star", "Total Stars Earned", s["stars"]),
        ("commit", "Total Commits", s["commits"]),
        ("pr", "Total PRs", s["prs"]),
        ("issue", "Total Issues", s["issues"]),
        ("repo", "Contributed to (last year)", s["contributed_to"]),
    ]
    body = []
    y = 68
    for key, label, value in rows:
        body.append(
            f'  <g transform="translate(25,{y})">'
            f'<path d="{ICONS[key]}" fill="{ICON}" transform="translate(0,-12) scale(0.9)"/>'
            f'<text x="25" y="0" fill="{TEXT}" font-family="{FONT}" font-size="14" font-weight="400">{label}:</text>'
            f'<text x="285" y="0" fill="{TEXT}" font-family="{FONT}" font-size="14" font-weight="600" '
            f'text-anchor="end">{value:,}</text></g>'
        )
        y += 25

    # rank ring: 100% of the circumference is the top of the field, so fill 100 - percentile
    r = 40
    circ = 2 * math.pi * r
    progress = circ * (1 - min(max(percentile, 0), 100) / 100)
    ring = (
        f'  <g transform="translate(400,110)">'
        f'<circle r="{r}" fill="none" stroke="{TEXT}" stroke-opacity="0.2" stroke-width="6"/>'
        f'<circle r="{r}" fill="none" stroke="{TITLE}" stroke-width="6" stroke-linecap="round" '
        f'stroke-dasharray="{progress:.1f} {circ:.1f}" transform="rotate(-90)"/>'
        f'<text y="9" text-anchor="middle" fill="{TITLE}" font-family="{FONT}" font-size="26" '
        f'font-weight="700">{level}</text></g>'
    )
    body.append(ring)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    body.append(
        f'  <text x="470" y="188" text-anchor="end" fill="{TEXT}" fill-opacity="0.45" '
        f'font-family="{FONT}" font-size="9">updated {stamp}</text>'
    )
    return card(495, 200, f"{s['name']}'s GitHub Stats", "\n".join(body))


def render_langs(s: dict) -> str:
    langs = s["langs"][:LANGS_COUNT]
    if not langs:
        raise RuntimeError("no languages returned")
    total = sum(v["size"] for _, v in langs)
    shares = [(name, v["color"], v["size"] / total * 100) for name, v in langs]

    body = []
    bar_x, bar_w, bar_y = 25, 445, 55
    x = bar_x
    bar = [f'  <g transform="translate(0,0)"><rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="8" rx="4" fill="{BORDER}"/>']
    for i, (_, color, pct) in enumerate(shares):
        w = bar_w * pct / 100
        # square the inner joins so the segments read as one continuous bar
        rx = 4 if i in (0, len(shares) - 1) else 0
        bar.append(f'<rect x="{x:.1f}" y="{bar_y}" width="{max(w, 1):.1f}" height="8" rx="{rx}" fill="{color}"/>')
        x += w
    bar.append("</g>")
    body.append("".join(bar))

    y = 90
    for i, (name, color, pct) in enumerate(shares):
        col_x = 25 if i % 2 == 0 else 260
        row_y = y + (i // 2) * 25
        body.append(
            f'  <g transform="translate({col_x},{row_y})">'
            f'<circle cx="5" cy="-4" r="5" fill="{color}"/>'
            f'<text x="18" y="0" fill="{TEXT}" font-family="{FONT}" font-size="12" font-weight="400">'
            f'{esc(name)} {pct:.2f}%</text></g>'
        )
    height = 90 + ((len(shares) + 1) // 2) * 25 + 10
    return card(495, height, "Most Used Languages", "\n".join(body))


def write(path: pathlib.Path, svg: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text() == svg:
        print(f"{path}: no change")
        return
    path.write_text(svg)
    print(f"wrote {path} ({len(svg)} bytes)")


def main() -> int:
    s = fetch()
    level, percentile = rank(s)
    print(
        f"{s['name']}: {s['commits']:,} commits, {s['stars']:,} stars, {s['prs']} PRs, "
        f"{s['issues']} issues, rank {level} (top {percentile:.1f}%)"
    )
    write(STATS_ASSET, render_stats(s))
    write(LANGS_ASSET, render_langs(s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
