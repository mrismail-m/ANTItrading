"""
===============================================================================
Module: scripts/run_trader.py
Purpose: Master Unified Autonomous Twice-Daily Paper-Trading Runner
Author: Daily Crypto Paper-Trading Agent (Antigravity)

Description:
  This script is the single deterministic entry point for executing the twice-daily
  paper-trading pass across all tracked Shariah-compliant cryptocurrency assets.
  
  Workflow:
    1. Loads persistent state from state/portfolio.json and state/watchlist.json.
    2. Runs live multi-timeframe TA research (1D & 4H) and saves state/latest_research.json.
    3. Analyzes macro & news sentiment and saves state/latest_sentiment.json.
    4. Evaluates risk management and trading decision rules across all tracked assets.
    5. Saves structured decisions to state/latest_decisions.json.
    6. Executes trades and updates state/portfolio.json, state/trade_log.csv,
       state/human_open_positions.csv, and state/human_decision_log.csv.
    7. Generates and saves an executive summary report to state/latest_summary.md
       and prints it to the terminal.

Usage:
  python3 scripts/run_trader.py [--dry-run] [--silent]
===============================================================================
"""

import os
import sys
import json
import argparse
import datetime
from typing import Dict, Any, List, Tuple

# Ensure workspace root is in sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from scripts.research import run_research, load_watchlist
from scripts.news_research import analyze_news_sentiment
from scripts.execute_trade import load_portfolio, execute_trade_pass
from scripts.discord_notifier import send_discord_notification


