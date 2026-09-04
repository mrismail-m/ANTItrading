#!/usr/bin/env bash
# ==============================================================================
# ANTItrading - Autonomous Runner & Git Synchronization Wrapper
# ==============================================================================
set -e

# Change directory to repository root (parent directory of deploy/)
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

echo "========================================================================"
echo "⚡ Starting ANTItrading Hourly Pass: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "========================================================================"

# Pull latest code updates (fast-forward only) if git remote is configured
if git remote -v &>/dev/null; then
    echo "📥 Pulling latest git changes..."
    git pull --ff-only origin main || echo "⚠️  Git pull failed or skipped (continuing with local state)."
fi

# Execute paper-trading pass using the virtual environment python
echo "🧠 Executing run_trader.py..."
./venv/bin/python3 scripts/run_trader.py

# Auto-commit and push updated state files to GitHub
if git remote -v &>/dev/null; then
    echo "💾 Checking for state updates to commit..."
    git add state/
    if git diff --staged --quiet; then
        echo "ℹ️  No state changes to commit."
    else
        git commit -m "chore(trader): automated pass update from oracle vps [skip ci]" || true
        git push origin main || echo "⚠️  Git push skipped or authentication required."
    fi
fi

echo "✅ Trading pass completed successfully at $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo ""
