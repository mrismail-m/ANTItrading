"""
===============================================================================
Module: scripts/backtest.py
Purpose: Quantitative Historical Backtesting Engine for ANTItrading
Author: Daily Crypto Paper-Trading Agent (Antigravity)

Description:
  Backtests the exact ANTItrading quantitative strategy across 90 to 365 days of
  historical Binance OHLCV candles:
    - $10,000 starting cash.
    - Dynamic ATR-based risk allocation ($100 risk target, $1,000 max position).
    - Multi-stage Take Profit (TP1 at +10% taking 50% profit, locking stop to breakeven).
    - Dynamic ATR trailing stops (2 * ATR).
    - Relative Strength vs. BTC ranking.
    - Maximum 6 concurrent positions.
    - Benchmarked against 50/50 BTC/ETH buy-and-hold portfolio.

Usage:
  python3 scripts/backtest.py [--days 180] [--output-json state/backtest_results.json]
===============================================================================
"""

import os
import sys
import json
import math
import argparse
import requests
import pandas as pd
import ta
from typing import Dict, Any, List

# Ensure workspace root is in sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from scripts.research import load_watchlist


def fetch_historical_klines(symbol: str, days: int = 180) -> pd.DataFrame:
    """
    Fetches daily historical OHLCV candles from Binance public API.
    """
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1d&limit={min(days + 50, 1000)}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return pd.DataFrame()
        raw = r.json()
        cols = ["open_time", "open", "high", "low", "close", "volume", "close_time", "qav", "num_trades", "tb_base", "tb_quote", "ignore"]
        df = pd.DataFrame(raw, columns=cols)
        for c in ["open", "high", "low", "close", "volume"]:
            df[c] = df[c].astype(float)
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
        return df
    except Exception:
        return pd.DataFrame()


