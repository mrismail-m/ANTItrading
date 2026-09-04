#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
ANTItrading Appwrite Cloud Function Handler
===============================================================================
Executes the hourly autonomous paper-trading pass on Appwrite Cloud Functions.
- Pulls persistent state from GitHub using GITHUB_TOKEN.
- Runs technical analysis, risk checks, and BTC Macro Circuit Breaker.
- Updates state and dispatches Discord notifications.
- Commits and pushes state back to GitHub to survive serverless container lifecycles.
===============================================================================
"""

import os
import sys
import subprocess
import datetime
from typing import Any

# Ensure project root is on sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from scripts.run_trader import run_trader_pass


def sync_from_github(context: Any) -> None:
    """Pulls latest state files from GitHub repository using GITHUB_TOKEN."""
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPO", "mrismail-m/ANTItrading")
    if not token or not repo:
        if hasattr(context, "log"):
            context.log("ℹ️ No GITHUB_TOKEN configured. Proceeding with bundled state.")
        return

    try:
        subprocess.run(["git", "config", "user.name", "ANTItrading-Appwrite-Bot"], cwd=ROOT_DIR, check=False)
        subprocess.run(["git", "config", "user.email", "bot@antitrader.internal"], cwd=ROOT_DIR, check=False)
        remote_url = f"https://{token}@github.com/{repo}.git"
        subprocess.run(["git", "remote", "set-url", "origin", remote_url], cwd=ROOT_DIR, check=False)
        if hasattr(context, "log"):
            context.log("📥 Pulling latest state from GitHub...")
        subprocess.run(["git", "pull", "--ff-only", "origin", "main"], cwd=ROOT_DIR, check=False)
    except Exception as err:
        if hasattr(context, "log"):
            context.log(f"⚠️ Git pull error (continuing with local state): {err}")


def sync_to_github(context: Any) -> None:
    """Commits and pushes modified state/ files to GitHub."""
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPO", "mrismail-m/ANTItrading")
    if not token or not repo:
        return

    try:
        subprocess.run(["git", "add", "state/"], cwd=ROOT_DIR, check=False)
        diff_res = subprocess.run(["git", "diff", "--staged", "--quiet"], cwd=ROOT_DIR)
        if diff_res.returncode != 0:
            if hasattr(context, "log"):
                context.log("💾 Committing and pushing state updates to GitHub...")
            subprocess.run(
                ["git", "commit", "-m", "chore(trader): automated pass update from appwrite [skip ci]"],
                cwd=ROOT_DIR,
                check=False
            )
            subprocess.run(["git", "push", "origin", "main"], cwd=ROOT_DIR, check=False)
            if hasattr(context, "log"):
                context.log("✅ Successfully pushed state updates to GitHub.")
        else:
            if hasattr(context, "log"):
                context.log("ℹ️ No state changes to commit.")
    except Exception as err:
        if hasattr(context, "error"):
            context.error(f"⚠️ Git push error: {err}")


def main(context: Any) -> Any:
    """
    Appwrite Function Entrypoint.
    Receives Appwrite's context object (with context.req, context.res, context.log, context.error).
    """
    if hasattr(context, "log"):
        context.log("🚀 ANTItrading Appwrite Function Triggered.")
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    try:
        # 1. Sync latest state from GitHub
        sync_from_github(context)

        # 2. Execute trading pass
        if hasattr(context, "log"):
            context.log("🧠 Executing live trading pass...")
        result = run_trader_pass(dry_run=False, silent=True)

        # 3. Persist state updates back to GitHub
        sync_to_github(context)

        portfolio = result.get("portfolio", {})
        cash = portfolio.get("cash", 0.0)
        history = portfolio.get("equity_history", [])
        curr_val = history[-1].get("portfolio_value", cash) if history else cash

        msg = f"✅ Pass completed! Equity: ${curr_val:,.2f} USD | Cash: ${cash:,.2f} USD"
        if hasattr(context, "log"):
            context.log(msg)

        if hasattr(context, "res") and hasattr(context.res, "json"):
            return context.res.json({
                "status": "success",
                "timestamp": now,
                "portfolio_value": curr_val,
                "cash_balance": cash,
                "open_positions": len(portfolio.get("positions", [])),
                "message": msg
            })
        return {"status": "success", "portfolio_value": curr_val}

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
