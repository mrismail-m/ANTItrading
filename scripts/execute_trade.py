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


def compute_portfolio_analytics(portfolio):
    """
    Computes rolling Sharpe Ratio, Sortino Ratio, Maximum Drawdown %, Calmar Ratio, and Benchmark comparison.
    Samples daily close equity across unique dates to prevent intra-day execution timestamps from distorting annualization.

    :param portfolio: Portfolio dictionary
    :return: Updated metrics sub-dictionary
    """
    import math

    starting_cash = portfolio.get("starting_cash", 10000.0)
    history = portfolio.get("equity_history", [])

    if len(history) < 2:
        return {
            "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0,
            "max_drawdown_pct": 0.0,
            "calmar_ratio": 0.0,
            "benchmark_return_pct": 0.0
        }

    # Group equity history by calendar date (taking the latest snapshot of each unique day)
    daily_equity_map = {}
    for h in history:
        ts = h.get("timestamp", "")
        date_key = ts[:10] if len(ts) >= 10 else ts
        daily_equity_map[date_key] = h.get("portfolio_value", starting_cash)

    daily_values = list(daily_equity_map.values())

    # If multiple days of history exist, compute daily returns; otherwise use consecutive snapshots
    if len(daily_values) >= 2:
        eval_values = daily_values
    else:
        eval_values = [h.get("portfolio_value", starting_cash) for h in history]

    returns = [(eval_values[i] - eval_values[i - 1]) / eval_values[i - 1] for i in range(1, len(eval_values))]

    if returns and len(returns) >= 2:
        mean_ret = sum(returns) / len(returns)
        variance = sum((r - mean_ret) ** 2 for r in returns) / len(returns)
        std_dev = math.sqrt(variance)
        sharpe = round((mean_ret / std_dev) * math.sqrt(365), 2) if std_dev > 0 else 0.0

        downside = [r for r in returns if r < 0]
        downside_var = sum(r ** 2 for r in downside) / len(returns) if downside else 0
        downside_std = math.sqrt(downside_var)
        sortino = round((mean_ret / downside_std) * math.sqrt(365), 2) if downside_std > 0 else 0.0
    elif returns and len(returns) == 1:
        # Initial sample - report stable non-annualized ratio
        sharpe = round(returns[0] * 100, 2)
        sortino = sharpe
    else:
        sharpe, sortino = 0.0, 0.0

    # Max Drawdown across all historical snapshots (high-watermark)
    all_values = [h.get("portfolio_value", starting_cash) for h in history]
    peak = all_values[0]
    max_dd = 0.0
    for v in all_values:
        if v > peak:
            peak = v
        dd = (peak - v) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd

    max_dd_pct = round(max_dd * 100, 2)
    total_ret = (all_values[-1] - starting_cash) / starting_cash if starting_cash > 0 else 0
    calmar = round(total_ret / max_dd, 2) if max_dd > 0 else 0.0

    bench_initial = history[0].get("benchmark_value", starting_cash)
    bench_current = history[-1].get("benchmark_value", starting_cash)
    bench_ret_pct = round(((bench_current - bench_initial) / bench_initial) * 100, 2) if bench_initial > 0 else 0.0

    return {
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "max_drawdown_pct": max_dd_pct,
        "calmar_ratio": calmar,
        "benchmark_return_pct": bench_ret_pct
    }


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
        "adx14", "vwap", "oi_change_24h", "taker_ratio", "ob_imbalance_2pct",
        "whale_alert", "market_regime", "suggested_pos_size"
    ]

    file_exists = os.path.exists(filepath)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    with open(filepath, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
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
                "ob_imbalance_2pct": d.get("ob_imbalance_2pct"),
                "whale_alert": d.get("whale_alert", "NEUTRAL_FLOW"),
                "market_regime": d.get("market_regime", "neutral"),
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
                "RUNNER (TP1)" if pos.get("tp1_hit", False) else "OPEN"
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

    prices_map = {}
    atr_map = {}
    chandelier_map = {}

    for d in decisions:
        d["timestamp"] = now
        action = d.get("action", "HOLD").upper()
        symbol = d.get("symbol")
        price = float(d.get("price", 0))
        amount_usd = float(d.get("amount_usd", 0))
        atr14 = float(d.get("atr14", 0))
        chand_stop = float(d.get("chandelier_stop", 0))

        if price > 0:
            prices_map[symbol] = price
        if atr14 > 0:
            atr_map[symbol] = atr14
        if chand_stop > 0:
            chandelier_map[symbol] = chand_stop

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
                    "highest_price": price,
                    "trailing_stop_price": round(price - (2.0 * atr14) if atr14 > 0 else price * 0.93, 4),
                    "opened_at": now
                })
            else:
                print(f"Warning: Insufficient cash for {symbol} BUY trade.", file=sys.stderr)

        elif action == "TRIM":
            # Partial Take Profit (Sell 50% at TP1 target, bank profit, lock stop to breakeven)
            matching_positions = [p for p in portfolio["positions"] if p["symbol"] == symbol]
            if matching_positions:
                pos = matching_positions[0]
                trim_qty = pos["qty"] * 0.5
                proceeds = trim_qty * price
                d["qty"] = trim_qty
                d["cost_or_proceeds"] = proceeds

                pos["qty"] -= trim_qty
                pos["cost_basis"] = round(pos["cost_basis"] * 0.5, 2)
                pos["tp1_hit"] = True
                # Lock stop to breakeven minimum
                pos["trailing_stop_price"] = max(pos.get("trailing_stop_price", 0.0), pos.get("entry_price", price))

                portfolio["cash"] += proceeds
                portfolio["trade_counter"] += 1
            else:
                print(f"Warning: No open position found for {symbol} TRIM.", file=sys.stderr)

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

    # Update trailing stops & highest price for remaining open positions using live ATR(14) and Chandelier Exit
    for pos in portfolio.get("positions", []):
        sym = pos["symbol"]
        if sym in prices_map:
            curr_p = prices_map[sym]
            asset_atr = atr_map.get(sym, curr_p * 0.03)
            if "highest_price" not in pos:
                pos["highest_price"] = pos.get("entry_price", curr_p)
            if curr_p > pos["highest_price"]:
                pos["highest_price"] = curr_p
            if "trailing_stop_price" not in pos:
                pos["trailing_stop_price"] = round(pos["highest_price"] - (2.0 * asset_atr), 4)
            elif curr_p > pos["entry_price"]:
                # Adjust trailing stop upwards if higher peak reached using true ATR(14) Chandelier Exit
                new_stop = round(pos["highest_price"] - (2.0 * asset_atr), 4)
                if pos.get("tp1_hit", False):
                    new_stop = max(new_stop, float(pos.get("entry_price", new_stop)))
                if new_stop > pos["trailing_stop_price"]:
                    pos["trailing_stop_price"] = new_stop

    # Calculate current total portfolio value
    positions_value = sum(p["qty"] * prices_map.get(p["symbol"], p["entry_price"]) for p in portfolio.get("positions", []))
    total_portfolio_value = portfolio["cash"] + positions_value

    # Update Equity History
    if "equity_history" not in portfolio:
        portfolio["equity_history"] = []

    # Dynamic Benchmark calculation (50/50 BTC/ETH starting from $10,000 at inception Aug 30: BTC $78,146, ETH $2,456.70)
    btc_p = prices_map.get("BTC", prices_map.get("BTCUSDT", 77304.16))
    eth_p = prices_map.get("ETH", prices_map.get("ETHUSDT", 2385.88))
    bench_btc_qty = 5000.0 / 78146.00
    bench_eth_qty = 5000.0 / 2456.70
    benchmark_value = (bench_btc_qty * btc_p) + (bench_eth_qty * eth_p)

    portfolio["equity_history"].append({
        "timestamp": now,
        "portfolio_value": round(total_portfolio_value, 2),
        "benchmark_value": round(benchmark_value, 2)
    })

    # Compute & attach portfolio risk & performance metrics
    portfolio["metrics"] = compute_portfolio_analytics(portfolio)

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
