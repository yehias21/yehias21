#!/usr/bin/env python3
"""Refresh the SPY block in README.md: rotate &v=<timestamp> on the Finviz chart
URL so GitHub's Camo image proxy fetches a fresh image each run."""

from __future__ import annotations

import datetime as dt
import pathlib
import re

README = pathlib.Path("README.md")


def splice(body: str, stamp: str) -> str:
    return re.sub(
        r"(<img[^>]*finviz\.com/chart\.ashx[^\"']*?)(?:&v=\d+)?([\"'])",
        lambda m: f"{m.group(1)}&v={stamp}{m.group(2)}",
        body,
    )


def main() -> int:
    now = dt.datetime.now(dt.timezone.utc)
    stamp = now.strftime("%Y%m%d%H%M")
    text = README.read_text(encoding="utf-8")
    new_text = splice(text, stamp)
    if new_text == text:
        print("no change")
        return 0
    README.write_text(new_text, encoding="utf-8")
    print(f"README updated v={stamp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
