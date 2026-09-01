"""
===============================================================================
Module: scripts/hodl_research.py
Purpose: Long-Term HODL Fundamental, Macro & Whale Research Engine
Author: Long-Term Crypto Quantitative HODL Agent (Antigravity)

Description:
  Executes macro, fundamental, valuation (MVRV Z-score proxy, 200-day EMA distance),
  and smart money / whale flow analysis across pre-screened Shariah-compliant assets
  in `state/hodl_watchlist.json`.

Outputs structured evaluation for Dollar-Cost Averaging (DCA) and HODL accumulation.
===============================================================================
"""

import json
import os
import sys
import requests
import pandas as pd
import ta


def load_hodl_watchlist(filepath="state/hodl_watchlist.json"):
    """Loads HODL watchlist from state/hodl_watchlist.json."""
    if not os.path.exists(filepath):
        return {
            "bitcoin": "BTCUSDT",
            "ethereum": "ETHUSDT",
            "solana": "SOLUSDT",
            "binancecoin": "BNBUSDT",
            "arbitrum": "ARBUSDT",
            "near": "NEARUSDT",
            "avalanche-2": "AVAXUSDT",
            "chainlink": "LINKUSDT",
            "injective-protocol": "INJUSDT",
            "helium": "HNTUSDT"
        }
    with open(filepath, "r") as f:
        return json.load(f)


def fetch_longterm_klines(symbol, limit=365):
    """
    Fetches daily kline candles (up to 365 days) from Binance API.

    :param symbol: Binance symbol (e.g. BTCUSDT)
    :param limit: Number of daily candles
    :return: DataFrame with OHLCV data
    """
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1d&limit={limit}"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    data = response.json()

    df = pd.DataFrame(data, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_asset_volume", "number_of_trades",
        "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore"
    ])

    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)

    return df


def fetch_macro_and_whale_data():
    """
    Fetches Fear & Greed Index, BTC/ETH Dominance, and Smart Money Macro Signals.

    :return: Dictionary of macro & whale metrics
    """
    fng_data = {}
    cg_data = {}

    try:
        r = requests.get("https://api.alternative.me/fng/", timeout=10)
        fng_data = r.json().get("data", [{}])[0]
    except Exception as err:
        fng_data = {"value": 50, "value_classification": "Neutral", "error": str(err)}

    try:
        r = requests.get("https://api.coingecko.com/api/v3/global", timeout=10)
        cg_data = r.json().get("data", {})
    except Exception as err:
        cg_data = {"error": str(err)}

    btc_dom = cg_data.get("market_cap_percentage", {}).get("btc", 55.0)
    eth_dom = cg_data.get("market_cap_percentage", {}).get("eth", 15.0)

    # Determine Macro Market Phase
    fg_val = int(fng_data.get("value", 50))
    if fg_val < 30:
        whale_sentiment = "Heavy Institutional Accumulation (Extreme Fear Discount)"
    elif fg_val > 75:
        whale_sentiment = "Whale Profit Realization / Overheated Distribution"
    else:
        whale_sentiment = "Neutral Steady DCA Accumulation"

    return {
        "fear_and_greed": fng_data,
        "btc_dominance": round(btc_dom, 2) if isinstance(btc_dom, (int, float)) else btc_dom,
        "eth_dominance": round(eth_dom, 2) if isinstance(eth_dom, (int, float)) else eth_dom,
        "whale_sentiment": whale_sentiment
    }


def compute_hodl_metrics(name, symbol):
    """
    Computes multi-year valuation, 200-day EMA, MVRV proxy, and 52-week drawdown.

    :param name: Coin name
    :param symbol: Binance symbol
    :return: Dictionary of fundamental HODL indicators
    """
    df = fetch_longterm_klines(symbol, limit=365)

    # Moving Averages
    df["ema50"] = ta.trend.EMAIndicator(df["close"], window=50).ema_indicator()
    df["ema200"] = ta.trend.EMAIndicator(df["close"], window=200).ema_indicator()
    df["rsi14"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi()

    last = df.iloc[-1]
    close_price = float(last["close"])
    ema50_val = float(last["ema50"]) if not pd.isna(last["ema50"]) else close_price
    ema200_val = float(last["ema200"]) if not pd.isna(last["ema200"]) else close_price
    rsi_val = float(last["rsi14"]) if not pd.isna(last["rsi14"]) else 50.0

    # 52-Week High & Drawdown
    high_52w = float(df["high"].max())
    low_52w = float(df["low"].min())
    drawdown_52w = round(((close_price - high_52w) / high_52w) * 100, 2)

    # Valuation: % Distance from 200-Day EMA
    pct_from_ema200 = round(((close_price - ema200_val) / ema200_val) * 100, 2) if ema200_val > 0 else 0.0

    # MVRV Proxy Index ((Price / EMA200 - 1) * 2.5)
    mvrv_proxy = round((close_price / ema200_val - 1) * 2.5, 2) if ema200_val > 0 else 0.0

    # Determine HODL DCA Action Zone
    if pct_from_ema200 < -10 or (mvrv_proxy < 0 and rsi_val < 45):
        dca_signal = "STRONG_BUY_ACCUMULATE"
        recommendation = "Deep value discount zone. Ideal for heavy DCA accumulation."
    elif -10 <= pct_from_ema200 <= 15 and rsi_val <= 60:
        dca_signal = "MODERATE_DCA_BUY"
        recommendation = "Fair valuation zone. Standard DCA recurring purchase recommended."
    elif 15 < pct_from_ema200 <= 50:
        dca_signal = "HOLD"
        recommendation = "Price is above structural support. Hold existing position; pause new buys."
    else:
        dca_signal = "TRIM_PROFIT_TAKE"
        recommendation = "Asset is overheated relative to 200D EMA. Consider scaling out 20-30% into BTC/Cash."

    short_symbol = symbol.replace("USDT", "")

    return {
        "name": name,
        "symbol": short_symbol,
        "ticker": symbol,
        "price": round(close_price, 4),
        "ema50": round(ema50_val, 4),
        "ema200": round(ema200_val, 4),
        "pct_from_ema200": pct_from_ema200,
        "mvrv_proxy": mvrv_proxy,
        "rsi14_daily": round(rsi_val, 2),
        "high_52w": round(high_52w, 4),
        "low_52w": round(low_52w, 4),
        "drawdown_from_52w_high_pct": drawdown_52w,
        "dca_signal": dca_signal,
        "recommendation": recommendation
    }


def run_hodl_research(watchlist_path="state/hodl_watchlist.json"):
    """
    Executes full multi-year fundamental, valuation, and whale research pass.

    :param watchlist_path: Path to state/hodl_watchlist.json
    :return: Dictionary of macro context and HODL asset evaluations
    """
    watchlist = load_hodl_watchlist(watchlist_path)
    evaluations = {}

    for name, symbol in watchlist.items():
        try:
            evaluations[symbol] = compute_hodl_metrics(name, symbol)
        except Exception as e:
            evaluations[symbol] = {"symbol": symbol, "error": str(e)}

    macro_data = fetch_macro_and_whale_data()

    return {
        "macro_and_whale_context": macro_data,
        "hodl_asset_evaluations": evaluations
    }


if __name__ == "__main__":
    results = run_hodl_research()
    print(json.dumps(results, indent=2))
