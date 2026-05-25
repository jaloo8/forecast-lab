#!/usr/bin/env bash
# Push a forecast-lab alert to ntfy.sh.
#
# The topic comes from NTFY_TOPIC in .env (gitignored) so it stays private —
# anyone who knows an ntfy topic can read/publish to it. Subscribe to the same
# topic in the ntfy phone app (https://ntfy.sh) to receive these.
#
# Usage: scripts/notify-failure.sh "message text"
# No-ops cleanly (exit 0) if NTFY_TOPIC is unset, so it's safe in cron.
set -u

# Resolve repo root from this script's location, so it works from any cwd.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$SCRIPT_DIR")"

msg="${1:-forecast-lab alert}"
topic="$(grep -E '^NTFY_TOPIC=' "$REPO/.env" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '[:space:]')"

if [ -z "$topic" ]; then
  echo "notify-failure: NTFY_TOPIC not set in .env; skipping push" >&2
  exit 0
fi

curl -fsS -m 10 \
  -H "Title: forecast-lab" \
  -H "Priority: high" \
  -H "Tags: rotating_light" \
  -d "$msg" \
  "https://ntfy.sh/${topic}" >/dev/null 2>&1 \
  || echo "notify-failure: ntfy push failed (network?)" >&2
exit 0
