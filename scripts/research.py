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
import time
import requests
import numpy as np
import pandas as pd
import ta
from concurrent.futures import ThreadPoolExecutor

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_WATCHLIST_PATH = os.path.join(ROOT_DIR, "state", "watchlist.json")
DEFAULT_RESEARCH_PATH = os.path.join(ROOT_DIR, "state", "latest_research.json")


def compute_choppiness_index(df, window=14):
    """
    Computes 14-period Choppiness Index (CHOP).
    CHOP < 38.2 = Strong directional trend
    CHOP > 61.8 = Choppy, sideways market
    """
    try:
        tr1 = pd.concat([
            df["high"] - df["low"],
            (df["high"] - df["close"].shift(1)).abs(),
            (df["low"] - df["close"].shift(1)).abs()
        ], axis=1).max(axis=1)
        sum_tr = tr1.rolling(window=window).sum()
        max_hi = df["high"].rolling(window=window).max()
        min_lo = df["low"].rolling(window=window).min()
        diff = (max_hi - min_lo).replace(0, 0.0001)
        chop = 100 * (np.log10(sum_tr / diff) / np.log10(window))
        return chop.fillna(50.0)
    except Exception:
        return pd.Series(50.0, index=df.index)


def load_watchlist(filepath=None):
    """
    Loads the asset watchlist from a JSON file.

    :param filepath: Path to watchlist.json file (defaults to state/watchlist.json)
    :return: Dictionary mapping asset names to Binance ticker symbols (e.g. {"bitcoin": "BTCUSDT"})
    """
    target_path = filepath or DEFAULT_WATCHLIST_PATH
    if not os.path.exists(target_path):
        print(f"Error: Watchlist file '{target_path}' not found.", file=sys.stderr)
        return {}
    with open(target_path, "r") as f:
        return json.load(f)


def is_fresh_candles(data):
    """Verifies that kline data is not from a dead or delisted market (within last 48 hours)."""
    if not data or not isinstance(data, list) or len(data) == 0:
        return False
    try:
        last_row = data[-1]
        close_time_ms = float(last_row[6] if len(last_row) > 6 else last_row[0])
        if close_time_ms < 1e11:
            close_time_ms *= 1000
        age_hours = (time.time() * 1000 - close_time_ms) / (1000 * 3600)
        return age_hours <= 48.0
    except Exception:
        return True


def fetch_binance_klines(symbol, interval="1d", limit=100):
    """
    Fetches OHLCV candles with multi-exchange global failover:
    1. Binance Spot API (verified fresh)
    2. Binance Futures API (verified fresh)
    3. MEXC Global Spot API (unrestricted globally / US cloud runners)
    4. Bybit Global Spot API

    :param symbol: Ticker symbol (e.g., BTCUSDT, HYPEUSDT)
    :param interval: Candle timeframe (default "1d")
    :param limit: Number of candles (default 100)
    :return: pandas.DataFrame containing open, high, low, close, volume as floats
    """
    raw_data = None

    # 1. Try Binance Spot API
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            cand = response.json()
            if is_fresh_candles(cand):
                raw_data = cand
    except Exception:
        pass

    # 2. Fall back to Binance Futures API
    if not raw_data:
        try:
            fapi_url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
            f_resp = requests.get(fapi_url, timeout=5)
            if f_resp.status_code == 200:
                cand = f_resp.json()
                if is_fresh_candles(cand):
                    raw_data = cand
        except Exception:
            pass

    # 3. Failover to MEXC Global API (identical schema, accessible from cloud runners)
    if not raw_data:
        try:
            mexc_url = f"https://api.mexc.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
            m_resp = requests.get(mexc_url, timeout=6)
            if m_resp.status_code == 200:
                cand = m_resp.json()
                if is_fresh_candles(cand):
                    raw_data = cand
        except Exception:
            pass

    # 4. Failover to Bybit Global API
    if not raw_data:
        try:
            bybit_int_map = {"1d": "D", "4h": "240", "1h": "60"}
            b_interval = bybit_int_map.get(interval, "D")
            bybit_url = f"https://api.bybit.com/v5/market/kline?category=spot&symbol={symbol}&interval={b_interval}&limit={limit}"
            b_resp = requests.get(bybit_url, timeout=6)
            if b_resp.status_code == 200:
                b_data = b_resp.json().get("result", {}).get("list", [])
                if b_data:
                    b_data = list(reversed(b_data))
                    cand = [
                        [int(row[0]), float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5])]
                        for row in b_data
                    ]
                    if is_fresh_candles(cand):
                        raw_data = cand
        except Exception:
            pass

    if not raw_data:
        raise RuntimeError(f"All global exchange sources (Binance, MEXC, Bybit) failed for {symbol}")

    df = pd.DataFrame(raw_data).iloc[:, :6]
    df.columns = ["open_time", "open", "high", "low", "close", "volume"]

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


