# 📈 ANTItrading — Automated Crypto Paper-Trading Agent

A daily paper-trading agent system engineered to perform automated market research, microstructure analysis, Shariah-compliant screening, and portfolio risk management across cryptocurrency markets.

---

## 🎯 Overview

**ANTItrading** is an agentic paper-trading system designed for daily execution. Operating under a strict long-only, zero-leverage paper trading framework ($10,000 initial capital), the agent integrates live market data from public exchange APIs and computes multi-timeframe technical indicators, futures order-flow dynamics, and macro sentiment metrics to make data-driven trade decisions.

> ⚠️ **DISCLAIMER:** This project is strictly for paper-trading simulation and educational research. No real monetary transactions or automated live exchange orders take place.

---

## ✨ Key Features & Capabilities

- **🕌 Shariah Compliance Screening:** Pre-screened 22-asset watchlist filtered against Islamic finance criteria (No Riba/lending yields, No excessive Gharar/speculative meme tokens, Halal utility).
- **📊 Live Multi-Timeframe Technical Analysis:** Real-time 1D & 4H kline processing computing EMA(12/26/50), RSI(14), MACD, 10-Day ROC, Volume MA(20), Volume Ratio, and Bollinger Bands (%B).
- **🔬 Microstructure & Order-Flow Metrics:**
  - **ADX(14):** Average Directional Index measuring trend strength (> 25 = strong trend).
  - **VWAP:** Volume Weighted Average Price for institutional fair-value pricing.
  - **Open Interest 24h % Change:** Real-time futures leverage buildup tracking.
  - **Taker Buy/Sell Ratio:** Taker order flow aggressive buyer/seller ratio.
- **🛡️ Dynamic Risk & Volatility Sizing:** ATR(14)-adjusted dynamic position allocation ($100 risk target per trade, capped at $1,000 max).
- **🤖 Master Execution Guide (`DAILY_TRADER.md`):** A standardized, 6-step prompt loop designed for seamless execution by LLM coding agents.
- **📄 Dual JSON & CSV State Logging:** Full state persistence including portfolio snapshots, audit-ready decision logs, and human-readable position views.

---

## 📁 Repository Structure

```
ANTItrading/
├── DAILY_TRADER.md               # Master execution workflow prompt for AI agents
├── README.md                     # Project documentation
├── watchlist.csv                 # Pre-screened Shariah-compliant watchlist table
├── scripts/
│   ├── README.md                 # Scripts documentation
│   ├── research.py               # Live TA, ADX, VWAP, & microstructure engine
│   ├── news_research.py          # News & macro sentiment aggregator
│   ├── shariah_research.py       # Shariah screening utility
│   └── execute_trade.py          # Portfolio state manager & CSV sync tool
└── state/
    ├── portfolio.json            # Active portfolio state (cash balance, open positions)
    ├── watchlist.json            # JSON map of active tracked tickers
    ├── trade_log.csv             # Append-only 30-column master trade decision log
    ├── human_open_positions.csv  # Human-readable view of open positions
    ├── human_decision_log.csv    # Human-readable view of decision history
    └── human_closed_trades.csv   # Human-readable view of completed trades
```

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.9+**
- Standard scientific Python libraries:
  ```bash
  pip install pandas requests ta
  ```

### Running Technical Research

To run live market research across the 22 Shariah-compliant assets:

```bash
python3 scripts/research.py
```

### Executing a Trade Pass

To execute a paper-trading pass using a structured decision payload:

```bash
python3 scripts/execute_trade.py --input-json /path/to/decisions.json
```

---

## 🤖 AI Agent Workflow

To trigger an automated daily paper-trading pass in an AI coding session, simply reference `@DAILY_TRADER.md`:

> *"Run today's daily paper-trading pass following @DAILY_TRADER.md"*

The agent will autonomously load the current portfolio, fetch market indicators, evaluate entry/exit triggers, execute state updates, and present a structured markdown summary.

---

## 📜 License

MIT License — see LICENSE for details.
