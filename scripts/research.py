"""
===============================================================================
Module: scripts/research.py
Purpose: Daily Technical Analysis (TA) & Market Context Research Module
Author: Daily Crypto Paper-Trading Agent (Antigravity)

Description:
  This script performs full technical analysis on all assets defined in
  `state/watchlist.json`. It fetches 100 daily OHLCV candles from the public
  Binance API and computes key technical indicators using pandas & the `ta` library:
    - EMA (12, 26, 50)
    - RSI (14)
    - MACD Line, Signal, and Histogram
    - Momentum / ROC (10)
    - VMA (20) & Volume Ratio
    - Bollinger Bands (%B)
    - ATR (14)
    - Price/RSI Swing Divergence (Bullish / Bearish / None)
    - Overall Trend Bias (Bullish / Bearish / Neutral)

  Additionally, it fetches global market sentiment:
    - Crypto Fear & Greed Index (Alternative.me)
    - Bitcoin & Ethereum Market Dominance (CoinGecko)

Usage:
  python3 scripts/research.py [--watchlist state/watchlist.json]

Output:
  Prints a JSON object containing `market_context` and `technical_analysis` per asset.
===============================================================================
"""

import json
import os
import sys
import requests
import pandas as pd
import ta


def load_watchlist(filepath="state/watchlist.json"):
    """
    Loads the asset watchlist from a JSON file.

    :param filepath: Path to watchlist.json file
    :return: Dictionary mapping asset names to Binance ticker symbols (e.g. {"bitcoin": "BTCUSDT"})
    """
    if not os.path.exists(filepath):
        print(f"Error: Watchlist file '{filepath}' not found.", file=sys.stderr)
        return {}
    with open(filepath, "r") as f:
        return json.load(f)


def fetch_binance_klines(symbol, interval="1d", limit=100):
    """
    Fetches daily OHLCV candles from Binance API for a given symbol.

    :param symbol: Binance ticker symbol (e.g., BTCUSDT)
    :param interval: Candle timeframe (default "1d")
    :param limit: Number of candles (default 100)
    :return: pandas.DataFrame containing open, high, low, close, volume as floats
    """
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    raw_data = response.json()

    columns = [
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "qav", "num_trades", "tb_base", "tb_quote", "ignore"
    ]
    df = pd.DataFrame(raw_data, columns=columns)

    # Cast numerical columns from string to float
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)

    return df


def detect_rsi_divergence(df, order=3, lookback=40):
    """
    Detects bullish or bearish divergence between Price swing points and RSI(14).

    Logic:
      - Swing High: Price local maximum over `order` periods.
        Bearish divergence if recent swing high price > past swing high price, BUT RSI is lower.
      - Swing Low: Price local minimum over `order` periods.
        Bullish divergence if recent swing low price < past swing low price, BUT RSI is higher.

    :param df: DataFrame containing 'close' and 'rsi14' columns
    :param order: Number of bars on each side to define a local extremum
    :param lookback: Number of recent bars to evaluate
    :return: String - "bullish", "bearish", or "none"
    """
    closes = df["close"].tolist()
    rsis = df["rsi14"].tolist()
    n = len(closes)

    high_indices = []
    low_indices = []

    # Identify swing highs and swing lows
    for i in range(order, n - order):
        # Local peak (swing high)
        if all(closes[i] > closes[i - j] for j in range(1, order + 1)) and \
           all(closes[i] > closes[i + j] for j in range(1, order + 1)):
            high_indices.append(i)

        # Local trough (swing low)
        if all(closes[i] < closes[i - j] for j in range(1, order + 1)) and \
           all(closes[i] < closes[i + j] for j in range(1, order + 1)):
            low_indices.append(i)

    # Filter to recent window
    high_indices = [i for i in high_indices if i >= n - lookback]
    low_indices = [i for i in low_indices if i >= n - lookback]

    # Check for bearish divergence across the last two swing highs
    if len(high_indices) >= 2:
        h1, h2 = high_indices[-2], high_indices[-1]
        if closes[h2] > closes[h1] and rsis[h2] < rsis[h1]:
            return "bearish"

    # Check for bullish divergence across the last two swing lows
    if len(low_indices) >= 2:
        l1, l2 = low_indices[-2], low_indices[-1]
        if closes[l2] < closes[l1] and rsis[l2] > rsis[l1]:
            return "bullish"

    return "none"


