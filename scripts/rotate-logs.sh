#!/usr/bin/env bash
# Rotate forecast-lab cron logs without sudo. Generates a logrotate config from
# this script's own location (so no hardcoded $HOME) and runs logrotate with a
# per-user state file. `copytruncate` copies then truncates in place, so cron's
# open append-handles on cron.log / health.log keep writing to the same inode —
# no need to signal the writers. Run daily from cron.
set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$SCRIPT_DIR")"
LOGDIR="$REPO/logs"
STATE="$REPO/.logrotate.state"

[ -d "$LOGDIR" ] || { echo "rotate-logs: no log dir at $LOGDIR" >&2; exit 0; }

CONF="$(mktemp)"
trap 'rm -f "$CONF"' EXIT
cat > "$CONF" <<EOF
$LOGDIR/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
}
EOF

logrotate -s "$STATE" "$CONF"
