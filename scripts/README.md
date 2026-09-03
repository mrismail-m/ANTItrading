# Reusable Trading Agent Scripts

This directory contains persistent, well-documented Python modules created for the **Daily Crypto Paper-Trading Agent**.

---

## 1. `scripts/research.py`
- **Purpose:** Fetches Binance daily OHLCV candles (100 days) for all tracked assets in `state/watchlist.json` and computes technical indicators:
  - EMA (12, 26, 50)
  - RSI (14)
  - MACD (Line, Signal, Histogram)
  - Momentum / ROC (10)
  - Volume MA (20) & Volume Ratio
  - Bollinger Bands (%B)
  - Average True Range (ATR 14)
  - Swing Divergence (Bullish / Bearish / None)
  - Overall Trend Bias (Bullish / Bearish / Neutral)
- **Market Context:** Fetches Crypto Fear & Greed Index and BTC/ETH market dominance.
- **Execution Command:**
  ```bash
  python3 scripts/research.py
  ```

---

## 2. `scripts/news_research.py`
- **Purpose:** Queries CryptoPanic feed for tracked asset symbols (`BTC`, `ETH`, `SOL`, etc.) to retrieve recent headlines, domains, and sentiment. Flags when web search tool should be invoked.
- **Execution Command:**
  ```bash
  python3 scripts/news_research.py
  ```

---

## 3. `scripts/execute_trade.py`
- **Purpose:** Updates portfolio holdings (`state/portfolio.json`), appends decision logs (`state/trade_log.csv`), and synchronizes human-readable CSV views (`state/human_open_positions.csv`, `state/human_decision_log.csv`).
- **Execution Command:**
  ```bash
  python3 scripts/execute_trade.py --input-json state/latest_decisions.json
  ```

---

## 4. `scripts/run_trader.py`
- **Purpose:** Master unified runner for twice-daily autonomous paper trading. Integrates multi-timeframe research (1D & 4H), sentiment, risk filters, trade execution, and summary reporting into a single command without temporary or scratch files.
- **Execution Command:**
  ```bash
  python3 scripts/run_trader.py [--dry-run] [--silent]
  ```

---

## 5. `scripts/backtest.py`
- **Purpose:** Quantitative historical simulation engine. Tests strategy rules, dynamic ATR sizing, TP1 profit scaling (+10%), and RS ranking against historical Binance candles (90-365 days) and benchmarks against 50/50 BTC/ETH.
- **Execution Command:**
  ```bash
  python3 scripts/backtest.py [--days 180] [--output-json state/backtest_results.json]
  ```
