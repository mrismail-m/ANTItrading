#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
Module: scripts/appwrite_db.py
Purpose: Appwrite Cloud Database State Synchronization
Author: Daily Crypto Paper-Trading Agent (Antigravity)

Description:
  Provides persistent state synchronization between local file storage
  (state/portfolio.json) and Appwrite Cloud Databases (antitrader / portfolio).
  
  Ensures that serverless cloud function executions and local developer runs
  always read and write the exact same portfolio state, positions, cash balance,
  and trade history.
===============================================================================
"""

import os
import sys
import json
import datetime
import requests
from typing import Dict, Any, Optional

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PORTFOLIO_PATH = os.path.join(ROOT_DIR, "state", "portfolio.json")

# Appwrite Database Configuration
APPWRITE_ENDPOINT = os.environ.get("APPWRITE_ENDPOINT", "https://nyc.cloud.appwrite.io/v1")
APPWRITE_PROJECT_ID = os.environ.get("APPWRITE_PROJECT_ID", "6a9af04c003d0566314d")
APPWRITE_DATABASE_ID = os.environ.get("APPWRITE_DATABASE_ID", "antitrader")
APPWRITE_PORTFOLIO_COLLECTION = "portfolio"
APPWRITE_PORTFOLIO_DOC_ID = "current_portfolio"
APPWRITE_TRADES_COLLECTION = "trades"


def _get_headers() -> Dict[str, str]:
    """Builds standard HTTP headers for Appwrite REST API."""
    headers = {
        "X-Appwrite-Project": APPWRITE_PROJECT_ID,
        "Content-Type": "application/json"
    }
    api_key = os.environ.get("APPWRITE_FUNCTION_API_KEY") or os.environ.get("APPWRITE_API_KEY")
    if api_key:
        headers["X-Appwrite-Key"] = api_key
    return headers


def sync_portfolio_from_db(local_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Fetches the current portfolio state document from Appwrite Database.
    If successful, updates the local state/portfolio.json file and returns the state dict.
    Returns None if fetching fails.
    """
    target_path = local_path or DEFAULT_PORTFOLIO_PATH
    url = f"{APPWRITE_ENDPOINT}/databases/{APPWRITE_DATABASE_ID}/collections/{APPWRITE_PORTFOLIO_COLLECTION}/documents/{APPWRITE_PORTFOLIO_DOC_ID}"

    try:
        resp = requests.get(url, headers=_get_headers(), timeout=10)
        if resp.status_code == 200:
            doc = resp.json()
            raw_data = doc.get("data")
            if raw_data:
                portfolio = json.loads(raw_data)
                # Cache/sync to local disk
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                with open(target_path, "w") as f:
                    json.dump(portfolio, f, indent=2)
                return portfolio
    except Exception as err:
        sys.stderr.write(f"[Appwrite DB] Sync from DB warning: {err}\n")

    return None


def sync_portfolio_to_db(portfolio: Dict[str, Any], local_path: Optional[str] = None) -> bool:
    """
    Persists the updated portfolio dictionary both to local file storage and Appwrite Database.
    Updates document 'current_portfolio' in collection 'portfolio'.
    """
    target_path = local_path or DEFAULT_PORTFOLIO_PATH

    # 1. Save to local disk
    try:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(target_path, "w") as f:
            json.dump(portfolio, f, indent=2)
    except Exception as err:
        sys.stderr.write(f"[Appwrite DB] Local save error: {err}\n")

    # 2. Persist to Appwrite Database
    url = f"{APPWRITE_ENDPOINT}/databases/{APPWRITE_DATABASE_ID}/collections/{APPWRITE_PORTFOLIO_COLLECTION}/documents/{APPWRITE_PORTFOLIO_DOC_ID}"
    cash = float(portfolio.get("cash", 10000.0))
    history = portfolio.get("equity_history", [])
    p_val = float(history[-1].get("portfolio_value", cash) if history else cash)
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    payload = {
        "data": {
            "cash": cash,
            "portfolio_value": p_val,
            "updated_at": now_iso,
            "data": json.dumps(portfolio)
        }
    }

    try:
        resp = requests.patch(url, json=payload, headers=_get_headers(), timeout=10)
        if resp.status_code in (200, 201):
            return True
        sys.stderr.write(f"[Appwrite DB] PATCH failed with status {resp.status_code}: {resp.text}\n")
    except Exception as err:
        sys.stderr.write(f"[Appwrite DB] Sync to DB warning: {err}\n")

    return False


def record_trade_to_db(trade: Dict[str, Any]) -> bool:
    """
    Appends a new executed trade record to the Appwrite Database 'trades' collection.
    """
    url = f"{APPWRITE_ENDPOINT}/databases/{APPWRITE_DATABASE_ID}/collections/{APPWRITE_TRADES_COLLECTION}/documents"
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    payload = {
        "documentId": "unique()",
        "data": {
            "symbol": str(trade.get("symbol", "")),
            "action": str(trade.get("action", "")),
            "price": float(trade.get("fill_price", trade.get("price", 0.0))),
            "qty": float(trade.get("qty", 0.0)),
            "cost_basis": float(trade.get("cost_basis", 0.0)) if trade.get("cost_basis") is not None else 0.0,
            "pnl_pct": float(trade.get("pnl_pct", 0.0)) if trade.get("pnl_pct") is not None else 0.0,
            "reasoning": str(trade.get("reasoning", ""))[:2000],
            "timestamp": str(trade.get("timestamp", now_iso))
        }
    }

    try:
        resp = requests.post(url, json=payload, headers=_get_headers(), timeout=10)
        return resp.status_code in (200, 201)
    except Exception as err:
        sys.stderr.write(f"[Appwrite DB] Record trade warning: {err}\n")
        return False
