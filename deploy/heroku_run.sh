#!/usr/bin/env bash
# ==============================================================================
# ANTItrading - Heroku Execution & Git Persistence Runner
# ==============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

echo "========================================================================"
echo "⚡ Starting ANTItrading Pass on Heroku: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "========================================================================"

# Configure git credentials if GITHUB_TOKEN is present
if [ -n "$GITHUB_TOKEN" ] && [ -n "$GITHUB_REPO" ]; then
    echo "🔑 Configuring Git credentials via GITHUB_TOKEN..."
    git config user.name "ANTItrading-Heroku-Bot"
    git config user.email "bot@antitrader.internal"
    git remote set-url origin "https://${GITHUB_TOKEN}@github.com/${GITHUB_REPO}.git"

    echo "📥 Pulling latest state from GitHub..."
    git pull --ff-only origin main || echo "⚠️  Git pull failed or diverged, continuing with current state."
fi

# Execute trader pass
echo "🧠 Executing run_trader.py..."
python3 scripts/run_trader.py

# Push state updates back to GitHub to survive Heroku's ephemeral dyno resets
if [ -n "$GITHUB_TOKEN" ] && [ -n "$GITHUB_REPO" ]; then
    echo "💾 Preserving state to GitHub..."
    git add state/
    if git diff --staged --quiet; then
        echo "ℹ️  No state changes to commit."
    else
        git commit -m "chore(trader): automated hourly pass update from heroku [skip ci]" || true
        git push origin main || echo "⚠️  Git push failed. Verify GITHUB_TOKEN permissions."
    fi
fi

echo "✅ [Heroku] Trading pass completed successfully."
