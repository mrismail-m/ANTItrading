#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
ANTItrading Discord Webhook Notifier
===============================================================================
Dispatches real-time portfolio updates, realized P&L, unrealized P&L,
and an ASCII-formatted active positions table to a Discord channel via webhook.
===============================================================================
"""

import os
import sys
import datetime
import requests
from typing import Dict, Any, List

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def get_discord_webhook_url() -> str:
    """
    Retrieves the Discord webhook URL from environment variables or .env file.
    """
    url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not url and os.path.exists(".env"):
        try:
            with open(".env", "r") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("DISCORD_WEBHOOK_URL="):
                        url = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
        except Exception:
            pass
    return url


def format_active_trades_table(positions: List[Dict[str, Any]], price_map: Dict[str, float]) -> str:
    """
    Renders an ASCII table showing strictly: Coin | Unrealized PNL
    """
    if not positions:
        return "No active positions currently open."

    headers = ["Coin", "Unrealized PNL"]
    rows = []

    for p in positions:
        sym = p.get("symbol", "-")
        entry = float(p.get("entry_price", 0.0))
        qty = float(p.get("qty", 0.0))
        cost_basis = float(p.get("cost_basis", entry * qty))
        curr = price_map.get(sym, 0.0)
        if curr <= 0.0:
            curr = entry if entry > 0.0 else float(p.get("highest_price", 1.0))

        val = qty * curr
        diff_usd = val - cost_basis
        diff_pct = ((curr - entry) / entry) * 100 if entry > 0 else 0.0

        sign = "+" if diff_usd >= 0 else "-"
        pnl_str = f"{sign}${abs(diff_usd):.2f} ({diff_pct:+.2f}%)"
        rows.append([sym, pnl_str])

    # Calculate column widths
    col_widths = [len(h) for h in headers]
    for r in rows:
        for i, val in enumerate(r):
            col_widths[i] = max(col_widths[i], len(val))

    # Build ASCII table
    header_line = " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    sep_line = "-+-".join("-" * col_widths[i] for i in range(len(headers)))
    row_lines = [" | ".join(r[i].ljust(col_widths[i]) for i in range(len(headers))) for r in rows]

    return "\n".join([header_line, sep_line] + row_lines)


def send_discord_notification(
    portfolio: Dict[str, Any],
    decisions: List[Dict[str, Any]],
    regime: str = "bullish_trend"
) -> bool:
    """
    Sends an executive Discord embed with Realized P&L and Active Trades table.
    """
    webhook_url = get_discord_webhook_url()
    if not webhook_url or not webhook_url.startswith("http"):
        print("ℹ️  Discord webhook URL not configured (DISCORD_WEBHOOK_URL). Skipping notification.")
        return False

    cash = float(portfolio.get("cash", 10000.0))
    start_cash = float(portfolio.get("starting_cash", 10000.0))
    positions = portfolio.get("positions", [])

    # Map current prices from decisions (filter out 0.0 errors)
    price_map = {}
    for d in decisions:
        p_val = float(d.get("price", 0.0))
        if p_val > 0.0:
            price_map[d.get("symbol")] = p_val

    total_cost_basis = sum(float(p.get("cost_basis", 0.0)) for p in positions)
    current_market_val = 0.0
    for p in positions:
        sym = p.get("symbol", "-")
        qty = float(p.get("qty", 0.0))
        entry = float(p.get("entry_price", 0.0))
        curr = price_map.get(sym, 0.0)
        if curr <= 0.0:
            curr = entry if entry > 0.0 else float(p.get("highest_price", 1.0))
        current_market_val += qty * curr

    unrealized_pnl = current_market_val - total_cost_basis
    realized_pnl = (cash + total_cost_basis) - start_cash
    total_equity = cash + current_market_val
    total_pnl = total_equity - start_cash
    total_pnl_pct = (total_pnl / start_cash) * 100 if start_cash > 0 else 0.0

    # Format Active Trades ASCII Table
    table_text = format_active_trades_table(positions, price_map)

    # Filter actions in this pass
    buys = [d for d in decisions if d.get("action") == "BUY"]
    trims = [d for d in decisions if d.get("action") == "TRIM"]
    sells = [d for d in decisions if d.get("action") == "SELL"]

    actions_summary = []
    for b in buys:
        actions_summary.append(f"🟢 BUY: {b.get('symbol')} (${float(b.get('amount_usd', 0)):.2f})")
    for t in trims:
        pnl = float(t.get("pnl_pct", 10.0))
        profit_usd = float(t.get("profit_usd", 0.0))
        p_str = f" | Banked: {profit_usd:+.2f} USD (+{pnl:.2f}%)" if profit_usd != 0 else f" (+{pnl:.2f}%)"
        actions_summary.append(f"✂️ TRIM: {t.get('symbol')}{p_str}")
    for s in sells:
        pnl = float(s.get("pnl_pct", 0.0))
        profit_usd = float(s.get("profit_usd", 0.0))
        p_val = float(s.get("fill_price", s.get("price", 0.0)))
        icon = "🟢" if pnl >= 0 else "🔴"
        p_str = f" | Realized PnL: {profit_usd:+.2f} USD ({pnl:+.2f}%)" if (profit_usd != 0 or pnl != 0) else ""
        actions_summary.append(f"{icon} SELL: {s.get('symbol')} @ ${p_val:.4f}{p_str}")

    embed_color = 0x00FF7F if total_pnl >= 0 else 0xFF4500

    desc_lines = [
        f"Portfolio Value: ${total_equity:,.2f} ({total_pnl_pct:+.2f}%)",
        f"Realized P&L: {realized_pnl:+,.2f} USD",
        f"Unrealized P&L: {unrealized_pnl:+,.2f} USD",
        "",
        f"```text\n{table_text}\n```"
    ]
    if actions_summary:
        desc_lines.extend(["", "Executed Orders:", "\n".join(actions_summary)])

    embed = {
        "color": embed_color,
        "description": "\n".join(desc_lines)
    }

    payload = {
        "username": "ANTItrading Agent",
        "embeds": [embed]
    }

    try:
        res = requests.post(webhook_url, json=payload, timeout=10)
        if res.status_code in [200, 204]:
            print("✅ Discord webhook notification sent successfully.")
            return True
        else:
            print(f"⚠️  Discord webhook returned status {res.status_code}: {res.text}", file=sys.stderr)
            return False
    except Exception as err:
        print(f"⚠️  Failed to send Discord webhook: {err}", file=sys.stderr)
        return False


if __name__ == "__main__":
    from scripts.execute_trade import load_portfolio
    portfolio_data = load_portfolio()
    # Mock prices for testing
    mock_decisions = [
        {"symbol": "SOL", "price": 100.85, "action": "HOLD"},
        {"symbol": "DOT", "price": 0.8770, "action": "HOLD"},
        {"symbol": "LTC", "price": 50.99, "action": "HOLD"},
        {"symbol": "NEAR", "price": 1.900, "action": "HOLD"},
        {"symbol": "ICP", "price": 2.493, "action": "HOLD"},
        {"symbol": "APT", "price": 0.604, "action": "HOLD"}
    ]
    table = format_active_trades_table(portfolio_data.get("positions", []), {d["symbol"]: d["price"] for d in mock_decisions})
    print(table)
    send_discord_notification(portfolio_data, mock_decisions)
