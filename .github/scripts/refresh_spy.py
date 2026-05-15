#!/usr/bin/env python3
"""Refresh assets/spy.png with a 1-month hourly SPY chart pulled from Yahoo Finance.

Finviz's chart.ashx endpoint started returning empty PNGs (content-length: 0) to
hotlinked GitHub Camo requests, so the README image broke. We now render the
chart ourselves from Yahoo's public chart API and commit the PNG.
"""

from __future__ import annotations

import datetime as dt
import io
import pathlib
import sys

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import requests

ASSET = pathlib.Path("assets/spy.png")
YAHOO_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/SPY"
    "?interval=1h&range=1mo&includePrePost=false"
)
HEADERS = {"User-Agent": "Mozilla/5.0 (refresh_spy.py; github.com/yehias21)"}


def fetch_series() -> tuple[list[dt.datetime], list[float]]:
    resp = requests.get(YAHOO_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    result = payload["chart"]["result"][0]
    timestamps = result["timestamp"]
    closes = result["indicators"]["quote"][0]["close"]
    times: list[dt.datetime] = []
    prices: list[float] = []
    for ts, px in zip(timestamps, closes):
        if px is None:
            continue
        times.append(dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc))
        prices.append(float(px))
    if not prices:
        raise RuntimeError("Yahoo returned no usable price points")
    return times, prices


def render(times: list[dt.datetime], prices: list[float]) -> bytes:
    last = prices[-1]
    first = prices[0]
    change = last - first
    pct = change / first * 100.0
    up = change >= 0
    line_color = "#16a34a" if up else "#dc2626"
    fill_color = "#16a34a22" if up else "#dc262622"

    fig, ax = plt.subplots(figsize=(9.0, 3.6), dpi=140)
    fig.patch.set_facecolor("#ffffff")
    ax.set_facecolor("#ffffff")

    ax.plot(times, prices, color=line_color, linewidth=1.6)
    ax.fill_between(times, prices, min(prices), color=fill_color)

    ax.set_title(
        f"SPY  ${last:,.2f}   {('+' if up else '')}{change:,.2f} ({pct:+.2f}%)   1M hourly",
        loc="left",
        fontsize=12,
        fontweight="600",
        color="#0f172a",
        pad=10,
    )

    ax.grid(True, color="#e2e8f0", linewidth=0.6)
    ax.tick_params(colors="#475569", labelsize=9)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color("#cbd5e1")

    locator = mdates.AutoDateLocator(minticks=4, maxticks=8)
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))

    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    fig.text(
        0.995, 0.012, f"Source: Yahoo Finance  ·  refreshed {stamp}",
        ha="right", va="bottom", fontsize=7, color="#94a3b8",
    )

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor())
    plt.close(fig)
    return buf.getvalue()


def main() -> int:
    times, prices = fetch_series()
    png = render(times, prices)
    ASSET.parent.mkdir(parents=True, exist_ok=True)
    if ASSET.exists() and ASSET.read_bytes() == png:
        print("no change")
        return 0
    ASSET.write_bytes(png)
    print(f"wrote {ASSET} ({len(png)} bytes, {len(prices)} points)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