def fetch_orderbook_imbalance(symbol):
    """
    Fetches Binance order book depth (100 levels) and calculates bid-ask volume imbalance ratio within +/- 2% of mid-price.
    Falls back to Futures depth API if Spot depth is unavailable.

    :param symbol: Binance symbol (e.g. BTCUSDT)
    :return: Float imbalance ratio between 0.0 and 1.0 (> 0.50 = bid dominance/support)
    """
    try:
        url = f"https://api.binance.com/api/v3/depth?symbol={symbol}&limit=100"
        res = requests.get(url, timeout=4)
        if res.status_code != 200:
            res = requests.get(f"https://fapi.binance.com/fapi/v1/depth?symbol={symbol}&limit=100", timeout=4)
        if res.status_code != 200:
            res = requests.get(f"https://api.mexc.com/api/v3/depth?symbol={symbol}&limit=100", timeout=4)

        if res.status_code == 200:
            data = res.json()
            bids = data.get("bids", [])
            asks = data.get("asks", [])
            if bids and asks:
                best_bid = float(bids[0][0])
                best_ask = float(asks[0][0])
                mid_price = (best_bid + best_ask) / 2.0

                lower_bound = mid_price * 0.98
                upper_bound = mid_price * 1.02

                bid_vol = sum(float(b[1]) * float(b[0]) for b in bids if float(b[0]) >= lower_bound)
                ask_vol = sum(float(a[1]) * float(a[0]) for a in asks if float(a[0]) <= upper_bound)

                total_vol = bid_vol + ask_vol
                if total_vol > 0:
                    return round(bid_vol / total_vol, 4)
    except Exception:
        pass
    return 0.50


def classify_market_regime(btc_price, btc_ema50, btc_adx14, fear_greed_val):
    """
    Classifies macro market regime into one of 4 states:
    - 'bullish_trend': BTC > EMA50, ADX > 25, Fear&Greed > 50
    - 'volatility_crash': BTC < EMA50, Fear&Greed < 30
    - 'ranging': ADX < 20
    - 'neutral': default state
    """
    fg = fear_greed_val if isinstance(fear_greed_val, (int, float)) else 50

    if btc_price > 0 and btc_ema50 > 0:
        if btc_price < btc_ema50 and fg < 30:
            return "volatility_crash"
        elif btc_price > btc_ema50 and btc_adx14 > 25 and fg > 50:
            return "bullish_trend"
        elif btc_adx14 < 20:
            return "ranging"

    return "neutral"


