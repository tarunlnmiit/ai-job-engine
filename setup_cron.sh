#!/bin/bash
# Setup cron job for daily scoring at 1 AM IST

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="python3"
DAEMON_SCRIPT="$PROJECT_DIR/core/scheduler/scoring_daemon.py"
LOG_FILE="$PROJECT_DIR/logs/scoring_daemon.log"

# Ensure logs dir exists
mkdir -p "$PROJECT_DIR/logs"

# Add cron job (1 AM IST = 01:00 in Asia/Kolkata timezone)
CRON_ENTRY="0 1 * * * cd $PROJECT_DIR && TZ=Asia/Kolkata $PYTHON_BIN $DAEMON_SCRIPT --context EU >> $LOG_FILE 2>&1"

echo "Adding cron job for daily scoring at 1 AM IST..."
echo "Cron entry: $CRON_ENTRY"
echo ""

# Check if entry already exists
if crontab -l 2>/dev/null | grep -q "scoring_daemon.py"; then
    echo "⚠️  Cron entry for scoring_daemon.py already exists."
    echo "View current crontab: crontab -l"
    echo "Edit: crontab -e"
else
    # Add to crontab
    (crontab -l 2>/dev/null; echo "$CRON_ENTRY") | crontab -
    echo "✅ Cron job added successfully!"
    echo ""
    echo "Verify with: crontab -l | grep scoring_daemon"
    echo "View logs: tail -f $LOG_FILE"
fi
