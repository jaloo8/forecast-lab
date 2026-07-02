#!/usr/bin/env bash
# Weekly reality-contact probe: runs `kq doctor` against the live venue and
# pushes an ntfy alert on CRIT (reality drift). Cron recipe in
# docs/SCHEDULED-RUNS.md. The 2026-06-11 audit found wire-format drift can
# silently zero the system for weeks -- this probe makes the next drift loud
# within a week, automatically.
#
# The alert goes through scripts/notify-failure.sh so the ntfy topic comes
# from ONE place ($NTFY_TOPIC env, falling back to NTFY_TOPIC in .env) --
# never hardcode a topic here or in the crontab.
set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$SCRIPT_DIR")"
cd "$REPO" || exit 1

# Resolve uv the way the other cron scripts do: cron's minimal PATH has no
# `uv` (a bare `uv` exits 127 and the probe never runs -- 2026-07-01 audit).
# Honor an explicit $UV, then PATH, then the documented install location.
UV="${UV:-$(command -v uv || echo "$HOME/.local/bin/uv")}"

OUT="$("$UV" run python -m kq doctor 2>&1)"
CODE=$?
echo "$OUT"

if [ "$CODE" -ge 2 ]; then
    SUMMARY="$(echo "$OUT" | grep '^\[CRIT\]' | head -5)"
    bash "$SCRIPT_DIR/notify-failure.sh" "REALITY DRIFT: kq doctor found CRIT reality-contact failures:
${SUMMARY}"
fi
exit "$CODE"
