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
import fcntl
import argparse
import datetime
from typing import Dict, Any, List, Tuple

# Ensure workspace root is in sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from scripts.research import run_research, run_fast_risk_research, load_watchlist
from scripts.news_research import analyze_news_sentiment
from scripts.execute_trade import load_portfolio, execute_trade_pass
from scripts.discord_notifier import send_discord_notification

# Portfolio & Risk Limits
MAX_POSITIONS = 10
PROFIT_LOCK_TRIGGER_PCT = 2.0  # Dynamic profit lock activates once gain reaches +2.0%
PROFIT_LOCK_RATIO = 0.60       # Ratchets stop to lock in 60% of peak gain (min 1.0% locked)
MAX_PORTFOLIO_BETA_PCT = 0.60  # Max aggregate BTC beta exposure across portfolio equity
MAX_PAIRWISE_CORR = 0.75       # Max pairwise correlation threshold for simultaneous entry gating

RSI_CUTOFFS = {
    "BTC": 78.0,
    "ETH": 76.0,
    "default": 68.0
}


class ExecutionLock:
    """Process-level file lock using fcntl to prevent concurrent executions."""
    def __init__(self, lockfile_path="/tmp/antitrader_run.lock"):
        self.lockfile_path = lockfile_path
        self.fp = None

    def acquire(self) -> bool:
        try:
            self.fp = open(self.lockfile_path, "w")
            fcntl.flock(self.fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.fp.write(f"{os.getpid()}\n")
            self.fp.flush()
            return True
        except (IOError, BlockingIOError, PermissionError):
            return False

    def release(self):
        if self.fp:
            try:
                fcntl.flock(self.fp, fcntl.LOCK_UN)
                self.fp.close()
            except Exception:
                pass
            self.fp = None


def should_veto_on_rsi(symbol: str, rsi14: float, adx14: float, ema12: float, ema26: float, ema50: float, price: float) -> Tuple[bool, str]:
    """Evaluates whether to veto on overbought RSI or allow riding a strong aligned trend."""
    cutoff = RSI_CUTOFFS.get(symbol, RSI_CUTOFFS["default"])
    if rsi14 <= cutoff:
        return False, ""
    # Strong trend override: if trend structure is powerful and aligned, ride rather than veto
    strong_trend = (adx14 >= 32.0) and (price > ema12 > ema26 > ema50)
    if strong_trend:
        return False, f" [RSI {rsi14:.1f} > {cutoff:.0f} override: Strong trend aligned (ADX {adx14:.1f})]"
    return True, f"RSI({rsi14:.1f}) exceeds {cutoff:.0f} threshold without strong trend alignment (ADX {adx14:.1f} < 32)."


def get_portfolio_btc_beta_exposure(open_positions: list, ta_data: dict) -> float:
    """Calculates sum of (current_position_value * btc_correlation) across all open positions."""
    total_exposure = 0.0
    for pos in open_positions:
        sym = pos.get("symbol")
        ticker = sym if sym.endswith("USDT") else f"{sym}USDT"
        asset_ta = ta_data.get(ticker, {})
        corr = float(asset_ta.get("btc_correlation", 1.0 if sym == "BTC" else 0.85))
        curr_price = float(asset_ta.get("price", pos.get("entry_price", 0.0)))
        qty = float(pos.get("qty", 0.0))
        val = (curr_price * qty) if (curr_price > 0 and qty > 0) else float(pos.get("cost_basis", 0.0))
        total_exposure += val * corr
    return total_exposure


def can_open_new_position(symbol: str, size_usd: float, open_positions: list, ta_data: dict, portfolio_value: float, max_beta_pct: float = 0.60) -> Tuple[bool, str]:
    """Verifies that adding a new position does not breach the portfolio BTC beta exposure cap."""
    curr_exposure = get_portfolio_btc_beta_exposure(open_positions, ta_data)
    ticker = symbol if symbol.endswith("USDT") else f"{symbol}USDT"
    new_corr = float(ta_data.get(ticker, {}).get("btc_correlation", 1.0 if symbol == "BTC" else 0.85))
    projected_exposure = curr_exposure + (size_usd * new_corr)
    max_allowed = portfolio_value * max_beta_pct
    if projected_exposure > max_allowed:
        pct = (projected_exposure / portfolio_value) * 100 if portfolio_value > 0 else 0.0
        return False, f"Portfolio BTC beta cap reached ({pct:.1f}% > {max_beta_pct*100:.0f}% max). Vetoing buy to prevent correlated flush."
    return True, ""


def get_pairwise_correlation(symbol_a: str, symbol_b: str, market_data: dict) -> float:
    """
    Returns pairwise correlation between two symbols.
    Checks market_data["pairwise_correlations"] first.
    Fallback Proxy: Two coins are 'the same bet' if both have btc_correlation > 0.80
    and their price action direction lines up (same trend_bias).
    """
    if symbol_a == symbol_b:
        return 1.0

    pair_matrix = market_data.get("pairwise_correlations", {})
    if f"{symbol_a}_{symbol_b}" in pair_matrix:
        return float(pair_matrix[f"{symbol_a}_{symbol_b}"])
    if f"{symbol_b}_{symbol_a}" in pair_matrix:
        return float(pair_matrix[f"{symbol_b}_{symbol_a}"])

    # Fallback Proxy using asset TA metadata
    ta_map = market_data.get("technical_analysis", market_data)
    ta_a = ta_map.get(f"{symbol_a}USDT", ta_map.get(symbol_a, {}))
    ta_b = ta_map.get(f"{symbol_b}USDT", ta_map.get(symbol_b, {}))

    corr_a = float(ta_a.get("btc_correlation", 1.0 if symbol_a == "BTC" else 0.85))
    corr_b = float(ta_b.get("btc_correlation", 1.0 if symbol_b == "BTC" else 0.85))
    bias_a = ta_a.get("trend_bias", "neutral")
    bias_b = ta_b.get("trend_bias", "neutral")

    # If one is BTC, the correlation is directly the asset's btc_correlation
    if symbol_a == "BTC":
        return corr_b
    if symbol_b == "BTC":
        return corr_a

    # Highly correlated bet proxy: both high BTC correlation and same trend direction
    if corr_a > 0.80 and corr_b > 0.80 and bias_a == bias_b:
        return round(min(corr_a, corr_b), 2)

    # Independent sectors or distinct catalyst behavior
    return round(corr_a * corr_b * 0.70, 2)


def filter_simultaneous_entries(
    candidates: list,
    market_data: dict,
    open_positions: list,
    max_pairwise_corr: float = 0.75
) -> Tuple[list, list]:
    """
    Greedily accepts high-score candidate BUY signals, filtering out ones too correlated
    to already-accepted candidates or currently held open positions.
    Returns: (accepted_candidates, rejected_candidates_with_reason)
    """
    accepted = []
    rejected = []

    sorted_candidates = sorted(
        candidates,
        key=lambda x: x.get("setup_score", 0),
        reverse=True
    )

    for c in sorted_candidates:
        sym = c["symbol"]
        too_correlated = False
        conflict_sym = None
        conflict_corr = 0.0

        # 1. Check correlation against already accepted candidates in this batch
        for a in accepted:
            corr = get_pairwise_correlation(sym, a["symbol"], market_data)
            if corr > max_pairwise_corr:
                too_correlated = True
                conflict_sym = a["symbol"]
                conflict_corr = corr
                break

        # 2. Check correlation against existing open positions
        if not too_correlated:
            for p in open_positions:
                p_sym = p.get("symbol")
                if not p_sym:
                    continue
                corr = get_pairwise_correlation(sym, p_sym, market_data)
                if corr > max_pairwise_corr:
                    too_correlated = True
                    conflict_sym = p_sym
                    conflict_corr = corr
                    break

        if too_correlated:
            c_copy = dict(c)
            c_copy["action"] = "HOLD"
            c_copy["reasoning"] = (
                f"Pairwise Correlation Veto: Ticker {sym} has {conflict_corr:.2f} correlation (> {max_pairwise_corr:.2f}) "
                f"with active/accepted asset {conflict_sym} (Candidate Score: {c.get('setup_score')}/100). Clustered beta risk vetoed."
            )
            rejected.append(c_copy)
        else:
            accepted.append(c)

    return accepted, rejected


def compute_setup_score(
    data: Dict[str, Any],
    regime: str,
    sentiment_item: Dict[str, Any]
) -> Tuple[int, Dict[str, Any]]:
    """
    Computes a 0-100 composite setup score across 6 technical and quantitative pillars:
    1. Trend & Multi-Timeframe Structure (0-25 pts)
    2. Relative Strength vs BTC Leadership (0-20 pts)
    3. Regime-Aware Momentum & Precision (0-15 pts)
    4. Volume & Institutional Money Flow (0-15 pts)
    5. Market Microstructure & Whale Flow (0-15 pts)
    6. Macro, Efficiency & Sentiment (0-10 pts)

    :param data: Technical indicator dictionary for this asset
    :param regime: Market regime string
    :param sentiment_item: Asset-level sentiment dict
    :return: (total_score, breakdown_dict)
    """
    if not data or data.get("status") == "UNAVAILABLE" or "error" in data:
        return 0, {
            "trend_mtf": 0, "relative_strength": 0, "momentum": 0,
            "volume_flow": 0, "microstructure": 0, "macro_efficiency": 0, "total": 0
        }

    trend_1d = data.get("trend_bias_1d", data.get("trend_bias", "neutral"))
    trend_4h = data.get("trend_bias_4h", "neutral")
    di_plus = float(data.get("di_plus", 20.0))
    di_minus = float(data.get("di_minus", 20.0))

    rs_rank = data.get("rs_rank", "-")
    rs_score = float(data.get("rs_score", 0.0))

    rsi14 = float(data.get("rsi14", 50.0))
    pct_b = float(data.get("bollinger_pct_b", 0.50))
    divergence = data.get("divergence", "none")

    cmf20 = float(data.get("cmf20", 0.0))
    mfi14 = float(data.get("mfi14", 50.0))
    squeeze_fired = bool(data.get("squeeze_fired", False))
    squeeze_on = bool(data.get("squeeze_on", False))
    volume_breakout = bool(data.get("volume_breakout", False))
    vol_ratio = float(data.get("volume_ratio", 1.0))

    whale_alert = data.get("whale_alert", "NEUTRAL_FLOW")
    ob_imbalance = float(data.get("ob_imbalance_2pct", 0.50))
    taker_ratio = float(data.get("taker_ratio", 1.0))
    funding_alert = data.get("funding_alert", "NEUTRAL_FUNDING")

    chop14 = float(data.get("chop14", 50.0))
    news_sent = sentiment_item.get("news_sentiment", "cautious_bullish")
    event_risk = sentiment_item.get("event_risk", "none")

    # 1. Trend & MTF Structure (0-25 pts)
    trend_pts = 0
    if trend_1d == "bullish":
        trend_pts += 10
    elif trend_1d == "bearish":
        trend_pts -= 5

    if trend_4h == "bullish":
        trend_pts += 8
    elif trend_4h == "bearish":
        trend_pts -= 4

    if trend_1d == "bullish" and trend_4h == "bullish":
        trend_pts += 2  # Confluence bonus

    if di_plus > di_minus:
        trend_pts += 5
    trend_pts = max(0, min(25, trend_pts))

    # 2. Relative Strength vs BTC (0-20 pts)
    rs_pts = 0
    try:
        rank_num = int(rs_rank)
    except Exception:
        rank_num = 99

    if rank_num in [1, 2, 3]:
        rs_pts += 20
    elif rank_num in [4, 5, 6]:
        rs_pts += 14
    elif rs_score >= 3.0:
        rs_pts += 12
    elif rs_score > 0.0:
        rs_pts += 6
    rs_pts = max(0, min(20, rs_pts))

    sym = data.get("symbol", "")
    adx14 = float(data.get("adx14", 20.0))

    # 3. Regime-Aware Momentum & Precision (0-15 pts)
    mom_pts = 0
    if regime == "bullish_trend":
        if 50.0 <= rsi14 <= 66.0:
            mom_pts += 15
        elif 66.0 < rsi14 <= 75.0:
            mom_pts += 12
        elif 40.0 <= rsi14 < 50.0:
            mom_pts += 8
        elif rsi14 > 75.0:
            if sym in ["BTC", "ETH"] and adx14 >= 30.0 and rsi14 <= 78.0:
                mom_pts += 14
            else:
                mom_pts -= 8
        elif rsi14 < 35.0:
            mom_pts -= 10
    elif regime == "ranging":
        if pct_b <= 0.25 or rsi14 <= 38.0:
            mom_pts += 15
        elif pct_b <= 0.40 or rsi14 <= 45.0:
            mom_pts += 10
        elif rsi14 >= 65.0 or pct_b >= 0.80:
            mom_pts -= 8
    else:  # neutral / normal
        if 48.0 <= rsi14 <= 62.0:
            mom_pts += 15
        elif 40.0 <= rsi14 < 48.0:
            mom_pts += 10
        elif rsi14 > 70.0:
            mom_pts -= 8

    if divergence == "bullish":
        mom_pts += 5
    elif divergence == "bearish":
        mom_pts -= 6
    mom_pts = max(0, min(15, mom_pts))

    # 4. Volume & Money Flow (0-15 pts)
    vol_pts = 0
    if cmf20 >= 0.08 and mfi14 >= 55.0:
        vol_pts += 8
    elif cmf20 >= 0.02:
        vol_pts += 5
    elif cmf20 <= -0.10:
        vol_pts -= 8

    if squeeze_fired:
        vol_pts += 7
    elif volume_breakout:
        vol_pts += 6
    elif vol_ratio >= 1.5:
        vol_pts += 4
    elif squeeze_on:
        vol_pts += 2
    vol_pts = max(0, min(15, vol_pts))

    # 5. Market Microstructure & Whale Flow (0-15 pts)
    micro_pts = 0
    if whale_alert in ["WHALE_ACCUMULATION", "BULLISH_WHALE_WALL"]:
        micro_pts += 5
    elif whale_alert in ["WHALE_DISTRIBUTION", "BEARISH_WHALE_WALL"]:
        micro_pts -= 8

    if ob_imbalance >= 0.58:
        micro_pts += 5
    elif ob_imbalance >= 0.52:
        micro_pts += 3
    elif ob_imbalance < 0.46:
        micro_pts -= 5

    if taker_ratio >= 1.05:
        micro_pts += 3
    elif taker_ratio < 0.95:
        micro_pts -= 3

    if funding_alert == "SHORT_SQUEEZE_ALERT":
        micro_pts += 4
    elif funding_alert == "LONG_FLUSH_ALERT":
        micro_pts -= 8
    micro_pts = max(0, min(15, micro_pts))

    # 6. Macro, Efficiency & Sentiment (0-10 pts)
    macro_pts = 0
    if chop14 < 45.0:
        macro_pts += 4
    elif chop14 > 61.8:
        macro_pts -= 4

    if news_sent == "bullish":
        macro_pts += 4
    elif news_sent == "cautious_bullish":
        macro_pts += 2
    elif news_sent == "bearish":
        macro_pts -= 4

    if event_risk == "high":
        macro_pts -= 6
    macro_pts = max(0, min(10, macro_pts))

    raw_total = trend_pts + rs_pts + mom_pts + vol_pts + micro_pts + macro_pts
    total_score = max(0, min(100, int(round(raw_total))))
    breakdown = {
        "trend_mtf": trend_pts,
        "relative_strength": rs_pts,
        "momentum": mom_pts,
        "volume_flow": vol_pts,
        "microstructure": micro_pts,
        "macro_efficiency": macro_pts,
        "total": total_score
    }
    return total_score, breakdown


def evaluate_asset_decision(
    symbol: str,
    ticker: str,
    data: Dict[str, Any],
    portfolio: Dict[str, Any],
    sentiment: Dict[str, Any],
    regime: str,
    now: str,
    active_open_count: int = None,
    btc_flush_alert: bool = False,
    macro_flush_reason: str = ""
) -> Dict[str, Any]:
    """
    Evaluates trading rules for a single cryptocurrency asset using the 0-100 Setup Scoring Engine.

    :param symbol: Short symbol (e.g. "SOL")
    :param ticker: Binance ticker (e.g. "SOLUSDT")
    :param data: Technical indicator dictionary for this asset
    :param portfolio: Current portfolio dictionary
    :param sentiment: Sentiment data dictionary
    :param regime: Classified market regime string
    :param now: ISO timestamp string
    :return: Decision dictionary conforming to trade log schema
    """
    if not data or "error" in data or data.get("status") == "UNAVAILABLE":
        err_msg = data.get("error", "Data unavailable") if data else "Data unavailable"
        pos_map = {p["symbol"]: p for p in portfolio.get("positions", [])}
        fallback_price = float(pos_map.get(symbol, {}).get("entry_price", 0.0))
        return {
            "timestamp": now,
            "symbol": symbol,
            "action": "HOLD",
            "price": fallback_price,
            "qty": 0.0,
            "cost_or_proceeds": 0.0,
            "reasoning": f"Data fetch error or inactive ticker feed ({err_msg}). Skipping trade.",
            "confidence": 0.0,
            "setup_score": 0,
            "score_breakdown": {},
            "conviction_score": 0.0,
            "conviction_tier": "WEAK",
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
    ema12 = float(data.get("ema12", 0.0))
    ema26 = float(data.get("ema26", 0.0))
    ema50 = float(data.get("ema50", 0.0))
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
    # 0-100 COMPOSITE SETUP SCORING
    # -------------------------------------------------------------------------
    setup_score, score_breakdown = compute_setup_score(data, regime, asset_sentiment)

    if setup_score >= 82:
        conviction_tier = "A+"
        conviction_mult = 1.15
        final_conviction = min(0.98, max(0.85, round(setup_score / 100.0, 2)))
    elif setup_score >= 70:
        conviction_tier = "SOLID"
        conviction_mult = 1.00
        final_conviction = round(setup_score / 100.0, 2)
    elif setup_score >= 55:
        conviction_tier = "CAUTIOUS"
        conviction_mult = 0.75
        final_conviction = round(setup_score / 100.0, 2)
    else:
        conviction_tier = "WEAK"
        conviction_mult = 0.50
        final_conviction = max(0.10, round(setup_score / 100.0, 2))

    # -------------------------------------------------------------------------
    # VOLATILITY-ADJUSTED RISK-PARITY POSITION SIZING
    # -------------------------------------------------------------------------
    portfolio_cash = float(portfolio.get("cash", 10000.0))
    positions_val = sum(p.get("qty", 0.0) * float(p.get("entry_price", 0.0)) for p in portfolio.get("positions", []))
    curr_equity = portfolio_cash + positions_val
    if curr_equity <= 0:
        curr_equity = float(portfolio.get("starting_cash", 10000.0))

    dollar_risk = max(50.0, round(curr_equity * 0.010, 2))
    # Enforce -5.0% Stop-Loss max: risk distance cannot exceed 5.0%
    stop_distance_per_unit = min(price * 0.05, (2.0 * atr14) if atr14 > 0 else (price * 0.05))
    stop_distance_pct = stop_distance_per_unit / price if price > 0 else 0.05
    raw_risk_parity_size = dollar_risk / stop_distance_pct if stop_distance_pct > 0 else 800.0

    target_size = round(raw_risk_parity_size * conviction_mult, 2)
    suggested_pos_size = min(1200.0, max(250.0, target_size))

    action = "HOLD"
    reasoning = ""
    confidence = final_conviction
    amount_usd = 0.0
    trade_pnl_pct = 0.0
    trade_profit_usd = 0.0
    trade_cost_basis = 0.0

    # -------------------------------------------------------------------------
    # 1. EVALUATE ACTIVE OPEN POSITIONS (Chandelier + Dynamic Profit-Lock + Runner Protection)
    # -------------------------------------------------------------------------
    if is_open:
        pos = pos_map[symbol]
        entry_p = float(pos.get("entry_price", price))
        highest_p = max(float(pos.get("highest_price", entry_p)), price)
        pnl_pct = ((price - entry_p) / entry_p) * 100 if entry_p > 0 else 0.0
        trade_cost_basis = float(pos.get("cost_basis", 0.0))
        trade_pnl_pct = pnl_pct
        trade_profit_usd = (pnl_pct / 100.0) * trade_cost_basis

        # Chandelier / ATR trailing stop with hard maximum -5.0% Stop-Loss floor
        max_sl_floor = round(entry_p * 0.95, 4)
        raw_chandelier_stop = round(highest_p - (2.0 * atr14), 4) if atr14 > 0 else max_sl_floor
        trade_chandelier_stop = max(max_sl_floor, raw_chandelier_stop)
        std_trail = float(pos.get("trailing_stop_price", max_sl_floor))
        std_trail = max(std_trail, max_sl_floor)
        trailing_stop = max(std_trail, trade_chandelier_stop)
        if pos.get("tp1_hit", False) or (btc_flush_alert and symbol != "BTC" and pnl_pct > 0):
            trailing_stop = max(trailing_stop, entry_p)

        peak_gain_pct = ((highest_p - entry_p) / entry_p) * 100 if entry_p > 0 else 0.0
        if peak_gain_pct >= PROFIT_LOCK_TRIGGER_PCT:
            if peak_gain_pct >= 8.0:
                lock_ratio = 0.88
            elif peak_gain_pct >= 6.0:
                lock_ratio = 0.82
            elif peak_gain_pct >= 4.0:
                lock_ratio = 0.70
            else:
                lock_ratio = 0.50

            profit_lock_pct = max(1.0, peak_gain_pct * lock_ratio)
            dynamic_profit_stop = round(entry_p * (1.0 + (profit_lock_pct / 100.0)), 4)
            trailing_stop = max(trailing_stop, dynamic_profit_stop)

        # Strictly monotonic non-decreasing
        trailing_stop = max(trailing_stop, std_trail)
        tp1_hit = pos.get("tp1_hit", False)

        # 1. TP1 Partial Profit Scaling (+10% gain lock-in)
        if pnl_pct >= 10.0 and not tp1_hit:
            action = "TRIM"
            confidence = 0.92
            trim_profit = trade_profit_usd * 0.5
            reasoning = (
                f"Take Profit 1 (TP1) hit (+{pnl_pct:.2f}% vs +10% target). Taking 50% profit off the table into cash (+{trim_profit:+.2f} USD), "
                f"locking runner trailing stop to breakeven (${entry_p:.4f})."
            )
        # 2. Trailing / Dynamic Profit-Lock / Chandelier Stop Breach Exit
        elif price < trailing_stop:
            action = "SELL"
            confidence = 0.92
            locked_ret_pct = ((trailing_stop - entry_p) / entry_p) * 100 if entry_p > 0 else 0.0
            if locked_ret_pct > 0:
                reasoning = (
                    f"Dynamic Profit-Lock Triggered: Price ${price:.4f} dropped below ratcheted profit stop (${trailing_stop:.4f}, "
                    f"+{locked_ret_pct:.2f}% locked profit from ${entry_p:.4f} entry). Realized PnL: {trade_profit_usd:+.2f} USD ({pnl_pct:+.2f}%). Executing SELL to bank gains."
                )
            else:
                reasoning = (
                    f"Stop-Loss Triggered: Price ${price:.4f} breached maximum -5.0% Stop-Loss level (${trailing_stop:.4f}, "
                    f"{pnl_pct:+.2f}% vs -5.00% max). Realized PnL: {trade_profit_usd:+.2f} USD. Executing SELL to cut loss."
                )
        # 3. BTC Macro Flush Defense: Exit underwater altcoins (<= -2.5%) during a macro BTC dump
        elif btc_flush_alert and symbol != "BTC" and pnl_pct <= -2.5:
            action = "SELL"
            confidence = 0.90
            reasoning = (
                f"🚨 BTC Macro Flush Circuit Breaker Triggered: {macro_flush_reason}. "
                f"Altcoin position is underwater ({pnl_pct:.2f}% from ${entry_p:.4f} entry). Realized Loss: {trade_profit_usd:+.2f} USD. "
                f"Executing defensive SELL to prevent altcoin beta cascade."
            )
        # 4. Ranging Regime Mean-Reversion Exit (Bank range profit at upper band)
        elif regime == "ranging" and (pct_b >= 0.85 or rsi14 >= 65.0) and pnl_pct > 0.5:
            action = "SELL"
            confidence = 0.88
            reasoning = f"Mean-reversion exit in ranging market: Price reached upper Bollinger Band (%B {pct_b:.2f}) with RSI {rsi14:.2f}. Banking range profit (+{pnl_pct:.2f}%)."
        # 5. Overbought & Bearish Divergence (Protect Runners in Strong Bull Trends)
        elif rsi14 >= 75.0 and divergence == "bearish":
            if regime == "bullish_trend" and pnl_pct >= 5.0 and not tp1_hit:
                action = "TRIM"
                confidence = 0.90
                trim_profit = trade_profit_usd * 0.33
                reasoning = (
                    f"Bullish Trend Overbought Pullback Defense: RSI is elevated ({rsi14:.2f}) with bearish divergence, but asset is in a strong macro bull trend (+{pnl_pct:.2f}%). "
                    f"Executing partial TRIM (33% size) to bank +{trim_profit:+.2f} USD while preserving core runner."
                )
            elif regime == "bullish_trend" and tp1_hit:
                action = "HOLD"
                confidence = 0.85
                reasoning = (
                    f"Runner position in strong bull trend (+{pnl_pct:.2f}%). RSI is elevated ({rsi14:.2f}) with divergence, "
                    f"but core runner is protected by trailing stop (${trailing_stop:.4f}). Holding runner to let trend extend."
                )
            else:
                action = "SELL"
                confidence = 0.88
                reasoning = f"Overbought RSI ({rsi14:.2f}) with bearish divergence in {regime} regime. Executing SELL to bank gains (+{pnl_pct:.2f}%)."
        # 6. Trend Breakdown Exit
        elif trend_1d == "bearish" and pnl_pct < -2.0:
            action = "SELL"
            confidence = 0.88
            reasoning = f"Daily trend bias flipped to bearish with negative position return ({pnl_pct:.2f}%). Cutting loss to preserve capital."
        # 7. Heavy Whale Distribution Exit
        elif whale_alert == "WHALE_DISTRIBUTION" and cmf20 <= -0.18 and pnl_pct < 2.0:
            action = "SELL"
            confidence = 0.88
            reasoning = f"Heavy institutional distribution detected (Whale Alert '{whale_alert}', CMF {cmf20:.4f}). Exiting to avoid institutional dump."
        else:
            action = "HOLD"
            confidence = final_conviction
            runner_tag = ""
            if tp1_hit:
                runner_tag = " [RUNNER - ZERO RISK]"
            elif peak_gain_pct >= PROFIT_LOCK_TRIGGER_PCT:
                locked_gain = ((trailing_stop - entry_p) / entry_p) * 100
                runner_tag = f" [🔒 PROFIT-LOCK ACTIVE: Stop at ${trailing_stop:.4f} locks +{locked_gain:.2f}% profit]"

            if pnl_pct >= 0:
                reasoning = f"Active position in profit (+{pnl_pct:.2f}% from ${entry_p:.4f} entry){runner_tag} (Setup Score: {setup_score}/100, {conviction_tier}). Price ${price:.4f} comfortably above trailing stop (${trailing_stop:.4f}); holding full amount."
            else:
                reasoning = f"Active position intact ({pnl_pct:.2f}% from ${entry_p:.4f} entry) (Setup Score: {setup_score}/100, {conviction_tier}). Price ${price:.4f} is well above trailing stop (${trailing_stop:.4f}); trend structure intact."

    # -------------------------------------------------------------------------
    # 2. EVALUATE WATCHLIST CANDIDATES FOR BUY ENTRIES (Scoring Engine + Hard Safety Vetoes)
    # -------------------------------------------------------------------------
    else:
        open_count = active_open_count if active_open_count is not None else len(portfolio.get("positions", []))
        cash = float(portfolio.get("cash", 0.0))

        # Hard Safety Vetoes
        if btc_flush_alert and symbol != "BTC":
            action = "HOLD"
            confidence = 0.90
            reasoning = f"🚨 BTC Macro Flush Alert Active ({macro_flush_reason}). Vetoing new altcoin buy entries to preserve liquid cash."
        elif regime == "volatility_crash":
            action = "HOLD"
            confidence = 0.85
            reasoning = "Macro market regime is 'volatility_crash'. New buy entries are vetoed to prioritize capital preservation."
        elif funding_alert == "LONG_FLUSH_ALERT":
            action = "HOLD"
            confidence = 0.85
            reasoning = f"Overcrowded long leverage (Funding {funding_rate:.6f} >= +0.03%). Vetoing buy entry to avoid long liquidation flush."
        elif whale_alert in ["WHALE_DISTRIBUTION", "BEARISH_WHALE_WALL"] and cmf20 <= -0.05:
            action = "HOLD"
            confidence = 0.85
            reasoning = f"Whale flow alert '{whale_alert}' with negative CMF ({cmf20:.4f}). Institutional selling pressure vetoes buy entry."
        elif should_veto_on_rsi(symbol, rsi14, adx14, ema12, ema26, ema50, price)[0]:
            action = "HOLD"
            confidence = 0.85
            reasoning = should_veto_on_rsi(symbol, rsi14, adx14, ema12, ema26, ema50, price)[1]
        elif rsi_1h > (78.0 if symbol in ["BTC", "ETH"] else 72.0) or price_vs_ema20_1h > (6.0 if symbol in ["BTC", "ETH"] else 4.5):
            limit_rsi = 78.0 if symbol in ["BTC", "ETH"] else 72.0
            limit_ema = 6.0 if symbol in ["BTC", "ETH"] else 4.5
            action = "HOLD"
            confidence = 0.80
            reasoning = f"1H timeframe is overextended (1H RSI {rsi_1h:.1f} > {limit_rsi:.0f}, price +{price_vs_ema20_1h:.2f}% vs EMA20 > {limit_ema:.1f}%). Awaiting intraday pullback."
        elif open_count >= MAX_POSITIONS:
            action = "HOLD"
            confidence = 0.80
            reasoning = f"Portfolio position cap reached ({open_count}/{MAX_POSITIONS} max positions). Candidate setup score: {setup_score}/100 ({conviction_tier}). Eligible for tournament rotation if score >= 80."
        elif cash < suggested_pos_size:
            action = "HOLD"
            confidence = 0.80
            reasoning = f"Setup qualified (Score: {setup_score}/100, {conviction_tier}) but insufficient liquid cash buffer (${cash:.2f} vs ${suggested_pos_size:.2f})."
        elif setup_score >= 70:
            action = "BUY"
            amount_usd = suggested_pos_size
            confidence = final_conviction
            squeeze_tag = " [⚡ TTM SQUEEZE FIRED]" if squeeze_fired else ""
            breakout_tag = f" [🚀 BREAKOUT Vol {vol_ratio:.1f}x]" if volume_breakout else ""
            cmf_tag = f" [💵 CMF: {cmf20:+.4f}]" if cmf20 >= 0.05 else ""
            reasoning = (
                f"BULLISH CONFLUENCE ENTRY ({conviction_tier} TIER, Score: {setup_score}/100): 1D/4H trend aligned, "
                f"healthy momentum (RSI {rsi14:.1f}), RS Rank #{rs_rank} (Score: {rs_score:+.2f}), "
                f"Order Book imbalance {ob_imbalance:.3f}.{breakout_tag}{squeeze_tag}{cmf_tag} Initiating {conviction_tier} allocation (${suggested_pos_size:.2f})."
            )
        else:
            action = "HOLD"
            confidence = final_conviction
            reasoning = f"Candidate score {setup_score}/100 ({conviction_tier}) below 70-point execution threshold. Awaiting stronger technical alignment."

    return {
        "timestamp": now,
        "symbol": symbol,
        "action": action,
        "price": price,
        "amount_usd": amount_usd,
        "qty": 0.0,
        "cost_or_proceeds": 0.0,
        "pnl_pct": round(trade_pnl_pct, 2),
        "profit_usd": round(trade_profit_usd, 2),
        "cost_basis": round(trade_cost_basis, 2),
        "reasoning": reasoning,
        "confidence": confidence,
        "setup_score": setup_score,
        "score_breakdown": score_breakdown,
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
    btc_d = market_ctx.get("btc_dominance")
    eth_d = market_ctx.get("eth_dominance")
    btc_d_str = f"{btc_d:.2f}%" if isinstance(btc_d, (int, float)) else "N/A"
    eth_d_str = f"{eth_d:.2f}%" if isinstance(eth_d, (int, float)) else "N/A"
    regime = market_ctx.get("market_regime", "neutral")

    lines = []
    lines.append("# 🚀 Daily Crypto Paper-Trading Agent — Executive Summary Report\n")
    lines.append(f"**Execution Timestamp:** `{now}`  ")
    lines.append("**Operational Status:** Autonomous Hourly Paper-Trading Pass Completed  ")
    lines.append(f"**Tracked Assets Universe:** {len(decisions)} Pre-Screened Shariah-Compliant Assets  \n")
    lines.append("---\n")

    # 1. Executive Portfolio Header
    lines.append("## 1. 💼 Executive Portfolio Header\n")
    lines.append("| Metric | Current Value | Baseline / Target | Notes |")
    lines.append("| :--- | :--- | :--- | :--- |")
    lines.append(f"| **Total Portfolio Value** | **${curr_equity:,.2f} USD** | ${start_cash:,.2f} Starting Cash | **{'+' if total_pnl_usd >= 0 else ''}${total_pnl_usd:,.2f} Net P&L ({'+' if total_pnl_pct >= 0 else ''}{total_pnl_pct:.2f}%)** |")
    lines.append(f"| **Cash Balance** | **${cash:,.2f} USD** | Min 20% Reserve | **{(cash / curr_equity * 100):.2f}%** Capital in Liquid Cash |")
    pos_val = curr_equity - cash
    lines.append(f"| **Active Positions Value** | **${pos_val:,.2f} USD** | Max {MAX_POSITIONS} Positions | **{(pos_val / curr_equity * 100):.2f}%** Capital Allocated |")
    lines.append(f"| **Open Positions Count** | **{len(positions)} / {MAX_POSITIONS}** | Max Cap: {MAX_POSITIONS} | {MAX_POSITIONS - len(positions)} Position Slots Available |")
    lines.append(f"| **Total Executed Trades** | **{portfolio.get('trade_counter', 0)} Trades** | — | Audit trail synchronized in CSV |")
    lines.append("\n---\n")

    # 2. Institutional Risk & Benchmark Metrics
    lines.append("## 2. 📊 Institutional Risk & Benchmark Metrics\n")
    bench_ret = float(metrics.get("benchmark_return_pct") or 0.0)
    alpha = total_pnl_pct - bench_ret
    lines.append("| Risk / Performance Metric | Portfolio Value | Benchmark (50/50 BTC/ETH) | Performance Alpha |")
    lines.append("| :--- | :--- | :--- | :--- |")
    lines.append(f"| **Total Cumulative Return** | **{'+' if total_pnl_pct >= 0 else ''}{total_pnl_pct:.2f}%** | **{'+' if bench_ret >= 0 else ''}{bench_ret:.2f}%** | **{'+' if alpha >= 0 else ''}{alpha:.2f}% Alpha** |")
    lines.append(f"| **Current Benchmark Value** | ${curr_equity:,.2f} | ${bench_val:,.2f} | **{'+' if (curr_equity - bench_val) >= 0 else ''}${(curr_equity - bench_val):,.2f} Value Premium** |")
    lines.append(f"| **Max Drawdown (%)** | **{float(metrics.get('max_drawdown_pct') or 0.0):.2f}%** | Macro Benchmark Variance | Capital preservation filter active |")
    lines.append(f"| **Calmar Ratio** | **{float(metrics.get('calmar_ratio') or 0.0):.2f}** | — | Return to max drawdown ratio |")
    lines.append(f"| **Rolling Sharpe Ratio** | **{float(metrics.get('sharpe_ratio') or 0.0):.2f}** | — | Annualized risk-adjusted return |")
    lines.append(f"| **Rolling Sortino Ratio** | **{float(metrics.get('sortino_ratio') or 0.0):.2f}** | — | Downside-volatility weighted |")
    lines.append("\n---\n")

    # 3. Macro Market Regime & Context
    btc_flush_alert = market_ctx.get("btc_flush_alert", False)
    macro_flush_reason = market_ctx.get("macro_flush_reason", "BTC technical structure healthy")
    cb_status = f"🚨 **MACRO FLUSH ACTIVE** ({macro_flush_reason})" if btc_flush_alert else "🟢 **NORMAL (Healthy)**"

    lines.append("## 3. 🌐 Macro Market Regime & Sentiment Context\n")
    lines.append(f"* **Market Regime:** `{regime}`")
    lines.append(f"* **BTC Macro Circuit Breaker:** {cb_status}")
    lines.append(f"* **Fear & Greed Index:** **{fg_val} / 100 ({fg_class})**")
    lines.append(f"* **BTC Dominance:** **{btc_d_str}** | **ETH Dominance:** **{eth_d_str}**")
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
    lines.append("| Asset | Action | Live Price | Setup Score | RSI(14) | RS Rank | Conviction Tier | CMF(20) | Squeeze / Breakout | Chandelier Stop | Decision Rationale |")
    lines.append("| :--- | :---: | :--- | :---: | :--- | :--- | :---: | :---: | :---: | :---: | :--- |")
    for d in decisions:
        rs_str = f"#{d.get('rs_rank', '-')} ({d.get('rs_score', 0.0):+.2f})"
        tier_str = f"`{d.get('conviction_tier', 'SOLID')}`"
        score_val = d.get('setup_score', int(float(d.get('confidence', 0.5)) * 100))
        score_str = f"**{score_val}/100**"
        cmf_val = float(d.get("cmf20", 0.0))
        cmf_str = f"`{cmf_val:+.3f}`"
        sq_str = "⚡ **FIRED**" if d.get("squeeze_fired") else ("🟠 SQUEEZE" if d.get("squeeze_on") else ("🚀 BREAKOUT" if d.get("volume_breakout") else "`NORMAL`"))
        ch_stop = f"${float(d.get('chandelier_stop', 0)):.4f}"
        lines.append(
            f"| **{d.get('symbol')}** | **{d.get('action')}** | ${d.get('price', 0):.4f} | "
            f"{score_str} | {d.get('rsi14', 0):.2f} | {rs_str} | {tier_str} | {cmf_str} | "
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


def _run_trader_pass_internal(mode: str = "AUTO", dry_run: bool = False, silent: bool = False) -> Dict[str, Any]:
    """
    Main orchestrator for paper-trading pass with Dual-Cadence Architecture:
    - FAST_GUARDIAN (Every 5 mins): Fast risk check for BTC + open positions only.
      Ratchets dynamic profit-locks, executes stop/TP1 exits, and cuts on BTC macro flush.
      Completely silent on Discord unless an order executes.
    - FULL (Hourly on :00): Full universe scan across 22 assets, evaluates new BUY entries,
      refreshes macro news sentiment, and dispatches comprehensive Discord portfolio embed.
    """
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    watchlist_path = os.path.join(ROOT_DIR, "state", "watchlist.json")
    research_path = os.path.join(ROOT_DIR, "state", "latest_research.json")
    sentiment_path = os.path.join(ROOT_DIR, "state", "latest_sentiment.json")
    decisions_path = os.path.join(ROOT_DIR, "state", "latest_decisions.json")
    summary_path = os.path.join(ROOT_DIR, "state", "latest_summary.md")

    # Resolve Execution Mode
    mode_clean = mode.upper()
    if mode_clean in ["FAST", "FAST_GUARDIAN"]:
        actual_mode = "FAST_GUARDIAN"
    elif mode_clean in ["FULL", "HOURLY"]:
        actual_mode = "FULL"
    else:  # AUTO
        current_minute = datetime.datetime.now(datetime.timezone.utc).minute
        if current_minute in [58, 59, 0, 1, 2]:
            actual_mode = "FULL"
        else:
            actual_mode = "FAST_GUARDIAN"

    # 1. Load Persistent Portfolio
    portfolio = load_portfolio()
    open_positions = portfolio.get("positions", [])
    open_symbols = [p["symbol"] for p in open_positions]

    # -------------------------------------------------------------------------
    # A. FAST RISK GUARDIAN (Runs every 5 mins on :05, :10, :15 ... :55)
    # -------------------------------------------------------------------------
    if actual_mode == "FAST_GUARDIAN":
        if not silent:
            print(f"🛡️ [FAST GUARDIAN] Checking risk & profit-locks for {len(open_symbols)} open positions + BTC...")

        research_data = run_fast_risk_research(open_symbols=open_symbols, output_path=research_path)
        market_ctx = research_data.get("market_context", {})
        ta_data = research_data.get("technical_analysis", {})
        regime = market_ctx.get("market_regime", "neutral")
        btc_flush_alert = market_ctx.get("btc_flush_alert", False)
        macro_flush_reason = market_ctx.get("macro_flush_reason", "")

        # Reuse cached sentiment
        sentiment_data = {}
        if os.path.exists(sentiment_path):
            try:
                with open(sentiment_path, "r") as f:
                    sentiment_data = json.load(f)
            except Exception:
                pass

        decisions = []
        for p in open_positions:
            sym = p.get("symbol")
            ticker = sym if sym.endswith("USDT") else f"{sym}USDT"
            asset_ta = ta_data.get(ticker, {})
            d = evaluate_asset_decision(
                symbol=sym,
                ticker=ticker,
                data=asset_ta,
                portfolio=portfolio,
                sentiment=sentiment_data,
                regime=regime,
                now=now,
                btc_flush_alert=btc_flush_alert,
                macro_flush_reason=macro_flush_reason
            )
            decisions.append(d)

        decisions_payload = {
            "timestamp": now,
            "mode": "FAST_GUARDIAN",
            "decisions": decisions
        }
        with open(decisions_path, "w") as f:
            json.dump(decisions_payload, f, indent=2)

        # Execute trades (ratchets trailing stops even on HOLD, or executes SELL/TRIM)
        if not dry_run:
            updated_portfolio = execute_trade_pass(decisions_payload)
        else:
            updated_portfolio = portfolio

        executed_actions = [d for d in decisions if d.get("action") in ["BUY", "SELL", "TRIM"]]

        # Discord Notification: SILENT unless an action executed!
        if not dry_run and len(executed_actions) > 0:
            if not silent:
                print(f"📢 [FAST GUARDIAN] Action executed ({len(executed_actions)} orders)! Dispatching Discord alert...")
            send_discord_notification(
                portfolio=updated_portfolio,
                decisions=decisions,
                regime=regime
            )
        elif not silent:
            print(f"🤫 [FAST GUARDIAN] Pass complete. Monitored {len(open_positions)} positions, 0 orders executed. Remaining silent on Discord.")

        return {
            "status": "success",
            "mode": "FAST_GUARDIAN",
            "timestamp": now,
            "portfolio": updated_portfolio,
            "decisions_count": len(decisions),
            "executed_count": len(executed_actions),
            "summary_path": summary_path
        }

    # -------------------------------------------------------------------------
    # B. FULL ALPHA SCANNER (Runs Hourly on :00)
    # -------------------------------------------------------------------------
    if not silent:
        print(f"🚀 [1/5] [FULL ALPHA SCANNER] Running full market research across tracked universe...")

    # 1. Technical Research (1D & 4H across all 22 assets)
    research_data = run_research(watchlist_path=watchlist_path, output_path=research_path)
    market_ctx = research_data.get("market_context", {})
    ta_data = research_data.get("technical_analysis", {})
    regime = market_ctx.get("market_regime", "neutral")

    # 2. Sentiment Research
    if not silent:
        print(f"📰 [2/5] Querying news headlines and macro sentiment...")
    sentiment_data = analyze_news_sentiment(output_path=sentiment_path)

    # 3. Decision Engine (Open Positions first, then RS-Ranked Candidates)
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

    btc_flush_alert = market_ctx.get("btc_flush_alert", False)
    macro_flush_reason = market_ctx.get("macro_flush_reason", "")

    decisions = []
    # Evaluate open positions
    open_decisions = []
    for sym, ticker in open_items:
        asset_ta = ta_data.get(ticker, {})
        d = evaluate_asset_decision(
            symbol=sym,
            ticker=ticker,
            data=asset_ta,
            portfolio=portfolio,
            sentiment=sentiment_data,
            regime=regime,
            now=now,
            btc_flush_alert=btc_flush_alert,
            macro_flush_reason=macro_flush_reason
        )
        open_decisions.append(d)
        decisions.append(d)

    # Calculate realistic projected open count and available cash after open position exits/trims
    retained_positions = [d for d in open_decisions if d.get("action") != "SELL"]
    current_open_count = len(retained_positions)
    sim_cash = float(portfolio.get("cash", 0.0))

    for d in open_decisions:
        pos_match = next((p for p in portfolio.get("positions", []) if p["symbol"] == d["symbol"]), None)
        if not pos_match:
            continue
        fill_p = float(d.get("price", 0.0)) * 0.9995
        if d.get("action") == "SELL":
            gross = float(pos_match.get("qty", 0.0)) * fill_p
            sim_cash += (gross - gross * 0.0010)
        elif d.get("action") == "TRIM":
            gross = (float(pos_match.get("qty", 0.0)) * 0.5) * fill_p
            sim_cash += (gross - gross * 0.0010)

    # Evaluate candidate assets (leaders get priority for available slots)
    sim_portfolio = dict(portfolio)
    candidate_decisions = []

    for sym, ticker in candidate_items:
        asset_ta = ta_data.get(ticker, {})
        sim_portfolio["cash"] = sim_cash
        d = evaluate_asset_decision(
            symbol=sym,
            ticker=ticker,
            data=asset_ta,
            portfolio=sim_portfolio,
            sentiment=sentiment_data,
            regime=regime,
            now=now,
            active_open_count=current_open_count,
            btc_flush_alert=btc_flush_alert,
            macro_flush_reason=macro_flush_reason
        )
        candidate_decisions.append(d)

    # Separate candidates that triggered BUY from others
    raw_buys = [d for d in candidate_decisions if d.get("action") == "BUY"]
    non_buys = [d for d in candidate_decisions if d.get("action") != "BUY"]

    accepted_buys = []
    rejected_buys = []

    if raw_buys:
        # 1. Pairwise Correlation Gate: Greedily accept highest-score setups, vetoing correlated redundant bets (> 0.75)
        corr_accepted, corr_rejected = filter_simultaneous_entries(
            candidates=raw_buys,
            market_data=research_data,
            open_positions=retained_positions,
            max_pairwise_corr=MAX_PAIRWISE_CORR
        )
        rejected_buys.extend(corr_rejected)

        # 2. Portfolio Beta Cap Check: Verify aggregate BTC beta exposure does not exceed 60% of equity
        portfolio_equity = float(portfolio.get("portfolio_value", 0.0))
        if portfolio_equity <= 0:
            portfolio_equity = float(portfolio.get("cash", 0.0)) + sum(float(p.get("cost_basis", 0.0)) for p in portfolio.get("positions", []))

        for cand in corr_accepted:
            size_usd = float(cand.get("amount_usd", 250.0))
            active_sim_positions = retained_positions + [
                {"symbol": ab["symbol"], "cost_basis": float(ab.get("amount_usd", 250.0)), "qty": float(ab.get("amount_usd", 250.0)) / max(0.0001, float(ab.get("price", 1.0)))}
                for ab in accepted_buys
            ]
            can_open, beta_reason = can_open_new_position(
                symbol=cand["symbol"],
                size_usd=size_usd,
                open_positions=active_sim_positions,
                ta_data=ta_data,
                portfolio_value=portfolio_equity,
                max_beta_pct=MAX_PORTFOLIO_BETA_PCT
            )
            if not can_open:
                cand_copy = dict(cand)
                cand_copy["action"] = "HOLD"
                cand_copy["reasoning"] = beta_reason
                rejected_buys.append(cand_copy)
            elif current_open_count >= MAX_POSITIONS:
                cand_copy = dict(cand)
                cand_copy["action"] = "HOLD"
                cand_copy["reasoning"] = f"Portfolio position cap reached ({current_open_count}/{MAX_POSITIONS} max positions). Candidate setup score: {cand.get('setup_score')}/100."
                rejected_buys.append(cand_copy)
            elif sim_cash < size_usd:
                cand_copy = dict(cand)
                cand_copy["action"] = "HOLD"
                cand_copy["reasoning"] = f"Setup qualified (Score: {cand.get('setup_score')}/100) but insufficient liquid cash buffer (${sim_cash:.2f} vs ${size_usd:.2f})."
                rejected_buys.append(cand_copy)
            else:
                accepted_buys.append(cand)
                pos_symbols.add(cand["symbol"])
                current_open_count += 1
                sim_cash -= size_usd

    # Reassemble all candidate decisions in original order and append to decisions
    cand_lookup = {d["symbol"]: d for d in (accepted_buys + rejected_buys + non_buys)}
    for sym, _ in candidate_items:
        if sym in cand_lookup:
            decisions.append(cand_lookup[sym])

    # -------------------------------------------------------------------------
    # 3B. PORTFOLIO TOURNAMENT (Dynamic Rebalancing)
    # -------------------------------------------------------------------------
    # When portfolio is at position cap (>= MAX_POSITIONS) or low on cash:
    # High-conviction candidates (Score >= 80) challenge stagnant/losing active holdings (Score < 50, PnL < 1.0%).
    if current_open_count >= MAX_POSITIONS or sim_cash < 250.0:
        challengers = [
            d for d in candidate_decisions
            if d.get("action") == "HOLD"
            and d.get("setup_score", 0) >= 80
            and not (btc_flush_alert and d.get("symbol") != "BTC")
            and d.get("price", 0) > 0
        ]
        challengers.sort(key=lambda x: (x.get("setup_score", 0), x.get("rs_score", 0.0)), reverse=True)

        eligible_laggards = []
        for d in open_decisions:
            if d.get("action") == "HOLD":
                pos_match = next((p for p in portfolio.get("positions", []) if p["symbol"] == d["symbol"]), None)
                if not pos_match:
                    continue
                is_tp1 = pos_match.get("tp1_hit", False)
                pnl = float(d.get("pnl_pct", 0.0))
                h_score = d.get("setup_score", 0)
                if not is_tp1 and pnl < 1.0 and h_score < 50:
                    eligible_laggards.append((h_score, pnl, d, pos_match))

        eligible_laggards.sort(key=lambda x: (x[0], x[1]))

        if challengers and eligible_laggards:
            top_cand = challengers[0]
            laggard_score, laggard_pnl, laggard_d, laggard_pos = eligible_laggards[0]
            cand_score = top_cand.get("setup_score", 0)
            score_gap = cand_score - laggard_score

            if score_gap >= 25:
                laggard_sym = laggard_d.get("symbol")
                cand_sym = top_cand.get("symbol")
                laggard_d["action"] = "SELL"
                laggard_d["confidence"] = 0.88
                laggard_d["reasoning"] = (
                    f"🔄 Portfolio Tournament Rotation: Replacing stagnant laggard {laggard_sym} "
                    f"(Score: {laggard_score}/100, Return: {laggard_pnl:+.2f}%) with higher-conviction "
                    f"momentum setup {cand_sym} (Score: {cand_score}/100, Confluence Delta: +{score_gap} pts)."
                )

                fill_p = float(laggard_d.get("price", 0.0)) * 0.9995
                gross_rec = float(laggard_pos.get("qty", 0.0)) * fill_p
                net_rec = gross_rec - (gross_rec * 0.0010)
                sim_cash += net_rec

                alloc_size = min(top_cand.get("suggested_pos_size", 800.0), max(250.0, sim_cash * 0.85))
                top_cand["action"] = "BUY"
                top_cand["amount_usd"] = alloc_size
                top_cand["confidence"] = top_cand.get("conviction_score", 0.85)
                top_cand["reasoning"] = (
                    f"🏆 TOURNAMENT PROMOTION: Promoted into portfolio via rotation replacement of "
                    f"laggard {laggard_sym} (Score {cand_score}/100 vs {laggard_score}/100, +{score_gap} pt advantage). "
                    f"{top_cand.get('reasoning', '')}"
                )

                if not silent:
                    print(f"   🏆 [PORTFOLIO TOURNAMENT] Rotated laggard {laggard_sym} ({laggard_score}/100) -> {cand_sym} ({cand_score}/100, +{score_gap} pts edge)")

    decisions_payload = {
        "timestamp": now,
        "mode": "FULL",
        "decisions": decisions
    }
    with open(decisions_path, "w") as f:
        json.dump(decisions_payload, f, indent=2)

    # 4. Trade Execution & State Persistence
    if not silent:
        print(f"⚡ [4/5] Syncing state and updating portfolio...")
    if not dry_run:
        updated_portfolio = execute_trade_pass(decisions_payload)
    else:
        updated_portfolio = portfolio
        if not silent:
            print("   [DRY-RUN] Skipped persistent trade execution and portfolio write.")

    # 5. Generate & Save Executive Report
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

    # 6. Dispatch Discord Webhook Notification (ALWAYS on Hourly Full Scan)
    if not dry_run:
        send_discord_notification(
            portfolio=updated_portfolio,
            decisions=decisions,
            regime=regime
        )

    return {
        "status": "success",
        "mode": "FULL",
        "timestamp": now,
        "portfolio": updated_portfolio,
        "decisions_count": len(decisions),
        "summary_path": summary_path
    }


def run_trader_pass(mode: str = "AUTO", dry_run: bool = False, silent: bool = False) -> Dict[str, Any]:
    """
    Thread/Process-safe wrapper around _run_trader_pass_internal.
    Uses ExecutionLock to prevent concurrent duplicate execution.
    """
    lock = ExecutionLock()
    if not lock.acquire():
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        msg = "Execution skipped: Previous pass is still running (Lock active)."
        if not silent:
            print(f"⏳ {msg}")
        return {
            "status": "skipped",
            "reason": msg,
            "timestamp": now
        }
    try:
        return _run_trader_pass_internal(mode=mode, dry_run=dry_run, silent=silent)
    finally:
        lock.release()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ANTItrading Autonomous Twice-Daily Paper-Trading Runner")
    parser.add_argument("--mode", type=str, default="AUTO", choices=["AUTO", "FULL", "FAST_GUARDIAN", "fast", "full"], help="Execution mode: AUTO, FULL, or FAST_GUARDIAN")
    parser.add_argument("--dry-run", action="store_true", help="Evaluate research and decisions without saving trades")
    parser.add_argument("--silent", action="store_true", help="Suppress terminal markdown rendering")
    args = parser.parse_args()

    run_trader_pass(mode=args.mode, dry_run=args.dry_run, silent=args.silent)
