#!/usr/bin/env bash
# ==============================================================================
# ANTItrading - Oracle Cloud Always Free VPS Turnkey Provisioning Script
# ==============================================================================
set -e

REPO_URL="https://github.com/mrismail-m/ANTItrading.git"
INSTALL_DIR="/opt/ANTItrading"

echo "======================================================================"
echo "🚀 Setting up ANTItrading on Oracle Cloud Always Free Ubuntu Instance"
echo "======================================================================"

# 1. Ensure running with superuser privileges
if [ "$EUID" -ne 0 ]; then
    echo "❌ Please run this script with sudo or as root: sudo bash deploy/setup_oracle_vps.sh"
    exit 1
fi

ACTUAL_USER="${SUDO_USER:-$USER}"
ACTUAL_HOME=$(getent passwd "$ACTUAL_USER" | cut -d: -f6)

echo "👤 Installing under user: $ACTUAL_USER"

# 2. Update apt and install essential packages
echo "📦 Installing system dependencies (Python 3, venv, pip, git)..."
apt-get update -y
apt-get install -y python3 python3-pip python3-venv git curl ufw

# 3. Setup or update repository in /opt/ANTItrading
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "🔄 Existing repository found at $INSTALL_DIR. Pulling latest code..."
    cd "$INSTALL_DIR"
    git pull origin main || true
else
    echo "📥 Cloning repository to $INSTALL_DIR..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# 4. Create Python Virtual Environment & Install Requirements
echo "🐍 Setting up Python 3 virtual environment..."
if [ ! -d "$INSTALL_DIR/venv" ]; then
    python3 -m venv "$INSTALL_DIR/venv"
fi

"$INSTALL_DIR/venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

# 5. Ensure scripts are executable
chmod +x "$INSTALL_DIR/deploy/run_and_sync.sh"

# 6. Setup .env file if it doesn't exist
if [ ! -f "$INSTALL_DIR/.env" ]; then
    echo "⚙️ Creating .env configuration file from template..."
    cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
    echo "ℹ️  Remember to add your DISCORD_WEBHOOK_URL to $INSTALL_DIR/.env"
fi

# 7. Setup Log File and Permissions
touch /var/log/antitrader.log
chown "$ACTUAL_USER:$ACTUAL_USER" /var/log/antitrader.log
chown -R "$ACTUAL_USER:$ACTUAL_USER" "$INSTALL_DIR"

# 8. Setup Logrotate to prevent log files from bloating disk
cat <<EOF > /etc/logrotate.d/antitrader
/var/log/antitrader.log {
    daily
    missingok
    rotate 7
    compress
    delaycompress
    notifempty
    create 0640 $ACTUAL_USER $ACTUAL_USER
}
EOF

# 9. Configure and Install Systemd Service & Timer
echo "⏰ Installing systemd timer (hourly at :15)..."
sed -i "s/User=.*/User=$ACTUAL_USER/" "$INSTALL_DIR/deploy/antitrader.service" 2>/dev/null || true

cp "$INSTALL_DIR/deploy/antitrader.service" /etc/systemd/system/antitrader.service
cp "$INSTALL_DIR/deploy/antitrader.timer" /etc/systemd/system/antitrader.timer

systemctl daemon-reload
systemctl enable antitrader.timer
systemctl restart antitrader.timer

echo ""
echo "======================================================================"
echo "🎉 ANTItrading VPS Setup Completed Successfully!"
echo "======================================================================"
echo "Timer Status:"
systemctl status antitrader.timer --no-pager
echo ""
echo "Quick Commands:"
echo "  • Run a test pass immediately:   sudo systemctl start antitrader.service"
echo "  • View live logs:                sudo journalctl -u antitrader.service -f"
echo "  • View paper-trading logfile:    tail -f /var/log/antitrader.log"
echo "  • Edit Discord/Env settings:     nano $INSTALL_DIR/.env"
echo "======================================================================"