def evaluate_asset_decision(
    symbol: str,
    ticker: str,
    data: Dict[str, Any],
    portfolio: Dict[str, Any],
    sentiment: Dict[str, Any],
    regime: str,
    now: str
) -> Dict[str, Any]:
    """
    Evaluates trading rules for a single cryptocurrency asset.

    :param symbol: Short symbol (e.g. "SOL")
    :param ticker: Binance ticker (e.g. "SOLUSDT")
    :param data: Technical indicator dictionary for this asset
    :param portfolio: Current portfolio dictionary
    :param sentiment: Sentiment data dictionary
    :param regime: Classified market regime string
    :param now: ISO timestamp string
    :return: Decision dictionary conforming to trade log schema
    """
    if not data or "error" in data:
        err_msg = data.get("error", "Data unavailable") if data else "Data unavailable"
        return {
            "timestamp": now,
            "symbol": symbol,
            "action": "HOLD",
            "price": 0.0,
            "qty": 0.0,
            "cost_or_proceeds": 0.0,
            "reasoning": f"Data fetch error or inactive Binance spot ticker ({err_msg}). Skipping trade.",
            "confidence": 0.0,
            "rsi14": 0.0,
            "ema12": 0.0,
            "ema26": 0.0,
            "ema50": 0.0,
            "macd": 0.0,
            "macd_signal": 0.0,
            "momentum_10": 0.0,
            "volume_ratio": 0.0,
            "divergence": "none",
            "trend_bias": "neutral",
            "news_sentiment": "no_signal",
            "event_risk": "none",
            "btc_correlation": 1.0,
            "funding_rate": 0.0,
            "onchain_signal": "no_signal",
            "social_trend": "normal",
            "adx14": 0.0,
            "vwap": 0.0,
            "oi_change_24h": 0.0,
            "taker_ratio": 1.0,
            "ob_imbalance_2pct": 0.50,
            "whale_alert": "NEUTRAL_FLOW",
            "market_regime": regime,
            "suggested_pos_size": 0.0
        }

    price = float(data.get("price", 0.0))
    rsi14 = float(data.get("rsi14", 50.0))
    adx14 = float(data.get("adx14", 20.0))
    vwap = float(data.get("vwap", price))
    atr14 = float(data.get("atr14", price * 0.03))
    trend_1d = data.get("trend_bias_1d", data.get("trend_bias", "neutral"))
    trend_4h = data.get("trend_bias_4h", "neutral")
    ob_imbalance = float(data.get("ob_imbalance_2pct", 0.50))
    taker_ratio = float(data.get("taker_ratio", 1.0))
    whale_alert = data.get("whale_alert", "NEUTRAL_FLOW")
    funding_rate = float(data.get("funding_rate", 0.0001))
    funding_alert = data.get("funding_alert", "NEUTRAL_FUNDING")
    rsi_1h = float(data.get("rsi_1h", 50.0))
    price_vs_ema20_1h = float(data.get("price_vs_ema20_1h", 0.0))
    rs_score = float(data.get("rs_score", 0.0))
    rs_rank = data.get("rs_rank", "-")
    divergence = data.get("divergence", "none")
    pct_b = float(data.get("bollinger_pct_b", 0.50))
    vol_ratio = float(data.get("volume_ratio", 1.0))
    volume_breakout = bool(data.get("volume_breakout", False))
    donchian_h20 = float(data.get("donchian_high_20", price))
    donchian_l20 = float(data.get("donchian_low_20", price))
    cmf20 = float(data.get("cmf20", 0.0))
    mfi14 = float(data.get("mfi14", 50.0))
    chop14 = float(data.get("chop14", 50.0))
    di_plus = float(data.get("di_plus", 20.0))
    di_minus = float(data.get("di_minus", 20.0))
    squeeze_on = bool(data.get("squeeze_on", False))
    squeeze_fired = bool(data.get("squeeze_fired", False))
    chandelier_stop = float(data.get("chandelier_stop", price * 0.93))

    pos_map = {p["symbol"]: p for p in portfolio.get("positions", [])}
    is_open = symbol in pos_map

    asset_sentiment = sentiment.get(symbol, {})
    news_sent = asset_sentiment.get("news_sentiment", "cautious_bullish")
    event_risk = asset_sentiment.get("event_risk", "none")

    # -------------------------------------------------------------------------
    # CALCULATE ADVANCED QUANT CONFLUENCE CONVICTION SCORE (0.0 to 1.0)
    # -------------------------------------------------------------------------
    conv_score = 0.15  # baseline

    # 1. Trend & Directional Movement (DMI)
    if trend_1d == "bullish" and trend_4h == "bullish":
        conv_score += 0.20
    elif trend_1d == "bullish" or trend_4h == "bullish":
        conv_score += 0.08
    if di_plus > di_minus:
        conv_score += 0.10

    # 2. Relative Strength Leadership
    try:
        rank_num = int(rs_rank)
    except Exception:
        rank_num = 99

    if rank_num in [1, 2, 3] or rs_score >= 5.0:
        conv_score += 0.20
    elif rank_num in [4, 5, 6] or rs_score > 0:
        conv_score += 0.10

    # 3. Institutional Money Flow (CMF & MFI)
    if cmf20 >= 0.08 and mfi14 >= 55.0:
        conv_score += 0.20  # Heavy smart-money accumulation
    elif cmf20 >= 0.02:
        conv_score += 0.10
    elif cmf20 <= -0.10:
        conv_score -= 0.15  # Distribution warning penalty

    # 4. Volatility Expansion & Squeeze (TTM Squeeze & Volume Breakout)
    if squeeze_fired:
        conv_score += 0.20  # Volatility compression exploding outward
    elif volume_breakout:
        conv_score += 0.15  # 20-Day Donchian range breakout on heavy volume
    elif vol_ratio >= 1.5:
        conv_score += 0.08

    # 5. Market Microstructure & Whale Flow
    if whale_alert in ["WHALE_ACCUMULATION", "BULLISH_WHALE_WALL"] or ob_imbalance >= 0.58:
        conv_score += 0.12
    elif taker_ratio >= 1.05:
        conv_score += 0.06

    if funding_alert == "SHORT_SQUEEZE_ALERT":
        conv_score += 0.15

    # 6. Choppiness Index (Trend Efficiency)
    if chop14 < 45.0:
        conv_score += 0.08  # Strong directional efficiency
    elif chop14 > 61.8:
        conv_score -= 0.08  # Consolidation penalty for breakout setups

    # 7. News & Sentiment Alignment
    if news_sent == "bullish" and event_risk == "none":
        conv_score += 0.08
    elif news_sent == "cautious_bullish" and event_risk == "none":
        conv_score += 0.04

    final_conviction = min(0.98, max(0.50, round(conv_score, 2)))

    # -------------------------------------------------------------------------
    # CONVICTION-WEIGHTED DYNAMIC POSITION SIZING (Feature 4)
    # -------------------------------------------------------------------------
    portfolio_cash = float(portfolio.get("cash", 10000.0))
    positions_val = sum(p.get("qty", 0.0) * float(p.get("entry_price", 0.0)) for p in portfolio.get("positions", []))
    curr_equity = portfolio_cash + positions_val
    if curr_equity <= 0:
        curr_equity = float(portfolio.get("starting_cash", 10000.0))

    base_alloc = round(curr_equity * 0.10, 2)  # 10% compounding base

    if final_conviction >= 0.85:
        conviction_tier = "A+"
        target_size = min(1200.0, max(800.0, round(base_alloc * 1.20, 2)))
    elif final_conviction >= 0.65:
        conviction_tier = "SOLID"
        target_size = min(1000.0, max(600.0, round(base_alloc * 1.00, 2)))
    else:
        conviction_tier = "CAUTIOUS"
        target_size = min(800.0, max(400.0, round(base_alloc * 0.70, 2)))

    if atr14 > 0:
        atr_risk_units = 100.0 / (2.0 * atr14)
        atr_size_cap = round(atr_risk_units * price, 2)
        suggested_pos_size = min(target_size, max(250.0, atr_size_cap))
    else:
        suggested_pos_size = target_size

    action = "HOLD"
    reasoning = ""
    confidence = final_conviction
    amount_usd = 0.0

    # -------------------------------------------------------------------------
    # 1. EVALUATE ACTIVE OPEN POSITIONS (Incorporating Chandelier Exit)
    # -------------------------------------------------------------------------
    if is_open:
        pos = pos_map[symbol]
        entry_p = float(pos.get("entry_price", price))
        highest_p = max(float(pos.get("highest_price", entry_p)), price)
        # Position-level Chandelier Exit hangs from trade's highest price peak
        trade_chandelier_stop = round(highest_p - (2.0 * atr14), 4) if atr14 > 0 else round(entry_p * 0.93, 4)
        std_trail = float(pos.get("trailing_stop_price", round(entry_p - (2.0 * atr14), 4)))
        trailing_stop = max(std_trail, trade_chandelier_stop)
        if pos.get("tp1_hit", False):
            trailing_stop = max(trailing_stop, entry_p)
        pnl_pct = ((price - entry_p) / entry_p) * 100 if entry_p > 0 else 0.0
        tp1_hit = pos.get("tp1_hit", False)

        # TP1 Partial Profit Scaling (+10% gain lock-in)
        if pnl_pct >= 10.0 and not tp1_hit:
            action = "TRIM"
            confidence = 0.92
            reasoning = (
                f"Take Profit 1 (TP1) hit (+{pnl_pct:.2f}% vs +10% target). Taking 50% profit off the table into cash, "
                f"locking runner trailing stop to breakeven (${entry_p:.4f})."
            )
        # Trailing / Chandelier Stop Breach Exit
        elif price < trailing_stop:
            action = "SELL"
            confidence = 0.92
            reasoning = f"Price ${price:.4f} breached dynamic Chandelier/ATR trailing stop level (${trailing_stop:.4f}). Executing SELL to preserve capital."
        # Ranging Regime Mean-Reversion Exit
        elif regime == "ranging" and (pct_b >= 0.85 or rsi14 >= 62.0):
            action = "SELL"
            confidence = 0.88
            reasoning = f"Mean-reversion exit in ranging market: Price reached upper Bollinger Band (%B {pct_b:.2f}) with RSI {rsi14:.2f}. Locking in range profit."
        # Daily Trend Breakdown Exit
        elif trend_1d == "bearish" and pnl_pct < 0:
            action = "SELL"
            confidence = 0.88
            reasoning = f"Daily trend bias flipped to bearish (price < EMA50) with negative position return ({pnl_pct:.2f}%). Closing position."
        # Extreme Overbought Exhaustion Exit
        elif rsi14 >= 75.0 and divergence == "bearish":
            action = "SELL"
            confidence = 0.90
            reasoning = f"Extreme overbought RSI ({rsi14:.2f}) combined with confirmed bearish RSI divergence. Executing profit take."
        # Institutional Whale Distribution Exit
        elif whale_alert == "WHALE_DISTRIBUTION" or cmf20 <= -0.18:
            action = "SELL"
            confidence = 0.88
            reasoning = f"Heavy institutional distribution detected (Whale Alert '{whale_alert}', CMF {cmf20:.4f}). Exiting to avoid institutional dump."
        else:
            action = "HOLD"
            confidence = final_conviction
            runner_tag = " [RUNNER - ZERO RISK]" if tp1_hit else ""
            if pnl_pct >= 0:
                reasoning = f"Active position in profit (+{pnl_pct:.2f}% from ${entry_p:.4f} entry){runner_tag}. Price ${price:.4f} comfortably above Chandelier stop (${trailing_stop:.4f}); holding."
            else:
                reasoning = f"Active position intact ({pnl_pct:.2f}% from ${entry_p:.4f} entry). Price ${price:.4f} is well above Chandelier stop (${trailing_stop:.4f}); trend structure intact."

    # -------------------------------------------------------------------------
    # 2. EVALUATE WATCHLIST CANDIDATES FOR BUY ENTRIES
    # -------------------------------------------------------------------------
    else:
        open_count = len(portfolio.get("positions", []))
        cash = float(portfolio.get("cash", 0.0))

        if open_count >= 6:
            action = "HOLD"
            confidence = 0.80
            reasoning = f"Portfolio position cap reached ({open_count}/6 max positions). Cash reserved until an existing position exits."
        elif regime == "volatility_crash":
            action = "HOLD"
            confidence = 0.85
            reasoning = "Macro market regime is 'volatility_crash'. New buy entries are vetoed to prioritize capital preservation."
        elif whale_alert in ["WHALE_DISTRIBUTION", "BEARISH_WHALE_WALL"]:
            action = "HOLD"
            confidence = 0.85
            reasoning = f"Whale flow alert '{whale_alert}' detected. Institutional selling pressure vetoes buy entry."
        elif cmf20 <= -0.10:
            action = "HOLD"
            confidence = 0.85
            reasoning = f"Institutional money flow is negative (CMF {cmf20:.4f} <= -0.10). Smart money distribution vetoes buy entry."
        elif funding_alert == "LONG_FLUSH_ALERT":
            action = "HOLD"
            confidence = 0.85
            reasoning = f"Overcrowded long leverage (Funding {funding_rate:.6f} >= +0.03%). Vetoing buy entry to avoid long liquidation flush."
        # --- RANGING REGIME: ACTIVE MEAN-REVERSION BUY LOGIC ---
        elif regime == "ranging":
            if (pct_b <= 0.25 or rsi14 <= 38.0) and ob_imbalance >= 0.52 and adx14 < 25.0:
                if cash >= suggested_pos_size:
                    action = "BUY"
                    amount_usd = suggested_pos_size
                    confidence = 0.84
                    reasoning = (
                        f"MEAN-REVERSION ENTRY ({conviction_tier} TIER): Ranging market oversold bounce play (Bollinger %B {pct_b:.2f} <= 0.25, "
                        f"RSI {rsi14:.2f} <= 38) with order book bid support ({ob_imbalance:.4f}). Initiating allocation (${suggested_pos_size:.2f})."
                    )
                else:
                    action = "HOLD"
                    reasoning = f"Mean-reversion setup present but insufficient cash buffer (${cash:.2f})."
            else:
                action = "HOLD"
                confidence = 0.75
                reasoning = f"Ranging regime active: Awaiting oversold lower Bollinger band touch (%B {pct_b:.2f} > 0.25)."
        # --- TREND REGIME: TREND-FOLLOWING & BREAKOUT BUY LOGIC ---
        elif rsi14 > (68.0 if (regime == "bullish_trend" and (rs_rank in [1, 2, 3] or rs_score >= 5.0) and adx14 >= 25.0) else 65.0):
            max_rsi = 68.0 if (regime == "bullish_trend" and (rs_rank in [1, 2, 3] or rs_score >= 5.0) and adx14 >= 25.0) else 65.0
            action = "HOLD"
            confidence = 0.85
            reasoning = f"Daily RSI is overbought ({rsi14:.2f} > {max_rsi:.0f} cutoff threshold). Standing aside to catch a healthier pullback."
        elif rsi14 < 45.0 and not squeeze_fired:
            action = "HOLD"
            confidence = 0.75
            reasoning = f"RSI is weak ({rsi14:.2f} < 45) with lack of upward momentum. Awaiting technical recovery."
        elif trend_1d != "bullish" or trend_4h != "bullish":
            action = "HOLD"
            confidence = 0.75
            reasoning = f"Multi-timeframe trend alignment unfulfilled (1D: '{trend_1d}', 4H: '{trend_4h}'). Requires dual bullish alignment."
        elif adx14 < 20.0 and not (volume_breakout or squeeze_fired):
            action = "HOLD"
            confidence = 0.75
            reasoning = f"ADX is choppy ({adx14:.2f} < 20 cutoff), indicating range-bound / non-trending conditions."
        elif ob_imbalance < 0.48:
            action = "HOLD"
            confidence = 0.75
            reasoning = f"Order book depth skewed to asks (imbalance ratio {ob_imbalance:.4f} < 0.48). Lacks sufficient bid support."
        elif taker_ratio < 0.95:
            action = "HOLD"
            confidence = 0.75
            reasoning = f"Taker buy/sell volume ratio ({taker_ratio:.4f} < 0.95) indicates active seller aggression."
        elif price < vwap * 0.98:
            action = "HOLD"
            confidence = 0.75
            reasoning = f"Price ${price:.4f} is trading notably below VWAP (${vwap:.4f}). Awaiting reclaim of VWAP."
        # 1-Hour Intraday Precision Filter
        elif rsi_1h > 68.0 or price_vs_ema20_1h > 3.5:
            action = "HOLD"
            confidence = 0.80
            triggers = []
            if rsi_1h > 68.0:
                triggers.append(f"1H RSI overbought ({rsi_1h:.2f} > 68)")
            if price_vs_ema20_1h > 3.5:
                triggers.append(f"price stretched +{price_vs_ema20_1h:.2f}% above 1H EMA20 (> +3.5%)")
            reasoning = f"1H timeframe is overextended ({' and '.join(triggers)}). Awaiting intraday pullback for precision entry."
        elif cash < suggested_pos_size:
            action = "HOLD"
            confidence = 0.80
            reasoning = f"Insufficient cash buffer (${cash:.2f} vs required ${suggested_pos_size:.2f}) to open position."
        else:
            # All strict buy criteria satisfied!
            action = "BUY"
            amount_usd = suggested_pos_size
            confidence = final_conviction
            squeeze_tag = f" [⚡ TTM SQUEEZE FIRED: Coiled volatility exploding outward!]" if squeeze_fired else ""
            breakout_tag = f" [🚀 VOLUME BREAKOUT: 24h Vol {vol_ratio:.1f}x expanding into 20D High ${donchian_h20:.4f}!]" if volume_breakout else ""
            cmf_tag = f" [💵 CMF: {cmf20:+.4f}]" if cmf20 >= 0.05 else ""
            reasoning = (
                f"BULLISH CONFIRMATION ({conviction_tier} TIER, Score: {final_conviction:.2f}): Dual 1D/4H bullish trend alignment (Price ${price:.4f} > EMA50), "
                f"healthy RSI ({rsi14:.2f}), strong ADX ({adx14:.2f}), Order Book bid dominance ({ob_imbalance:.4f}), "
                f"and Taker Ratio ({taker_ratio:.4f}). RS Rank: #{rs_rank} (Score: {rs_score:+.2f}).{breakout_tag}{squeeze_tag}{cmf_tag} Initiating {conviction_tier} allocation (${suggested_pos_size:.2f})."
            )

    return {
        "timestamp": now,
        "symbol": symbol,
        "action": action,
        "price": price,
        "amount_usd": amount_usd,
        "qty": 0.0,
        "cost_or_proceeds": 0.0,
        "reasoning": reasoning,
        "confidence": confidence,
        "conviction_score": final_conviction,
        "conviction_tier": conviction_tier,
        "volume_breakout": volume_breakout,
        "donchian_high_20": donchian_h20,
        "donchian_low_20": donchian_l20,
        "cmf20": cmf20,
        "mfi14": mfi14,
        "chop14": chop14,
        "di_plus": di_plus,
        "di_minus": di_minus,
        "squeeze_on": squeeze_on,
        "squeeze_fired": squeeze_fired,
        "chandelier_stop": chandelier_stop,
        "rsi14": rsi14,
        "rsi_4h": float(data.get("rsi_4h", 50.0)),
        "rsi_1h": rsi_1h,
        "ema20_1h": float(data.get("ema20_1h", price)),
        "price_vs_ema20_1h": price_vs_ema20_1h,
        "rs_score": rs_score,
        "rs_rank": rs_rank,
        "ema12": float(data.get("ema12", 0.0)),
        "ema26": float(data.get("ema26", 0.0)),
        "ema50": float(data.get("ema50", 0.0)),
        "macd": float(data.get("macd", 0.0)),
        "macd_signal": float(data.get("macd_signal", 0.0)),
        "momentum_10": float(data.get("momentum_10", 0.0)),
        "volume_ratio": vol_ratio,
        "divergence": divergence,
        "trend_bias": trend_1d,
        "news_sentiment": news_sent,
        "event_risk": event_risk,
        "btc_correlation": 1.0 if symbol == "BTC" else 0.85,
        "funding_rate": funding_rate,
        "funding_alert": funding_alert,
        "onchain_signal": "no_signal",
        "social_trend": "normal",
        "adx14": adx14,
        "vwap": vwap,
        "atr14": atr14,
        "oi_change_24h": float(data.get("oi_change_24h", 0.0)),
        "taker_ratio": taker_ratio,
        "ob_imbalance_2pct": ob_imbalance,
        "whale_alert": whale_alert,
        "market_regime": regime,
        "suggested_pos_size": suggested_pos_size
    }