def fetch_derivatives_microstructure(symbol):
    """
    Fetches futures Open Interest 24h % change, Taker Buy/Sell ratio, and Funding Rate from Binance Futures API.

    :param symbol: Binance symbol (e.g. BTCUSDT)
    :return: Tuple of (oi_change_24h, taker_ratio, funding_rate, funding_alert)
    """
    oi_change_24h = 0.0
    taker_ratio = 1.0
    funding_rate = 0.0001
    funding_alert = "NEUTRAL_FUNDING"

    try:
        # Fetch OI History
        r_oi = requests.get(f"https://fapi.binance.com/futures/data/openInterestHist?symbol={symbol}&period=1d&limit=2", timeout=4)
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
        r_tr = requests.get(f"https://fapi.binance.com/futures/data/takerlongshortRatio?symbol={symbol}&period=1d&limit=1", timeout=4)
        if r_tr.status_code == 200:
            data_tr = r_tr.json()
            if len(data_tr) > 0:
                taker_ratio = round(float(data_tr[0].get("buySellRatio", 1.0)), 4)
    except Exception:
        pass

    try:
        # Fetch Current Funding Rate
        r_fr = requests.get(f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={symbol}", timeout=4)
        if r_fr.status_code == 200:
            funding_rate = round(float(r_fr.json().get("lastFundingRate", 0.0001)), 6)
        else:
            # Fallback to Bybit linear funding rate
            r_bybit = requests.get(f"https://api.bybit.com/v5/market/funding/history?category=linear&symbol={symbol}&limit=1", timeout=4)
            if r_bybit.status_code == 200:
                f_list = r_bybit.json().get("result", {}).get("list", [])
                if f_list:
                    funding_rate = round(float(f_list[0].get("fundingRate", 0.0001)), 6)
    except Exception:
        pass

    if funding_rate <= -0.0001 and oi_change_24h > 2.0:
        funding_alert = "SHORT_SQUEEZE_ALERT"
    elif funding_rate >= 0.0003:
        funding_alert = "LONG_FLUSH_ALERT"

    return oi_change_24h, taker_ratio, funding_rate, funding_alert


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

    # Momentum / Rate of Change
    df["momentum_10"] = ta.momentum.ROCIndicator(df["close"], window=10).roc()

    # 7-day and 14-day ROC for Relative Strength vs BTC
    closes = df["close"].tolist()
    roc_7 = round(((closes[-1] - closes[-8]) / closes[-8]) * 100, 2) if len(closes) >= 8 else 0.0
    roc_14 = round(((closes[-1] - closes[-15]) / closes[-15]) * 100, 2) if len(closes) >= 15 else 0.0

    # Volume Indicators
    df["vma20"] = ta.trend.SMAIndicator(df["volume"], window=20).sma_indicator()
    df["volume_ratio"] = df["volume"] / df["vma20"]

    # Bollinger Bands (%B) & Volatility (ATR)
    bb = ta.volatility.BollingerBands(df["close"], window=20, window_dev=2)
    df["bollinger_pct_b"] = bb.bollinger_pband()
    df["atr14"] = ta.volatility.AverageTrueRange(df["high"], df["low"], df["close"], window=14).average_true_range()

    # TTM Volatility Squeeze (Bollinger Bands coiling inside Keltner Channels)
    bb_upper = bb.bollinger_hband()
    bb_lower = bb.bollinger_lband()
    kc = ta.volatility.KeltnerChannel(df["high"], df["low"], df["close"], window=20, window_atr=10, multiplier=1.5)
    kc_upper = kc.keltner_channel_hband()
    kc_lower = kc.keltner_channel_lband()
    df["squeeze_on"] = (bb_upper <= kc_upper) & (bb_lower >= kc_lower)
    df["squeeze_fired"] = (df["squeeze_on"].shift(1) == True) & (df["squeeze_on"] == False)

    # Chaikin Money Flow (CMF 20) & Money Flow Index (MFI 14)
    df["cmf20"] = ta.volume.ChaikinMoneyFlowIndicator(df["high"], df["low"], df["close"], df["volume"], window=20).chaikin_money_flow()
    df["mfi14"] = ta.volume.MFIIndicator(df["high"], df["low"], df["close"], df["volume"], window=14).money_flow_index()

    # ADX & DMI Directional System (+DI and -DI)
    adx_ind = ta.trend.ADXIndicator(df["high"], df["low"], df["close"], window=14)
    df["adx14"] = adx_ind.adx()
    df["di_plus"] = adx_ind.adx_pos()
    df["di_minus"] = adx_ind.adx_neg()

    # Choppiness Index (CHOP 14)
    df["chop14"] = compute_choppiness_index(df, window=14)

    # Chandelier Trailing Exit (22-period Highest High - 2.5 * ATR14)
    highest_high_22 = df["high"].rolling(window=22).max()
    df["chandelier_stop"] = highest_high_22 - (2.5 * df["atr14"])

    # VWAP
    vwap_ind = ta.volume.VolumeWeightedAveragePrice(df["high"], df["low"], df["close"], df["volume"], window=14)
    df["vwap"] = vwap_ind.volume_weighted_average_price()

    # 20-day Price Channel (Donchian High & Low)
    df["donchian_high_20"] = df["high"].rolling(window=20).max()
    df["donchian_low_20"] = df["low"].rolling(window=20).min()

    # Divergence
    divergence = detect_rsi_divergence(df)

    last = df.iloc[-1]
    close_price = float(last["close"])
    ema50_val = float(last["ema50"])
    macd_val = float(last["macd"])
    macd_sig = float(last["macd_signal"])
    rsi_val = float(last["rsi14"])
    atr_val = float(last["atr14"])

    # Detect Volume Expansion & 20-Day Range Breakout
    vol_ratio = float(last["volume_ratio"]) if pd.notna(last["volume_ratio"]) else 1.0
    donchian_h20 = float(last["donchian_high_20"]) if pd.notna(last["donchian_high_20"]) else close_price
    donchian_l20 = float(last["donchian_low_20"]) if pd.notna(last["donchian_low_20"]) else close_price
    volume_breakout = bool((vol_ratio >= 1.8) and (close_price >= donchian_h20 * 0.99))

    # Determine Trend Bias (1D) with EMA stack confirmation
    ema12_val = float(last["ema12"])
    ema26_val = float(last["ema26"])
    if close_price > ema50_val and rsi_val > 50 and (macd_val > macd_sig or (ema12_val > ema26_val > ema50_val and rsi_val > 52)):
        trend_bias = "bullish"
    elif close_price < ema50_val and rsi_val < 50 and (macd_val < macd_sig or (ema12_val < ema26_val < ema50_val and rsi_val < 48)):
        trend_bias = "bearish"
    else:
        trend_bias = "neutral"

    # 4H Multi-Timeframe Research
    trend_bias_4h = "neutral"
    rsi_4h = 50.0
    try:
        df_4h = fetch_binance_klines(symbol, interval="4h", limit=50)
        df_4h["ema12"] = ta.trend.EMAIndicator(df_4h["close"], window=12).ema_indicator()
        df_4h["ema26"] = ta.trend.EMAIndicator(df_4h["close"], window=26).ema_indicator()
        df_4h["ema50"] = ta.trend.EMAIndicator(df_4h["close"], window=50).ema_indicator()
        df_4h["rsi14"] = ta.momentum.RSIIndicator(df_4h["close"], window=14).rsi()
        macd_4h = ta.trend.MACD(df_4h["close"], window_slow=26, window_fast=12, window_sign=9)
        df_4h["macd"] = macd_4h.macd()
        df_4h["macd_signal"] = macd_4h.macd_signal()

        last_4h = df_4h.iloc[-1]
        c_4h = float(last_4h["close"])
        ema12_4h = float(last_4h["ema12"])
        ema26_4h = float(last_4h["ema26"])
        ema50_4h = float(last_4h["ema50"])
        macd_val_4h = float(last_4h["macd"])
        macd_sig_4h = float(last_4h["macd_signal"])
        rsi_4h = round(float(last_4h["rsi14"]), 2)

        if c_4h > ema50_4h and rsi_4h > 50 and (macd_val_4h > macd_sig_4h or (ema12_4h > ema26_4h and c_4h > ema50_4h * 1.005)):
            trend_bias_4h = "bullish"
        elif c_4h < ema50_4h and rsi_4h < 50 and (macd_val_4h < macd_sig_4h or (ema12_4h < ema26_4h and c_4h < ema50_4h * 0.995)):
            trend_bias_4h = "bearish"
        else:
            trend_bias_4h = "neutral"
    except Exception:
        pass

    trend_alignment = "aligned" if trend_bias == trend_bias_4h else "diverging"

    # 1H Intraday Precision Timing Indicators
    rsi_1h = 50.0
    ema20_1h = close_price
    price_vs_ema20_1h = 0.0
    try:
        df_1h = fetch_binance_klines(symbol, interval="1h", limit=30)
        df_1h["ema20"] = ta.trend.EMAIndicator(df_1h["close"], window=20).ema_indicator()
        df_1h["rsi14"] = ta.momentum.RSIIndicator(df_1h["close"], window=14).rsi()
        last_1h = df_1h.iloc[-1]
        rsi_1h = round(float(last_1h["rsi14"]), 2)
        ema20_1h = round(float(last_1h["ema20"]), 4)
        if ema20_1h > 0:
            price_vs_ema20_1h = round(((close_price - ema20_1h) / ema20_1h) * 100, 2)
    except Exception:
        pass

    # Microstructure: OI Change, Taker Ratio, Funding Rate, Orderbook Imbalance
    oi_change_24h, taker_ratio, funding_rate, funding_alert = fetch_derivatives_microstructure(symbol)
    ob_imbalance_2pct = fetch_orderbook_imbalance(symbol)

    # Classify Intraday Whale Activity (requiring confluence to avoid single-tick top-100 book noise)
    if taker_ratio >= 1.10 and oi_change_24h > 3.0 and ob_imbalance_2pct >= 0.52:
        whale_alert = "WHALE_ACCUMULATION"
    elif taker_ratio <= 0.90 and oi_change_24h > 3.0 and ob_imbalance_2pct <= 0.48:
        whale_alert = "WHALE_DISTRIBUTION"
    elif taker_ratio >= 1.15 and ob_imbalance_2pct >= 0.60:
        whale_alert = "BULLISH_WHALE_WALL"
    elif taker_ratio <= 0.85 and ob_imbalance_2pct <= 0.38:
        whale_alert = "BEARISH_WHALE_WALL"
    else:
        whale_alert = "NEUTRAL_FLOW"

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
        "rsi_4h": rsi_4h,
        "rsi_1h": rsi_1h,
        "ema20_1h": ema20_1h,
        "price_vs_ema20_1h": price_vs_ema20_1h,
        "roc_7": roc_7,
        "roc_14": roc_14,
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
        "funding_rate": funding_rate,
        "funding_alert": funding_alert,
        "ob_imbalance_2pct": ob_imbalance_2pct,
        "whale_alert": whale_alert,
        "suggested_pos_size": suggested_pos_size,
        "donchian_high_20": round(donchian_h20, 4),
        "donchian_low_20": round(donchian_l20, 4),
        "volume_breakout": volume_breakout,
        "squeeze_on": bool(last["squeeze_on"]) if pd.notna(last["squeeze_on"]) else False,
        "squeeze_fired": bool(last["squeeze_fired"]) if pd.notna(last["squeeze_fired"]) else False,
        "cmf20": round(float(last["cmf20"]), 4) if pd.notna(last["cmf20"]) else 0.0,
        "mfi14": round(float(last["mfi14"]), 2) if pd.notna(last["mfi14"]) else 50.0,
        "di_plus": round(float(last["di_plus"]), 2) if pd.notna(last["di_plus"]) else 20.0,
        "di_minus": round(float(last["di_minus"]), 2) if pd.notna(last["di_minus"]) else 20.0,
        "chop14": round(float(last["chop14"]), 2) if pd.notna(last["chop14"]) else 50.0,
        "chandelier_stop": round(float(last["chandelier_stop"]), 4) if pd.notna(last["chandelier_stop"]) else round(close_price * 0.93, 4),
        "divergence": divergence,
        "trend_bias": trend_bias,
        "trend_bias_1d": trend_bias,
        "trend_bias_4h": trend_bias_4h,
        "trend_alignment": trend_alignment
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


def run_research(watchlist_path=None, output_path=None):
    """
    Main function to execute complete technical and macro research.
    Calculates Relative Strength vs BTC and ranks all assets by RS leadership score.

    :param watchlist_path: Path to state/watchlist.json
    :param output_path: Path to save persistent state/latest_research.json
    :return: Dictionary containing market context and asset TA breakdowns
    """
    target_watchlist = watchlist_path or DEFAULT_WATCHLIST_PATH
    target_output = output_path or DEFAULT_RESEARCH_PATH
    watchlist = load_watchlist(target_watchlist)
    ta_results = {}

    for name, ticker in watchlist.items():
        try:
            ta_results[ticker] = compute_technical_indicators(name, ticker)
        except Exception as e:
            ta_results[ticker] = {"symbol": ticker, "error": str(e)}

    # Compute Relative Strength (RS) vs. BTC
    btc_ta = ta_results.get("BTCUSDT", {})
    btc_roc7 = btc_ta.get("roc_7", 0.0)
    btc_roc14 = btc_ta.get("roc_14", 0.0)

    rs_ranked = []
    for ticker, data in ta_results.items():
        if "error" not in data:
            roc7 = data.get("roc_7", 0.0)
            roc14 = data.get("roc_14", 0.0)
            rs7 = round(roc7 - btc_roc7, 2)
            rs14 = round(roc14 - btc_roc14, 2)
            rs_score = round(0.6 * rs7 + 0.4 * rs14, 2)
            data["rs_7"] = rs7
            data["rs_14"] = rs14
            data["rs_score"] = rs_score
            rs_ranked.append((ticker, rs_score))

    # Rank by RS leadership
    rs_ranked.sort(key=lambda x: x[1], reverse=True)
    for rank, (ticker, _) in enumerate(rs_ranked, start=1):
        if ticker in ta_results:
            ta_results[ticker]["rs_rank"] = rank

    market_ctx = fetch_global_market_context()

    # Determine Market Regime & BTC Macro Flush Circuit Breaker
    btc = ta_results.get("BTCUSDT", {})
    btc_p = btc.get("price", 0)
    btc_ema50 = btc.get("ema50", 0)
    btc_adx = btc.get("adx14", 0)
    btc_trend_4h = btc.get("trend_bias_4h", "neutral")
    btc_trend_1d = btc.get("trend_bias_1d", "neutral")
    btc_rsi_1h = btc.get("rsi_1h", 50.0)
    btc_vs_ema20_1h = btc.get("price_vs_ema20_1h", 0.0)

    fg_val = market_ctx.get("fear_and_greed", {}).get("value", 50)
    try:
        fg_val = int(fg_val)
    except Exception:
        fg_val = 50

    regime = classify_market_regime(btc_p, btc_ema50, btc_adx, fg_val)
    market_ctx["market_regime"] = regime

    # BTC Macro Flush Detection
    btc_flush_alert = False
    macro_flush_reason = "BTC technical structure healthy"

    if btc_trend_1d == "bearish":
        btc_flush_alert = True
        macro_flush_reason = f"BTC 1D Trend Bias is Bearish (Price ${btc_p:,.0f} below 1D EMA50 ${btc_ema50:,.0f})"
    elif btc_trend_4h == "bearish":
        btc_flush_alert = True
        macro_flush_reason = "BTC 4H Trend Bias is Bearish (Breakdown below 4H EMA50 / Bearish 4H MACD)"
    elif btc_vs_ema20_1h <= -0.8 and btc_rsi_1h < 45.0:
        btc_flush_alert = True
        macro_flush_reason = f"BTC Fast Intraday Flush: Price stretched {btc_vs_ema20_1h:.2f}% below 1H EMA20 with RSI1H at {btc_rsi_1h:.1f}"

    market_ctx["btc_flush_alert"] = btc_flush_alert
    market_ctx["macro_flush_reason"] = macro_flush_reason

    results = {
        "market_context": market_ctx,
        "technical_analysis": ta_results
    }

    if target_output:
        os.makedirs(os.path.dirname(target_output), exist_ok=True)
        with open(target_output, "w") as f:
            json.dump(results, f, indent=2)

    return results


def run_fast_risk_research(open_symbols=None, output_path=None):
    """
    Fast Risk Guardian research scan.
    Runs every 5 minutes in ~2-4 seconds.
    Fetches technical data concurrently ONLY for BTCUSDT (for the Macro Flush Circuit Breaker)
    and open position symbols (to calculate current price, ATR14, and trailing profit-locks).

    :param open_symbols: List of active open symbols (e.g. ['LTC', 'SUI', 'AVAX'])
    :param output_path: Path to save persistent state/latest_research.json
    :return: Dictionary containing market context and targeted asset TA breakdowns
    """
    target_output = output_path or DEFAULT_RESEARCH_PATH
    open_symbols = open_symbols or []

    # Target tickers: always BTCUSDT + open positions
    target_tickers = ["BTCUSDT"]
    for s in open_symbols:
        t = s if s.endswith("USDT") else f"{s}USDT"
        if t not in target_tickers:
            target_tickers.append(t)

    ta_results = {}
    with ThreadPoolExecutor(max_workers=min(len(target_tickers), 6)) as executor:
        futures = {
            executor.submit(compute_technical_indicators, ticker.replace("USDT", ""), ticker): ticker
            for ticker in target_tickers
        }
        for future in futures:
            ticker = futures[future]
            try:
                ta_results[ticker] = future.result()
            except Exception as e:
                ta_results[ticker] = {"symbol": ticker, "error": str(e)}

    # Reuse cached market context if available to skip slow external APIs
    market_ctx = {}
    if os.path.exists(target_output):
        try:
            with open(target_output, "r") as f:
                cached = json.load(f)
                market_ctx = cached.get("market_context", {})
        except Exception:
            pass

    # Update BTC Macro Flush Detection with live BTC data
    btc = ta_results.get("BTCUSDT", {})
    btc_p = btc.get("price", 0)
    btc_ema50 = btc.get("ema50", 0)
    btc_adx = btc.get("adx14", 0)
    btc_trend_4h = btc.get("trend_bias_4h", "neutral")
    btc_trend_1d = btc.get("trend_bias_1d", "neutral")
    btc_rsi_1h = btc.get("rsi_1h", 50.0)
    btc_vs_ema20_1h = btc.get("price_vs_ema20_1h", 0.0)

    fg_val = market_ctx.get("fear_and_greed", {}).get("value", 50)
    try:
        fg_val = int(fg_val)
    except Exception:
        fg_val = 50

    regime = classify_market_regime(btc_p, btc_ema50, btc_adx, fg_val)
    market_ctx["market_regime"] = regime

    btc_flush_alert = False
    macro_flush_reason = "BTC technical structure healthy"

    if btc_trend_1d == "bearish":
        btc_flush_alert = True
        macro_flush_reason = f"BTC 1D Trend Bias is Bearish (Price ${btc_p:,.0f} below 1D EMA50 ${btc_ema50:,.0f})"
    elif btc_trend_4h == "bearish":
        btc_flush_alert = True
        macro_flush_reason = "BTC 4H Trend Bias is Bearish (Breakdown below 4H EMA50 / Bearish 4H MACD)"
    elif btc_vs_ema20_1h <= -0.8 and btc_rsi_1h < 45.0:
        btc_flush_alert = True
        macro_flush_reason = f"BTC Fast Intraday Flush: Price stretched {btc_vs_ema20_1h:.2f}% below 1H EMA20 with RSI1H at {btc_rsi_1h:.1f}"

    market_ctx["btc_flush_alert"] = btc_flush_alert
    market_ctx["macro_flush_reason"] = macro_flush_reason

    results = {
        "market_context": market_ctx,
        "technical_analysis": ta_results
    }

    if target_output:
        os.makedirs(os.path.dirname(target_output), exist_ok=True)
        # Merge with existing TA data if present so full universe cache is preserved
        if os.path.exists(target_output):
            try:
                with open(target_output, "r") as f:
                    cached_data = json.load(f)
                    merged_ta = cached_data.get("technical_analysis", {})
                    merged_ta.update(ta_results)
                    results["technical_analysis"] = merged_ta
            except Exception:
                pass
        with open(target_output, "w") as f:
            json.dump(results, f, indent=2)

    return results


if __name__ == "__main__":
    results = run_research()
    print(json.dumps(results, indent=2))