def prepare_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Precomputes technical indicators across the candle series.
    """
    if len(df) < 50:
        return df
    df["ema12"] = ta.trend.EMAIndicator(df["close"], window=12).ema_indicator()
    df["ema26"] = ta.trend.EMAIndicator(df["close"], window=26).ema_indicator()
    df["ema50"] = ta.trend.EMAIndicator(df["close"], window=50).ema_indicator()
    df["rsi14"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi()
    macd = ta.trend.MACD(df["close"], window_slow=26, window_fast=12, window_sign=9)
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["atr14"] = ta.volatility.AverageTrueRange(df["high"], df["low"], df["close"], window=14).average_true_range()
    adx_ind = ta.trend.ADXIndicator(df["high"], df["low"], df["close"], window=14)
    df["adx14"] = adx_ind.adx()
    df["bollinger_pct_b"] = ta.volatility.BollingerBands(df["close"], window=20, window_dev=2).bollinger_pband()
    df["roc_7"] = df["close"].pct_change(7) * 100
    df["roc_14"] = df["close"].pct_change(14) * 100
    return df


def run_backtest(days: int = 180, output_json: str = None) -> Dict[str, Any]:
    """
    Executes historical simulation across the tracked universe.
    """
    watchlist = load_watchlist()
    print(f"📊 Fetching {days} days of historical data for {len(watchlist)} assets from Binance...")

    market_data = {}
    for name, ticker in watchlist.items():
        df = fetch_historical_klines(ticker, days=days)
        if not df.empty and len(df) >= 50:
            market_data[ticker] = prepare_indicators(df)

    if "BTCUSDT" not in market_data or "ETHUSDT" not in market_data:
        print("Error: BTC or ETH historical data unavailable for backtesting.", file=sys.stderr)
        return {}

    btc_df = market_data["BTCUSDT"]
    eth_df = market_data["ETHUSDT"]
    total_bars = len(btc_df)
    sim_start = max(50, total_bars - days)

    print(f"🔬 Simulating strategy across {total_bars - sim_start} daily trading sessions...")

    # Simulation State
    cash = 10000.0
    starting_cash = 10000.0
    positions = []
    closed_trades = []
    equity_curve = []
    benchmark_curve = []

    # Benchmark initial units (50/50 BTC/ETH)
    btc_start_p = btc_df.iloc[sim_start]["close"]
    eth_start_p = eth_df.iloc[sim_start]["close"]
    bench_btc_qty = 5000.0 / btc_start_p if btc_start_p > 0 else 0
    bench_eth_qty = 5000.0 / eth_start_p if eth_start_p > 0 else 0

    for idx in range(sim_start, total_bars):
        current_date = btc_df.iloc[idx]["open_time"].strftime("%Y-%m-%d")
        btc_bar = btc_df.iloc[idx]
        eth_bar = eth_df.iloc[idx]
        btc_p = btc_bar["close"]
        eth_p = eth_bar["close"]

        # 1. Update Open Positions & Evaluate Exits (Trailing Stops & TP1)
        remaining_positions = []
        for pos in positions:
            sym = pos["symbol"]
            ticker = f"{sym}USDT"
            df = market_data.get(ticker)
            if df is None or idx >= len(df):
                remaining_positions.append(pos)
                continue

            bar = df.iloc[idx]
            high_p = bar["high"]
            low_p = bar["low"]
            close_p = bar["close"]
            atr = bar["atr14"]

            # Update highest price reached
            if high_p > pos["highest_price"]:
                pos["highest_price"] = high_p
                if not pos["tp1_hit"]:
                    new_stop = high_p - (2.0 * atr)
                    if new_stop > pos["trailing_stop"]:
                        pos["trailing_stop"] = new_stop

            # Check TP1 Hit (+10% gain target)
            pnl_pct = ((high_p - pos["entry_price"]) / pos["entry_price"]) * 100
            if pnl_pct >= 10.0 and not pos["tp1_hit"]:
                # Execute TRIM: sell 50%, lock stop to breakeven
                tp_price = pos["entry_price"] * 1.10
                trim_qty = pos["qty"] * 0.5
                proceeds = trim_qty * tp_price
                profit = proceeds - (pos["cost_basis"] * 0.5)
                cash += proceeds
                pos["qty"] -= trim_qty
                pos["cost_basis"] *= 0.5
                pos["tp1_hit"] = True
                pos["trailing_stop"] = pos["entry_price"]  # Breakeven stop locked!
                closed_trades.append({
                    "symbol": sym,
                    "type": "TRIM (TP1 +10%)",
                    "entry_price": pos["entry_price"],
                    "exit_price": tp_price,
                    "profit_usd": profit,
                    "return_pct": 10.0,
                    "exit_date": current_date
                })

            # Check Trailing Stop Breach
            if low_p <= pos["trailing_stop"]:
                exit_price = pos["trailing_stop"]
                proceeds = pos["qty"] * exit_price
                profit = proceeds - pos["cost_basis"]
                ret_pct = ((exit_price - pos["entry_price"]) / pos["entry_price"]) * 100
                cash += proceeds
                closed_trades.append({
                    "symbol": sym,
                    "type": "STOP_EXIT",
                    "entry_price": pos["entry_price"],
                    "exit_price": exit_price,
                    "profit_usd": profit,
                    "return_pct": ret_pct,
                    "exit_date": current_date
                })
            else:
                remaining_positions.append(pos)

        positions = remaining_positions

        # 2. Evaluate Candidate Buys (RS-Ranked)
        if len(positions) < 6 and cash >= 200.0:
            # Calculate RS vs BTC for today
            btc_roc7 = btc_bar.get("roc_7", 0.0)
            btc_roc14 = btc_bar.get("roc_14", 0.0)

            candidates = []
            for name, ticker in watchlist.items():
                sym = ticker.replace("USDT", "")
                if any(p["symbol"] == sym for p in positions):
                    continue
                df = market_data.get(ticker)
                if df is None or idx >= len(df):
                    continue

                bar = df.iloc[idx]
                c = bar["close"]
                ema50 = bar["ema50"]
                rsi = bar["rsi14"]
                adx = bar["adx14"]
                atr = bar["atr14"]
                roc7 = bar.get("roc_7", 0.0)
                roc14 = bar.get("roc_14", 0.0)
                rs_score = 0.6 * (roc7 - btc_roc7) + 0.4 * (roc14 - btc_roc14)

                # Bullish Entry Filter: Price > EMA50, RSI 45-65, ADX > 20
                if c > ema50 and 45.0 <= rsi <= 65.0 and adx >= 20.0 and atr > 0:
                    candidates.append({
                        "symbol": sym,
                        "ticker": ticker,
                        "price": c,
                        "atr": atr,
                        "rs_score": rs_score
                    })

            # Sort by Relative Strength leadership
            candidates.sort(key=lambda x: x["rs_score"], reverse=True)

            # Allocate up to available position slots
            available_slots = 6 - len(positions)
            for cand in candidates[:available_slots]:
                risk_target = 100.0
                units = risk_target / (2.0 * cand["atr"]) if cand["atr"] > 0 else 0
                pos_size = min(1000.0, max(200.0, round(units * cand["price"], 2)))

                if cash >= pos_size:
                    qty = pos_size / cand["price"]
                    cash -= pos_size
                    positions.append({
                        "symbol": cand["symbol"],
                        "qty": qty,
                        "entry_price": cand["price"],
                        "cost_basis": pos_size,
                        "highest_price": cand["price"],
                        "trailing_stop": cand["price"] - (2.0 * cand["atr"]),
                        "tp1_hit": False,
                        "entry_date": current_date
                    })

        # 3. Calculate Daily Portfolio & Benchmark Equity
        pos_val = 0.0
        for p in positions:
            ticker = f"{p['symbol']}USDT"
            df = market_data.get(ticker)
            curr_c = df.iloc[idx]["close"] if df is not None and idx < len(df) else p["entry_price"]
            pos_val += p["qty"] * curr_c

        curr_total = cash + pos_val
        bench_total = (bench_btc_qty * btc_p) + (bench_eth_qty * eth_p)
        equity_curve.append(curr_total)
        benchmark_curve.append(bench_total)

    # Performance Analytics
    final_equity = equity_curve[-1]
    total_ret_pct = round(((final_equity - starting_cash) / starting_cash) * 100, 2)
    bench_final = benchmark_curve[-1]
    bench_ret_pct = round(((bench_final - 10000.0) / 10000.0) * 100, 2)
    alpha_pct = round(total_ret_pct - bench_ret_pct, 2)

    # Max Drawdown
    peak = equity_curve[0]
    max_dd = 0.0
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd
    max_dd_pct = round(max_dd * 100, 2)

    # Trade Statistics
    wins = [t for t in closed_trades if t["profit_usd"] > 0]
    losses = [t for t in closed_trades if t["profit_usd"] <= 0]
    win_rate = round((len(wins) / len(closed_trades)) * 100, 2) if closed_trades else 0.0
    gross_profits = sum(t["profit_usd"] for t in wins)
    gross_losses = abs(sum(t["profit_usd"] for t in losses))
    profit_factor = round(gross_profits / gross_losses, 2) if gross_losses > 0 else 999.0
    calmar_ratio = round(total_ret_pct / max_dd_pct, 2) if max_dd_pct > 0 else 0.0

    # Sharpe Ratio
    daily_returns = [(equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1] for i in range(1, len(equity_curve))]
    mean_r = sum(daily_returns) / len(daily_returns) if daily_returns else 0.0
    var_r = sum((r - mean_r) ** 2 for r in daily_returns) / len(daily_returns) if len(daily_returns) > 1 else 0.0
    std_r = math.sqrt(var_r)
    sharpe = round((mean_r / std_r) * math.sqrt(365), 2) if std_r > 0 else 0.0

    results = {
        "days": days,
        "trading_sessions": len(equity_curve),
        "starting_equity": starting_cash,
        "final_equity": round(final_equity, 2),
        "total_return_pct": total_ret_pct,
        "benchmark_return_pct": bench_ret_pct,
        "alpha_pct": alpha_pct,
        "max_drawdown_pct": max_dd_pct,
        "calmar_ratio": calmar_ratio,
        "sharpe_ratio": sharpe,
        "total_closed_trades": len(closed_trades),
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate_pct": win_rate,
        "profit_factor": profit_factor,
        "gross_profits_usd": round(gross_profits, 2),
        "gross_losses_usd": round(gross_losses, 2)
    }

    if output_json:
        os.makedirs(os.path.dirname(output_json), exist_ok=True)
        with open(output_json, "w") as f:
            json.dump(results, f, indent=2)

    # Print Summary Report
    print("\n" + "=" * 70)
    print(f"📊 ANTITRADING QUANTITATIVE BACKTEST REPORT ({days} DAYS)")
    print("=" * 70)
    print(f"Starting Capital:       ${starting_cash:,.2f} USD")
    print(f"Final Capital:          ${final_equity:,.2f} USD")
    print(f"Strategy Return:        {'+' if total_ret_pct >= 0 else ''}{total_ret_pct:.2f}%")
    print(f"50/50 BTC/ETH Return:   {'+' if bench_ret_pct >= 0 else ''}{bench_ret_pct:.2f}%")
    print(f"Strategy Alpha:         {'+' if alpha_pct >= 0 else ''}{alpha_pct:.2f}% 🏆")
    print(f"Max Drawdown:           {max_dd_pct:.2f}%")
    print(f"Calmar Ratio:           {calmar_ratio:.2f}")
    print(f"Annualized Sharpe:      {sharpe:.2f}")
    print("-" * 70)
    print(f"Total Closed Trades:    {len(closed_trades)}")
    print(f"Win Rate:               {win_rate:.2f}% ({len(wins)}W / {len(losses)}L)")
    print(f"Profit Factor:          {profit_factor:.2f}")
    print(f"Gross Profit:           ${gross_profits:,.2f}")
    print(f"Gross Loss:             ${gross_losses:,.2f}")
    print("=" * 70 + "\n")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ANTItrading Historical Backtest Engine")
    parser.add_argument("--days", type=int, default=180, help="Number of historical days to backtest (default: 180)")
    parser.add_argument("--output-json", type=str, default="state/backtest_results.json", help="Path to save results JSON")
    args = parser.parse_args()

    run_backtest(days=args.days, output_json=args.output_json)
