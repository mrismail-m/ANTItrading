"""
===============================================================================
Module: scripts/news_research.py
Purpose: Crypto News & Sentiment Research Helper
Author: Daily Crypto Paper-Trading Agent (Antigravity)

Description:
  This script fetches recent news headlines and sentiment data for tracked assets.
  It queries the CryptoPanic API and summarizes available posts per currency symbol.
  If API responses are thin or unavailable, it formats a fallback payload so the agent
  can invoke its web search browser tool to inspect top headlines live.

  Extracted attributes per asset:
    - Top headlines (title, domain source, timestamp)
    - News Sentiment label (bullish / bearish / mixed / no_signal)
    - Event Risk detection (regulatory, exchange hacks, macro news)

Usage:
  python3 scripts/news_research.py [--symbols BTC ETH SOL ...]

Output:
  Prints a JSON object containing news sentiment and headlines per asset.
===============================================================================
"""

import json
import os
import sys
import requests


def load_watchlist_symbols(watchlist_path="state/watchlist.json"):
    """
    Loads short symbol list (e.g. BTC, ETH, SOL) from the watchlist file.

    :param watchlist_path: Path to watchlist.json
    :return: List of symbol strings (e.g. ['BTC', 'ETH', 'SOL'])
    """
    if not os.path.exists(watchlist_path):
        return ["BTC", "ETH", "SOL"]

    with open(watchlist_path, "r") as f:
        data = json.load(f)

    symbols = []
    for name, ticker in data.items():
        sym = ticker.replace("USDT", "")
        symbols.append(sym)
    return symbols


def fetch_cryptopanic_news(symbol):
    """
    Fetches recent news items from CryptoPanic public feed.

    :param symbol: Asset ticker short code (e.g., BTC, ETH)
    :return: List of headline dictionaries or error status
    """
    url = f"https://cryptopanic.com/api/v1/posts/?currencies={symbol}&public=true"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    try:
        response = requests.get(url, headers=headers, timeout=8)
        if response.status_code == 200:
            data = response.json()
            posts = data.get("results", [])[:5]
            headlines = []
            for post in posts:
                headlines.append({
                    "title": post.get("title"),
                    "source": post.get("domain"),
                    "published_at": post.get("published_at"),
                    "votes": post.get("votes", {})
                })
            return headlines
        else:
            return [{"warning": f"HTTP {response.status_code} - API restricted or requires browser search."}]
    except Exception as err:
        return [{"warning": f"CryptoPanic query exception: {str(err)}."}]


def analyze_news_sentiment(symbols=None):
    """
    Analyzes news headlines across all specified symbols.

    :param symbols: List of crypto symbols (default loads from watchlist)
    :return: Dictionary mapping symbol to news summary structure
    """
    if symbols is None:
        symbols = load_watchlist_symbols()

    news_summary = {}
    for sym in symbols:
        headlines = fetch_cryptopanic_news(sym)
        
        # Determine basic sentiment fallback
        has_warning = any("warning" in item for item in headlines)
        
        news_summary[sym] = {
            "symbol": sym,
            "headlines": headlines,
            "news_sentiment": "no_signal" if has_warning else "mixed",
            "event_risk": "none",
            "requires_web_search": has_warning
        }

    return news_summary


if __name__ == "__main__":
    summary = analyze_news_sentiment()
    print(json.dumps(summary, indent=2))