def fetch_derivatives_microstructure(symbol):
    """
    Fetches futures Open Interest 24h % change and Taker Buy/Sell ratio from Binance Futures API.

    :param symbol: Binance symbol (e.g. BTCUSDT)
    :return: Tuple of (oi_change_24h, taker_ratio)
    """
    oi_change_24h = 0.0
    taker_ratio = 1.0
    try:
        # Fetch OI History
        r_oi = requests.get(f"https://fapi.binance.com/futures/data/openInterestHist?symbol={symbol}&period=1d&limit=2", timeout=5)
        if r_oi.status_code == 200:
            data_oi = r_oi.json()
            if len(data_oi) >= 2:
                prev_oi = float(data_oi[0].get("sumOpenInterestValue", 0))
                curr_oi = float(data_oi[1].get("sumOpenInterestValue", 0))
                if prev_oi > 0:
                    oi_change_24h = round(((curr_oi - prev_oi) / prev_oi) * 100, 2)
    except Exception:
        pass

    try:
        # Fetch Taker Buy/Sell Ratio
        r_tr = requests.get(f"https://fapi.binance.com/futures/data/takerlongshortRatio?symbol={symbol}&period=1d&limit=1", timeout=5)
        if r_tr.status_code == 200:
            data_tr = r_tr.json()
            if len(data_tr) > 0:
                taker_ratio = round(float(data_tr[0].get("buySellRatio", 1.0)), 4)
    except Exception:
        pass

    return oi_change_24h, taker_ratio


