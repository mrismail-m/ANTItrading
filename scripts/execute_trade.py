"""
===============================================================================
Module: scripts/execute_trade.py
Purpose: State Management & Trade Execution Sync Utility
Author: Daily Crypto Paper-Trading Agent (Antigravity)

Description:
  This script provides utility functions to safely execute paper trades and update
  persistent workspace files:
    1. `state/portfolio.json`: Updates cash balance and active position array.
    2. `state/trade_log.csv`: Appends structured decision rows including technical indicator snapshots.
    3. `state/human_open_positions.csv`: Syncs human-friendly open positions view.
    4. `state/human_closed_trades.csv`: Syncs human-friendly closed trades log.
    5. `state/human_decision_log.csv`: Syncs human-friendly decision history.

Usage:
  python3 scripts/execute_trade.py --input-json decisions.json

Input JSON format:
  {
    "timestamp": "2026-08-30T13:25:00+00:00",
    "decisions": [
      {
        "symbol": "BTC",
        "action": "HOLD",
        "price": 78176.57,
        "qty": 0.0,
        "cost_or_proceeds": 0.0,
        "reasoning": "...",
        "confidence": 0.80,
        "rsi14": 71.26,
        "ema12": 76129.39,
        "ema26": 72227.32,
        "ema50": 69365.83,
        "macd": 3902.06,
        "macd_signal": 3394.81,
        "momentum_10": 7.05,
        "volume_ratio": 0.09,
        "divergence": "none",
        "trend_bias": "bullish",
        "news_sentiment": "bullish",
        "event_risk": "none"
      }
    ]
  }
===============================================================================
"""

import json
import os
import csv
import sys
import datetime


def load_portfolio(filepath="state/portfolio.json"):
    """Loads current portfolio state from state/portfolio.json."""
    if not os.path.exists(filepath):
        return {"cash": 10000.0, "starting_cash": 10000.0, "positions": [], "trade_counter": 0}
    with open(filepath, "r") as f:
        return json.load(f)


