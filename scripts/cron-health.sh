#!/usr/bin/env bash
# Cron wrapper around `kq health-check`: append the JSON snapshot to the
# heartbeat log, and push an ntfy alert only on CRIT (exit >= 2) so a single
# WARN (e.g. demo Kalshi has 0 markets) doesn't spam. Push-on-CRIT-only is
# safe against cron-death because health_check escalates prolonged staleness
# WARN -> CRIT past 3x each freshness threshold (audit 2026-06-11), so a dead
# pipeline reaches this push path within hours. Always exits 0 so cron never
# emails about it.
set -u
REPO="$HOME/forecast-lab"
UV="$HOME/.local/bin/uv"
cd "$REPO" || exit 0
mkdir -p logs

out="$("$UV" run python -m kq health-check --json 2>&1)"
rc=$?
printf '%s\n' "$out" >> "$REPO/logs/health.log"

if [ "$rc" -ge 2 ]; then
  bash "$REPO/scripts/notify-failure.sh" "health-check CRIT (exit $rc) on $(hostname) at $(date -u +%FT%TZ)"
fi
exit 0