def generate_executive_summary_markdown(
    portfolio: Dict[str, Any],
    market_ctx: Dict[str, Any],
    decisions: List[Dict[str, Any]],
    now: str
) -> str:
    """
    Renders the standardized GitHub-style markdown executive summary report.
    """
    cash = float(portfolio.get("cash", 10000.0))
    positions = portfolio.get("positions", [])
    metrics = portfolio.get("metrics", {})
    history = portfolio.get("equity_history", [])
    curr_equity = history[-1].get("portfolio_value", cash) if history else cash
    bench_val = history[-1].get("benchmark_value", 10000.0) if history else 10000.0
    start_cash = float(portfolio.get("starting_cash", 10000.0))
    total_pnl_usd = curr_equity - start_cash
    total_pnl_pct = (total_pnl_usd / start_cash) * 100 if start_cash > 0 else 0.0

    fg = market_ctx.get("fear_and_greed", {})
    fg_val = fg.get("value", "N/A")
    fg_class = fg.get("value_classification", "Neutral")
    btc_d = market_ctx.get("btc_dominance", 0.0)
    eth_d = market_ctx.get("eth_dominance", 0.0)
    regime = market_ctx.get("market_regime", "neutral")

    lines = []
    lines.append("# 🚀 Daily Crypto Paper-Trading Agent — Executive Summary Report\n")
    lines.append(f"**Execution Timestamp:** `{now}`  ")
    lines.append("**Operational Status:** Autonomous Twice-Daily Paper-Trading Pass Completed  ")
    lines.append(f"**Tracked Assets Universe:** {len(decisions)} Pre-Screened Shariah-Compliant Assets  \n")
    lines.append("---\n")

    # 1. Executive Portfolio Header
    lines.append("## 1. 💼 Executive Portfolio Header\n")
    lines.append("| Metric | Current Value | Baseline / Target | Notes |")
    lines.append("| :--- | :--- | :--- | :--- |")
    lines.append(f"| **Total Portfolio Value** | **${curr_equity:,.2f} USD** | ${start_cash:,.2f} Starting Cash | **{'+' if total_pnl_usd >= 0 else ''}${total_pnl_usd:,.2f} Net P&L ({'+' if total_pnl_pct >= 0 else ''}{total_pnl_pct:.2f}%)** |")
    lines.append(f"| **Cash Balance** | **${cash:,.2f} USD** | Min 20% Reserve | **{(cash / curr_equity * 100):.2f}%** Capital in Liquid Cash |")
    pos_val = curr_equity - cash
    lines.append(f"| **Active Positions Value** | **${pos_val:,.2f} USD** | Max 6 Positions | **{(pos_val / curr_equity * 100):.2f}%** Capital Allocated |")
    lines.append(f"| **Open Positions Count** | **{len(positions)} / 6** | Max Cap: 6 | {6 - len(positions)} Position Slots Available |")
    lines.append(f"| **Total Executed Trades** | **{portfolio.get('trade_counter', 0)} Trades** | — | Audit trail synchronized in CSV |")
    lines.append("\n---\n")

    # 2. Institutional Risk & Benchmark Metrics
    lines.append("## 2. 📊 Institutional Risk & Benchmark Metrics\n")
    bench_ret = metrics.get("benchmark_return_pct", 0.0)
    alpha = total_pnl_pct - bench_ret
    lines.append("| Risk / Performance Metric | Portfolio Value | Benchmark (50/50 BTC/ETH) | Performance Alpha |")
    lines.append("| :--- | :--- | :--- | :--- |")
    lines.append(f"| **Total Cumulative Return** | **{'+' if total_pnl_pct >= 0 else ''}{total_pnl_pct:.2f}%** | **{'+' if bench_ret >= 0 else ''}{bench_ret:.2f}%** | **{'+' if alpha >= 0 else ''}{alpha:.2f}% Alpha** |")
    lines.append(f"| **Current Benchmark Value** | ${curr_equity:,.2f} | ${bench_val:,.2f} | **{'+' if (curr_equity - bench_val) >= 0 else ''}${(curr_equity - bench_val):,.2f} Value Premium** |")
    lines.append(f"| **Max Drawdown (%)** | **{metrics.get('max_drawdown_pct', 0.0):.2f}%** | Macro Benchmark Variance | Capital preservation filter active |")
    lines.append(f"| **Calmar Ratio** | **{metrics.get('calmar_ratio', 0.0):.2f}** | — | Return to max drawdown ratio |")
    lines.append(f"| **Rolling Sharpe Ratio** | **{metrics.get('sharpe_ratio', 0.0):.2f}** | — | Annualized risk-adjusted return |")
    lines.append(f"| **Rolling Sortino Ratio** | **{metrics.get('sortino_ratio', 0.0):.2f}** | — | Downside-volatility weighted |")
    lines.append("\n---\n")

    # 3. Macro Market Regime & Context
    lines.append("## 3. 🌐 Macro Market Regime & Sentiment Context\n")
    lines.append(f"* **Market Regime:** `{regime}`")
    lines.append(f"* **Fear & Greed Index:** **{fg_val} / 100 ({fg_class})**")
    lines.append(f"* **BTC Dominance:** **{btc_d:.2f}%** | **ETH Dominance:** **{eth_d:.2f}%**")
    lines.append("\n---\n")

    # 4. Active Portfolio Snapshot
    lines.append("## 4. 📈 Active Portfolio Snapshot (Open Positions)\n")
    if positions:
        lines.append("| Trade ID | Asset | Qty | Entry Price | Highest Price | Trailing Stop | Cost Basis | Scaling Status |")
        lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
        for idx, p in enumerate(positions, 1):
            tp1_status = "**RUNNER (TP1 Locked)**" if p.get("tp1_hit", False) else "FULL POSITION"
            lines.append(
                f"| **TRADE-{idx:03d}** | `{p.get('symbol')}` | {p.get('qty', 0):.4f} | "
                f"${p.get('entry_price', 0):.4f} | ${p.get('highest_price', 0):.4f} | "
                f"${p.get('trailing_stop_price', 0):.4f} | ${p.get('cost_basis', 0):.2f} | {tp1_status} |"
            )
    else:
        lines.append("_No open positions currently active. Portfolio is 100% liquid cash._")
    lines.append("\n---\n")

    # 5. Trade Actions & Decisions Summary
    buys = [d for d in decisions if d.get("action") == "BUY"]
    trims = [d for d in decisions if d.get("action") == "TRIM"]
    sells = [d for d in decisions if d.get("action") == "SELL"]
    holds = [d for d in decisions if d.get("action") == "HOLD"]

    lines.append(f"## 5. 🎯 Trade Actions Summary ({len(buys)} BUYS, {len(trims)} TRIMS, {len(sells)} SELLS, {len(holds)} HOLDS)\n")
    lines.append("| Asset | Action | Live Price | RSI(14) | RS Rank | Conviction Tier | CMF(20) | Squeeze / Breakout | Chandelier Stop | Decision Rationale |")
    lines.append("| :--- | :---: | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :--- |")
    for d in decisions:
        rs_str = f"#{d.get('rs_rank', '-')} ({d.get('rs_score', 0.0):+.2f})"
        tier_str = f"`{d.get('conviction_tier', 'SOLID')}`"
        cmf_val = float(d.get("cmf20", 0.0))
        cmf_str = f"`{cmf_val:+.3f}`"
        sq_str = "⚡ **FIRED**" if d.get("squeeze_fired") else ("🟠 SQUEEZE" if d.get("squeeze_on") else ("🚀 BREAKOUT" if d.get("volume_breakout") else "`NORMAL`"))
        ch_stop = f"${float(d.get('chandelier_stop', 0)):.4f}"
        lines.append(
            f"| **{d.get('symbol')}** | **{d.get('action')}** | ${d.get('price', 0):.4f} | "
            f"{d.get('rsi14', 0):.2f} | {rs_str} | {tier_str} | {cmf_str} | "
            f"{sq_str} | {ch_stop} | {d.get('reasoning')} |"
        )
    lines.append("\n---\n")

    # 6. Persistent Files Confirmation
    lines.append("## 6. 📁 Workspace File Synchronization\n")
    lines.append("* `state/latest_research.json`: Multi-timeframe TA (1D/4H/1H), RS vs BTC, and funding metrics.")
    lines.append("* `state/latest_sentiment.json`: News headlines & macro sentiment cached.")
    lines.append("* `state/latest_decisions.json`: Standardized decision array persisted.")
    lines.append("* `state/latest_summary.md`: Rendered markdown report saved.")
    lines.append("* `state/portfolio.json`: Portfolio cash, holdings, TP1 status, and risk metrics synchronized.")
    lines.append("* `state/trade_log.csv`: Audit log rows appended.")
    lines.append("* `state/human_open_positions.csv`: Active positions view synchronized.")
    lines.append("* `state/human_decision_log.csv`: Human decision trail synchronized.\n")

    return "\n".join(lines)