def save_portfolio(portfolio, filepath="state/portfolio.json"):
    """Saves updated portfolio dictionary to state/portfolio.json."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(portfolio, f, indent=2)


def append_trade_log(decisions, cash_after, filepath="state/trade_log.csv"):
    """
    Appends decision records to state/trade_log.csv.

    :param decisions: List of decision dicts with TA & reasoning attributes
    :param cash_after: Updated portfolio cash after decisions
    :param filepath: Path to trade_log.csv
    """
    fieldnames = [
        "timestamp", "symbol", "action", "price", "qty", "cost_or_proceeds",
        "reasoning", "confidence", "cash_after", "rsi14", "ema12", "ema26",
        "ema50", "macd", "macd_signal", "momentum_10", "volume_ratio",
        "divergence", "trend_bias", "news_sentiment", "event_risk",
        "btc_correlation", "funding_rate", "onchain_signal", "social_trend",
        "adx14", "vwap", "oi_change_24h", "taker_ratio", "suggested_pos_size"
    ]

    file_exists = os.path.exists(filepath)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    with open(filepath, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()

        for d in decisions:
            row = {
                "timestamp": d.get("timestamp", datetime.datetime.now(datetime.timezone.utc).isoformat()),
                "symbol": d.get("symbol"),
                "action": d.get("action"),
                "price": f"{d.get('price'):.4f}" if isinstance(d.get("price"), (int, float)) else d.get("price"),
                "qty": f"{d.get('qty'):.6f}" if isinstance(d.get("qty"), (int, float)) else d.get("qty"),
                "cost_or_proceeds": f"{d.get('cost_or_proceeds'):.2f}" if isinstance(d.get("cost_or_proceeds"), (int, float)) else d.get("cost_or_proceeds"),
                "reasoning": d.get("reasoning"),
                "confidence": f"{d.get('confidence'):.2f}" if isinstance(d.get("confidence"), (int, float)) else d.get("confidence"),
                "cash_after": f"{cash_after:.2f}",
                "rsi14": d.get("rsi14"),
                "ema12": d.get("ema12"),
                "ema26": d.get("ema26"),
                "ema50": d.get("ema50"),
                "macd": d.get("macd"),
                "macd_signal": d.get("macd_signal"),
                "momentum_10": d.get("momentum_10"),
                "volume_ratio": d.get("volume_ratio"),
                "divergence": d.get("divergence"),
                "trend_bias": d.get("trend_bias"),
                "news_sentiment": d.get("news_sentiment"),
                "event_risk": d.get("event_risk"),
                "btc_correlation": d.get("btc_correlation", 1.0),
                "funding_rate": d.get("funding_rate", 0.0),
                "onchain_signal": d.get("onchain_signal", "no_signal"),
                "social_trend": d.get("social_trend", "normal"),
                "adx14": d.get("adx14"),
                "vwap": d.get("vwap"),
                "oi_change_24h": d.get("oi_change_24h"),
                "taker_ratio": d.get("taker_ratio"),
                "suggested_pos_size": d.get("suggested_pos_size")
            }
            writer.writerow(row)


def sync_human_views(portfolio, decisions, open_pos_path="state/human_open_positions.csv", decision_log_path="state/human_decision_log.csv"):
    """
    Updates human-readable CSV views for Open Positions and Decision Log.

    :param portfolio: Current portfolio dictionary
    :param decisions: List of today's decision dictionaries
    """
    # 1. Update Open Positions CSV
    with open(open_pos_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["trade_id", "symbol", "entry_price", "qty", "cost_basis", "date_opened", "status"])
        for idx, pos in enumerate(portfolio.get("positions", []), start=1):
            writer.writerow([
                f"TRADE-{idx:03d}",
                pos.get("symbol"),
                f"{pos.get('entry_price'):.4f}",
                f"{pos.get('qty'):.6f}",
                f"{pos.get('cost_basis'):.2f}",
                pos.get("opened_at"),
                "OPEN"
            ])

    # 2. Append to Human Decision Log CSV
    human_fields = [
        "timestamp", "symbol", "action", "price", "rsi14", "trend_bias",
        "divergence", "news_sentiment", "event_risk", "reasoning", "confidence"
    ]
    file_exists = os.path.exists(decision_log_path)
    with open(decision_log_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=human_fields)
        if not file_exists:
            writer.writeheader()

        for d in decisions:
            row = {
                "timestamp": d.get("timestamp", datetime.datetime.now(datetime.timezone.utc).isoformat()),
                "symbol": d.get("symbol"),
                "action": d.get("action"),
                "price": f"{d.get('price'):.4f}" if isinstance(d.get("price"), (int, float)) else d.get("price"),
                "rsi14": d.get("rsi14"),
                "trend_bias": d.get("trend_bias"),
                "divergence": d.get("divergence"),
                "news_sentiment": d.get("news_sentiment"),
                "event_risk": d.get("event_risk"),
                "reasoning": d.get("reasoning"),
                "confidence": f"{d.get('confidence'):.2f}" if isinstance(d.get("confidence"), (int, float)) else d.get("confidence")
            }
            writer.writerow(row)


def execute_trade_pass(payload):
    """
    Executes trades in payload and updates all state files.

    :param payload: Dictionary containing timestamp and list of decisions
    """
    portfolio = load_portfolio()
    decisions = payload.get("decisions", [])
    now = payload.get("timestamp", datetime.datetime.now(datetime.timezone.utc).isoformat())

    for d in decisions:
        d["timestamp"] = now
        action = d.get("action", "HOLD").upper()
        symbol = d.get("symbol")
        price = float(d.get("price", 0))
        amount_usd = float(d.get("amount_usd", 0))

        if action == "BUY" and amount_usd > 0 and price > 0:
            if portfolio["cash"] >= amount_usd:
                qty = amount_usd / price
                d["qty"] = qty
                d["cost_or_proceeds"] = -amount_usd

                portfolio["cash"] -= amount_usd
                portfolio["trade_counter"] += 1
                portfolio["positions"].append({
                    "symbol": symbol,
                    "qty": qty,
                    "entry_price": price,
                    "cost_basis": amount_usd,
                    "opened_at": now
                })
            else:
                print(f"Warning: Insufficient cash for {symbol} BUY trade.", file=sys.stderr)

        elif action == "SELL":
            # Locate matching position
            matching_positions = [p for p in portfolio["positions"] if p["symbol"] == symbol]
            if matching_positions:
                pos = matching_positions[0]
                proceeds = pos["qty"] * price
                d["qty"] = pos["qty"]
                d["cost_or_proceeds"] = proceeds
                portfolio["cash"] += proceeds
                portfolio["positions"].remove(pos)
            else:
                print(f"Warning: No open position found for {symbol} SELL.", file=sys.stderr)
        else:
            d["qty"] = 0.0
            d["cost_or_proceeds"] = 0.0

    save_portfolio(portfolio)
    append_trade_log(decisions, portfolio["cash"])
    sync_human_views(portfolio, decisions)

    return portfolio


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--input-json":
        with open(sys.argv[2], "r") as f:
            data = json.load(f)
        updated_port = execute_trade_pass(data)
        print(json.dumps(updated_port, indent=2))
    else:
        print("Usage: python3 scripts/execute_trade.py --input-json <path_to_decisions_json>")
