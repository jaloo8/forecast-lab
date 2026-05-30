#!/usr/bin/env bash
# Phase 4 exit-criterion #2 drill (CLAUDE.md §5): prove a *real* pipeline
# failure is detected as CRIT and — optionally — that the ntfy alert actually
# reaches your phone. This is the live end-to-end complement to the hermetic
# unit tests: `test_health_check.py` already proves an empty weather table is
# CRIT, and `test_cron_scripts.py` (#91) already proves cron-health.sh fires
# notify-failure.sh on exit>=2. This script wires those proven pieces into the
# one thing only a live run can confirm: a synthetic failure → a real push.
#
# Two legs:
#   1. INJECTION (always; safe, repeatable, no phone spam): bootstrap a
#      throwaway empty DuckDB, point `kq health-check` at it via DATABASE_URL,
#      and assert it exits CRIT (>=2). Models the realistic "ingest stopped →
#      empty table" failure. Touches nothing real (temp DB, auto-removed).
#   2. DELIVERY (opt-in, --push): fire scripts/notify-failure.sh with a
#      clearly-labeled SYNTHETIC message → real ntfy push → your phone.
#      Requires NTFY_TOPIC in .env (no-ops cleanly without it). Skipped by
#      default so re-runs / CI never spam the phone.
#
# Usage:
#   scripts/alert-drill.sh            # injection only (asserted, safe)
#   scripts/alert-drill.sh --push     # + one real, clearly-labeled push
#
# Exit: 0 = drill passed (failure detected as CRIT); 1 = drill FAILED (a real
# failure was NOT detected — investigate the health-check before trusting cron).
set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$SCRIPT_DIR")"
UV="${UV:-$HOME/.local/bin/uv}"
cd "$REPO" || exit 1

PUSH=0
[ "${1:-}" = "--push" ] && PUSH=1

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
DB="$TMP/synthetic_empty.duckdb"

# --- Leg 1: inject a synthetic failure and assert CRIT detection ---
# Bootstrap an empty schema (tables exist, zero rows). An empty
# weather_forecast is a CRIT per health_check (the pipeline-stopped signal).
"$UV" run python -c "from pathlib import Path; from kq.storage.duckdb_store import bootstrap; bootstrap(Path('$DB'))"

out="$(DATABASE_URL="duckdb:///$DB" "$UV" run python -m kq health-check --json 2>&1)"
rc=$?
echo "drill: health-check on synthetic empty DB -> exit $rc"
echo "drill: $out"

if [ "$rc" -lt 2 ]; then
  echo "drill: FAIL — expected CRIT (exit >=2) on an empty DB, got $rc." >&2
  echo "drill: a real pipeline failure would NOT alert. Fix before trusting cron." >&2
  exit 1
fi
echo "drill: PASS — synthetic failure detected as CRIT (exit $rc)."

# --- Leg 2 (opt-in): real, clearly-labeled push ---
if [ "$PUSH" -eq 1 ]; then
  msg="[SYNTHETIC TEST] forecast-lab Phase 4 alert drill: health-check CRIT (exit ${rc}) on $(hostname) at $(date -u +%FT%TZ). No action needed — this is a test push, not a real outage."
  bash "$REPO/scripts/notify-failure.sh" "$msg"
  echo "drill: push attempted via notify-failure.sh — check your phone (needs NTFY_TOPIC in .env + topic subscribed)."
else
  echo "drill: delivery leg skipped (pass --push to fire one real labeled alert)."
fi
exit 0