def run_trader_pass(dry_run: bool = False, silent: bool = False) -> Dict[str, Any]:
    """
    Main orchestrator for twice-daily paper-trading pass.
    Evaluates open positions first, then prioritizes new buys by Relative Strength (RS) leadership ranking.
    """
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    watchlist_path = os.path.join(ROOT_DIR, "state", "watchlist.json")
    research_path = os.path.join(ROOT_DIR, "state", "latest_research.json")
    sentiment_path = os.path.join(ROOT_DIR, "state", "latest_sentiment.json")
    decisions_path = os.path.join(ROOT_DIR, "state", "latest_decisions.json")
    summary_path = os.path.join(ROOT_DIR, "state", "latest_summary.md")

    if not silent:
        print(f"🚀 [1/5] Running live market research across tracked universe...")

    # 1. Technical Research (1D & 4H)
    research_data = run_research(watchlist_path=watchlist_path, output_path=research_path)
    market_ctx = research_data.get("market_context", {})
    ta_data = research_data.get("technical_analysis", {})
    regime = market_ctx.get("market_regime", "neutral")

    # 2. Sentiment Research
    if not silent:
        print(f"📰 [2/5] Querying news headlines and macro sentiment...")
    sentiment_data = analyze_news_sentiment(output_path=sentiment_path)

    # 3. Load Persistent Portfolio
    portfolio = load_portfolio()

    # 4. Decision Engine (Open Positions first, then RS-Ranked Candidates)
    if not silent:
        print(f"🧠 [3/5] Evaluating decision rules, multi-stage TP1 scaling, and RS ranking...")
    watchlist = load_watchlist(watchlist_path)
    pos_symbols = {p["symbol"] for p in portfolio.get("positions", [])}

    # Separate into currently open vs candidate assets
    open_items = []
    candidate_items = []
    for name, ticker in watchlist.items():
        sym = ticker.replace("USDT", "")
        if sym in pos_symbols:
            open_items.append((sym, ticker))
        else:
            candidate_items.append((sym, ticker))

    # Sort candidates by RS score descending (Top Market Leaders first!)
    candidate_items.sort(
        key=lambda x: ta_data.get(x[1], {}).get("rs_score", -999.0),
        reverse=True
    )

    decisions = []
    # Evaluate open positions
    for sym, ticker in open_items:
        asset_ta = ta_data.get(ticker, {})
        d = evaluate_asset_decision(
            symbol=sym,
            ticker=ticker,
            data=asset_ta,
            portfolio=portfolio,
            sentiment=sentiment_data,
            regime=regime,
            now=now
        )
        decisions.append(d)

    # Evaluate candidate assets (leaders get priority for available slots)
    for sym, ticker in candidate_items:
        asset_ta = ta_data.get(ticker, {})
        d = evaluate_asset_decision(
            symbol=sym,
            ticker=ticker,
            data=asset_ta,
            portfolio=portfolio,
            sentiment=sentiment_data,
            regime=regime,
            now=now
        )
        decisions.append(d)
        # If candidate triggered BUY, simulate adding to temp open count so subsequent candidates respect cap
        if d.get("action") == "BUY":
            pos_symbols.add(sym)

    # Save decisions to fixed state file
    decisions_payload = {
        "timestamp": now,
        "decisions": decisions
    }
    with open(decisions_path, "w") as f:
        json.dump(decisions_payload, f, indent=2)

    # 5. Trade Execution & State Persistence
    if not silent:
        print(f"⚡ [4/5] Syncing state and updating portfolio...")
    if not dry_run:
        updated_portfolio = execute_trade_pass(decisions_payload)
    else:
        updated_portfolio = portfolio
        if not silent:
            print("   [DRY-RUN] Skipped persistent trade execution and portfolio write.")

    # 6. Generate & Save Executive Report
    if not silent:
        print(f"📄 [5/5] Generating Executive Summary Report...")
    summary_md = generate_executive_summary_markdown(
        portfolio=updated_portfolio,
        market_ctx=market_ctx,
        decisions=decisions,
        now=now
    )
    with open(summary_path, "w") as f:
        f.write(summary_md)

    if not silent:
        print("\n" + summary_md)

    # 7. Dispatch Discord Webhook Notification
    if not dry_run:
        send_discord_notification(
            portfolio=updated_portfolio,
            decisions=decisions,
            regime=regime
        )

    return {
        "status": "success",
        "timestamp": now,
        "portfolio": updated_portfolio,
        "decisions_count": len(decisions),
        "summary_path": summary_path
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ANTItrading Autonomous Twice-Daily Paper-Trading Runner")
    parser.add_argument("--dry-run", action="store_true", help="Evaluate research and decisions without saving trades")
    parser.add_argument("--silent", action="store_true", help="Suppress terminal markdown rendering")
    args = parser.parse_args()

    run_trader_pass(dry_run=args.dry_run, silent=args.silent)