def compute_technical_indicators(name, symbol):
    """
    Computes all technical indicators for a single cryptocurrency asset.

    :param name: Human-readable asset name (e.g. "bitcoin")
    :param symbol: Binance symbol (e.g. "BTCUSDT")
    :return: Dictionary containing key indicator metrics and trend summary
    """
    df = fetch_binance_klines(symbol)

    # Moving Averages
    df["ema12"] = ta.trend.EMAIndicator(df["close"], window=12).ema_indicator()
    df["ema26"] = ta.trend.EMAIndicator(df["close"], window=26).ema_indicator()
    df["ema50"] = ta.trend.EMAIndicator(df["close"], window=50).ema_indicator()

    # Relative Strength Index
    df["rsi14"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi()

    # MACD
    macd = ta.trend.MACD(df["close"], window_slow=26, window_fast=12, window_sign=9)
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_hist"] = macd.macd_diff()

    # Momentum / Rate of Change (10)
    df["momentum_10"] = ta.momentum.ROCIndicator(df["close"], window=10).roc()

    # Volume Indicators
    df["vma20"] = ta.trend.SMAIndicator(df["volume"], window=20).sma_indicator()
    df["volume_ratio"] = df["volume"] / df["vma20"]

    # Bollinger Bands (%B) & Volatility (ATR)
    df["bollinger_pct_b"] = ta.volatility.BollingerBands(df["close"], window=20, window_dev=2).bollinger_pband()
    df["atr14"] = ta.volatility.AverageTrueRange(df["high"], df["low"], df["close"], window=14).average_true_range()

    # ADX & DMI
    adx_ind = ta.trend.ADXIndicator(df["high"], df["low"], df["close"], window=14)
    df["adx14"] = adx_ind.adx()

    # VWAP
    vwap_ind = ta.volume.VolumeWeightedAveragePrice(df["high"], df["low"], df["close"], df["volume"], window=14)
    df["vwap"] = vwap_ind.volume_weighted_average_price()

    # Divergence
    divergence = detect_rsi_divergence(df)

    last = df.iloc[-1]
    close_price = float(last["close"])
    ema50_val = float(last["ema50"])
    macd_val = float(last["macd"])
    macd_sig = float(last["macd_signal"])
    rsi_val = float(last["rsi14"])
    atr_val = float(last["atr14"])

    # Determine Trend Bias
    if close_price > ema50_val and macd_val > macd_sig and rsi_val > 50:
        trend_bias = "bullish"
    elif close_price < ema50_val and macd_val < macd_sig and rsi_val < 50:
        trend_bias = "bearish"
    else:
        trend_bias = "neutral"

    # Microstructure: OI Change & Taker Ratio
    oi_change_24h, taker_ratio = fetch_derivatives_microstructure(symbol)

    # Dynamic ATR Position Sizing ($100 risk target / (2 * ATR / Price))
    risk_target = 100.0
    risk_per_unit = 2.0 * atr_val if atr_val > 0 else (0.05 * close_price)
    units = risk_target / risk_per_unit if risk_per_unit > 0 else 0
    suggested_pos_size = min(1000.0, max(200.0, round(units * close_price, 2)))

    short_symbol = symbol.replace("USDT", "")

    return {
        "name": name,
        "symbol": short_symbol,
        "ticker": symbol,
        "price": round(close_price, 4),
        "rsi14": round(rsi_val, 2),
        "ema12": round(float(last["ema12"]), 4),
        "ema26": round(float(last["ema26"]), 4),
        "ema50": round(float(last["ema50"]), 4),
        "macd": round(macd_val, 4),
        "macd_signal": round(macd_sig, 4),
        "macd_hist": round(float(last["macd_hist"]), 4),
        "momentum_10": round(float(last["momentum_10"]), 2),
        "volume_ratio": round(float(last["volume_ratio"]), 2),
        "bollinger_pct_b": round(float(last["bollinger_pct_b"]), 4),
        "atr14": round(atr_val, 4),
        "adx14": round(float(last["adx14"]), 2),
        "vwap": round(float(last["vwap"]), 4),
        "oi_change_24h": oi_change_24h,
        "taker_ratio": taker_ratio,
        "suggested_pos_size": suggested_pos_size,
        "divergence": divergence,
        "trend_bias": trend_bias
    }


def fetch_global_market_context():
    """
    Fetches macro market sentiment metrics (Fear & Greed Index and BTC/ETH dominance).

    :return: Dictionary containing fear_and_greed index and market dominance figures
    """
    fng_data = {}
    cg_data = {}

    try:
        r = requests.get("https://api.alternative.me/fng/", timeout=10)
        fng_data = r.json().get("data", [{}])[0]
    except Exception as err:
        fng_data = {"error": str(err)}

    try:
        r = requests.get("https://api.coingecko.com/api/v3/global", timeout=10)
        cg_data = r.json().get("data", {})
    except Exception as err:
        cg_data = {"error": str(err)}

    return {
        "fear_and_greed": fng_data,
        "btc_dominance": cg_data.get("market_cap_percentage", {}).get("btc", None),
        "eth_dominance": cg_data.get("market_cap_percentage", {}).get("eth", None)
    }


def run_research(watchlist_path="state/watchlist.json"):
    """
    Main function to execute complete technical and macro research.

    :param watchlist_path: Path to state/watchlist.json
    :return: Dictionary containing market context and asset TA breakdowns
    """
    watchlist = load_watchlist(watchlist_path)
    ta_results = {}

    for name, ticker in watchlist.items():
        try:
            ta_results[ticker] = compute_technical_indicators(name, ticker)
        except Exception as e:
            ta_results[ticker] = {"symbol": ticker, "error": str(e)}

    market_ctx = fetch_global_market_context()

    return {
        "market_context": market_ctx,
        "technical_analysis": ta_results
    }


if __name__ == "__main__":
    results = run_research()
    print(json.dumps(results, indent=2))
