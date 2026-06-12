#!/usr/bin/env bash
# Weekly reality-contact probe: runs `kq doctor` against the live venue and
# pushes an ntfy alert on CRIT (reality drift). Cron recipe in
# docs/SCHEDULED-RUNS.md. The 2026-06-11 audit found wire-format drift can
# silently zero the system for weeks -- this probe makes the next drift loud
# within a week, automatically.
set -u
cd "$(dirname "$0")/.."

OUT="$(uv run python -m kq doctor 2>&1)"
CODE=$?
echo "$OUT"

if [ "$CODE" -ge 2 ] && [ -n "${NTFY_TOPIC:-}" ]; then
    SUMMARY="$(echo "$OUT" | grep '^\[CRIT\]' | head -5)"
    curl -s \
        -H "Title: forecast-lab REALITY DRIFT" \
        -H "Priority: high" \
        -H "Tags: rotating_light" \
        -d "kq doctor found CRIT reality-contact failures:
${SUMMARY}" \
        "https://ntfy.sh/${NTFY_TOPIC}" > /dev/null || echo "(ntfy push failed)"
fi
exit "$CODE"
