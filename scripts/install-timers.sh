#!/bin/bash
# Install OpportunityScout systemd timers
# Usage: sudo bash scripts/install-timers.sh
set -e

PROJECT=/opt/opportunity-scout
SYSTEMD_DIR=/etc/systemd/system

echo "📦 Installing OpportunityScout systemd timers..."

# Make wrapper scripts executable
chmod +x "$PROJECT/scripts/run-daily.sh"
chmod +x "$PROJECT/scripts/run-weekly.sh"
chmod +x "$PROJECT/scripts/run-midweek.sh"

# Copy service and timer files
for unit in scout-daily scout-weekly scout-midweek scout-backup; do
    cp "$PROJECT/systemd/${unit}.service" "$SYSTEMD_DIR/"
    cp "$PROJECT/systemd/${unit}.timer" "$SYSTEMD_DIR/"
    echo "  ✅ Installed ${unit}.service + .timer"
done

# Reload systemd
systemctl daemon-reload

# Enable and start timers
for timer in scout-daily scout-weekly scout-midweek scout-backup; do
    systemctl enable "${timer}.timer"
    systemctl start "${timer}.timer"
    echo "  🟢 Enabled ${timer}.timer"
done

# Remove old crontab entries (keep empty crontab)
crontab -u ubuntu -r 2>/dev/null || true
echo "  🗑️  Old crontab removed"

echo ""
echo "✅ All timers installed. Check status with:"
echo "   systemctl list-timers 'scout-*'"
echo ""
echo "📋 View logs with:"
echo "   journalctl -u scout-daily --since today"
echo "   journalctl -u scout-weekly --since '1 week ago'"
echo ""
echo "🔧 Manual trigger:"
echo "   sudo systemctl start scout-daily.service"
