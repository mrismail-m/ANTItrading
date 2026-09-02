"""
===============================================================================
Module: scripts/server.py
Purpose: FastAPI Backend Server for ANTItrading UI Dashboard
Author: Daily Crypto Paper-Trading Agent (Antigravity)

Description:
  Provides REST API endpoints for the ANTItrading web UI dashboard:
    - GET /api/portfolio: Portfolio equity, cash, positions, metrics
    - GET /api/open-positions: Active position details & live market values
    - GET /api/decision-log: Decision history log
    - GET /api/market-research: Technical analysis & market regime breakdown
    - GET /api/klines: Historical Binance OHLCV candles for TradingView chart
    - POST /api/run-agent: Triggers live daily paper-trading pass

Usage:
  python3 scripts/server.py [--port 5000]
===============================================================================
"""

import os
import sys
import json
import csv
import subprocess
import requests
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Ensure ANTItrading root directory is in sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from scripts.research import run_research, fetch_binance_klines
from scripts.execute_trade import load_portfolio

app = FastAPI(
    title="ANTItrading API",
    description="Backend API server for Daily Crypto Paper-Trading Agent",
    version="1.0.0"
)

# Enable CORS for local Vite dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/portfolio")
def get_portfolio():
    """Returns current portfolio state, cash, active positions, and metrics."""
    portfolio_path = os.path.join(ROOT_DIR, "state", "portfolio.json")
    if not os.path.exists(portfolio_path):
        raise HTTPException(status_code=444, detail="Portfolio state file not found.")
    
    with open(portfolio_path, "r") as f:
        data = json.load(f)
    return data


@app.get("/api/open-positions")
def get_open_positions():
    """Returns active open positions with live prices and calculated P&L."""
    portfolio_path = os.path.join(ROOT_DIR, "state", "portfolio.json")
    if not os.path.exists(portfolio_path):
        return []
    
    with open(portfolio_path, "r") as f:
        portfolio = json.load(f)
    
    positions = portfolio.get("positions", [])
    if not positions:
        return []
    
    # Fetch live price map from Binance for open positions
    result_positions = []
    for pos in positions:
        sym = pos.get("symbol")
        ticker = f"{sym}USDT"
        curr_price = pos.get("entry_price", 0.0)
        
        try:
            r = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={ticker}", timeout=3)
            if r.status_code == 200:
                curr_price = float(r.json().get("price", curr_price))
        except Exception:
            pass
        
        qty = float(pos.get("qty", 0.0))
        entry_price = float(pos.get("entry_price", 0.0))
        cost_basis = float(pos.get("cost_basis", 0.0))
        current_val = round(qty * curr_price, 2)
        pnl_usd = round(current_val - cost_basis, 2)
        pnl_pct = round(((curr_price - entry_price) / entry_price) * 100, 2) if entry_price > 0 else 0.0
        
        result_positions.append({
            "symbol": sym,
            "qty": qty,
            "entry_price": entry_price,
            "current_price": curr_price,
            "cost_basis": cost_basis,
            "current_value": current_val,
            "pnl_usd": pnl_usd,
            "pnl_pct": pnl_pct,
            "highest_price": pos.get("highest_price", entry_price),
            "trailing_stop_price": pos.get("trailing_stop_price", round(entry_price * 0.93, 4)),
            "opened_at": pos.get("opened_at")
        })
        
    return result_positions


@app.get("/api/decision-log")
def get_decision_log(limit: int = 50):
    """Returns recent human-readable decision logs."""
    log_path = os.path.join(ROOT_DIR, "state", "human_decision_log.csv")
    if not os.path.exists(log_path):
        return []
    
    decisions = []
    with open(log_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            decisions.append(row)
    
    # Reverse to show newest decisions first
    return decisions[::-1][:limit]


@app.get("/api/market-research")
def get_market_research():
    """Runs live market research and returns TA indicators + Market Regime context."""
    try:
        data = run_research()
        return data
    except Exception as err:
        raise HTTPException(status_code=500, detail=str(err))


@app.get("/api/klines")
def get_klines(symbol: str = "SOLUSDT", interval: str = "1d", limit: int = 100):
    """Fetches Binance OHLCV candlestick data formatted for TradingView lightweight-charts."""
    try:
        df = fetch_binance_klines(symbol, interval=interval, limit=limit)
        candles = []
        for idx, row in df.iterrows():
            # lightweight-charts expects unix timestamp in seconds or YYYY-MM-DD
            time_sec = int(row["open_time"]) // 1000
            candles.append({
                "time": time_sec,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"])
            })
        return candles
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Failed to fetch klines for {symbol}: {str(err)}")


@app.post("/api/run-agent")
def run_agent_pass():
    """Executes the daily paper-trading pass script and returns updated state."""
    scratch_script = os.path.join(ROOT_DIR, "..", ".gemini", "antigravity", "brain", "1b11d2f8-88dc-4967-90cd-6b803f9c79ca", "scratch", "run_daily_trade.py")
    if not os.path.exists(scratch_script):
        # Fallback to python execution inline
        from scripts.execute_trade import execute_trade_pass
        res = run_research()
        # run trade pass
        payload = {"timestamp": "", "decisions": []}
    
    try:
        proc = subprocess.run([sys.executable, scratch_script], capture_output=True, text=True, timeout=60)
        if proc.returncode == 0:
            portfolio = load_portfolio()
            return {"status": "success", "message": "Agent paper-trading pass completed.", "portfolio": portfolio, "output": proc.stdout}
        else:
            raise HTTPException(status_code=500, detail=f"Agent execution failed: {proc.stderr}")
    except Exception as err:
        raise HTTPException(status_code=500, detail=str(err))


if __name__ == "__main__":
    print("🚀 Starting ANTItrading FastAPI server on http://localhost:5000")
    uvicorn.run(app, host="0.0.0.0", port=5000)
