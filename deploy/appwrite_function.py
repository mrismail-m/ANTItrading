#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
ANTItrading Appwrite Cloud Function Handler
===============================================================================
Executes the hourly autonomous paper-trading pass on Appwrite Cloud Functions.
- Synchronizes persistent portfolio state with Appwrite Cloud Database.
- Runs technical analysis, risk checks, and BTC Macro Circuit Breaker.
- Updates state, logs executed trades to Appwrite Database, and dispatches Discord notifications.
- Fully self-contained inside Appwrite without relying on GitHub Actions or external git runners.
===============================================================================
"""

import os
import sys
import datetime
from typing import Any

# Ensure project root is on sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from scripts.appwrite_db import sync_portfolio_from_db, sync_portfolio_to_db
from scripts.run_trader import run_trader_pass


def main(context: Any) -> Any:
    """
    Appwrite Function Entrypoint.
    Receives Appwrite's context object (with context.req, context.res, context.log, context.error).
    """
    if hasattr(context, "log"):
        context.log("🚀 ANTItrading Appwrite Function Triggered.")
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    try:
        # 1. Sync persistent portfolio state from Appwrite Database
        if hasattr(context, "log"):
            context.log("📦 Syncing portfolio state from Appwrite Database...")
        db_portfolio = sync_portfolio_from_db()
        if db_portfolio and hasattr(context, "log"):
            cash = db_portfolio.get("cash", 0.0)
            positions = [p.get("symbol") for p in db_portfolio.get("positions", [])]
            context.log(f"✅ State loaded from Database | Cash: ${cash:,.2f} USD | Positions ({len(positions)}): {positions}")
        elif hasattr(context, "log"):
            context.log("ℹ️ No remote database state found; proceeding with bundled state.")

        # 2. Determine mode and execute live trading pass
        mode = "AUTO"
        if hasattr(context, "req") and context.req:
            try:
                body = getattr(context.req, "bodyJson", None) or getattr(context.req, "body", None)
                if isinstance(body, dict) and "mode" in body:
                    mode = str(body["mode"]).upper()
            except Exception:
                pass

        if hasattr(context, "log"):
            context.log(f"🧠 Executing autonomous trading pass (Requested Mode: {mode})...")
        result = run_trader_pass(mode=mode, dry_run=False, silent=True)
        actual_mode = result.get("mode", "UNKNOWN")
        executed_count = result.get("executed_count", 0)

        portfolio = result.get("portfolio", {})
        cash = portfolio.get("cash", 0.0)
        positions = portfolio.get("positions", [])
        history = portfolio.get("equity_history", [])
        curr_val = history[-1].get("portfolio_value", cash) if history else cash

        # 3. Ensure database is updated with final post-trade state
        if hasattr(context, "log"):
            context.log("💾 Persisting post-pass portfolio to Appwrite Database...")
        sync_portfolio_to_db(portfolio)

        msg = f"✅ [{actual_mode}] Pass completed! Equity: ${curr_val:,.2f} USD | Cash: ${cash:,.2f} USD | Open: {len(positions)} | Orders: {executed_count}"
        if hasattr(context, "log"):
            context.log(msg)

        if hasattr(context, "res") and hasattr(context.res, "json"):
            return context.res.json({
                "status": "success",
                "mode": actual_mode,
                "timestamp": now,
                "portfolio_value": curr_val,
                "cash_balance": cash,
                "open_positions": len(positions),
                "executed_orders": executed_count,
                "message": msg
            })
        return {"status": "success", "mode": actual_mode, "portfolio_value": curr_val}

    except Exception as err:
        err_msg = f"❌ Execution failed: {err}"
        if hasattr(context, "error"):
            context.error(err_msg)
        if hasattr(context, "res") and hasattr(context.res, "json"):
            return context.res.json({
                "status": "error",
                "timestamp": now,
                "error": str(err)
            }, 500)
        raise err
