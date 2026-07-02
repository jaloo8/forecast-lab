#!/usr/bin/env bash
# Nightly DuckDB backup with rotation. v1 = local timestamped copy (cheap
# insurance against an `rm` / corruption). The external-drive + Backblaze B2
# leg from CLAUDE.md §10 is the next step once a target is configured.
#
# Env knobs: KQ_BACKUP_DIR (default ~/forecast-lab-backups), KQ_BACKUP_KEEP
# (default 14 most-recent copies), KQ_DUCKDB_CLI (duckdb CLI used for the
# pre-copy CHECKPOINT; defaults to `duckdb` on PATH), KQ_UV (fallback
# checkpoint runner; default ~/.local/bin/uv — deliberately NOT $UV, which
# `uv run` exports itself).
#
# Post-2026-06-11-audit hardening (the old script exited 0 on copy failure
# and copied DB+WAL non-atomically while writers run):
#   1. set -euo pipefail + ERR trap — ANY failure exits nonzero with a
#      message so cron sees it.
#   2. CHECKPOINT before copying — flushes the WAL into the main file so the
#      snapshot is consistent even after a crashed writer. If a writer holds
#      the DB lock the checkpoint fails and so does the backup, loudly —
#      better no backup than a silently torn one. (Schedule at a quiet
#      minute; the short per-tick cron jobs checkpoint on close.)
#   3. Copy to a temp name, then atomic mv — no half-written file is ever
#      visible under a final backup name.
set -euo pipefail
trap 'echo "backup: FAILED (line $LINENO)" >&2' ERR

REPO="$HOME/forecast-lab"
DB="$REPO/data/forecast_lab.duckdb"
DEST="${KQ_BACKUP_DIR:-$HOME/forecast-lab-backups}"
KEEP="${KQ_BACKUP_KEEP:-14}"
DUCKDB_CLI="${KQ_DUCKDB_CLI:-$(command -v duckdb || true)}"
UV="${KQ_UV:-$HOME/.local/bin/uv}"

[ -f "$DB" ] || { echo "backup: no DB at $DB" >&2; exit 1; }
mkdir -p "$DEST"

if [ -n "$DUCKDB_CLI" ] && [ -x "$DUCKDB_CLI" ]; then
  "$DUCKDB_CLI" "$DB" -c "CHECKPOINT" >/dev/null \
    || { echo "backup: checkpoint failed (duckdb CLI) — writer active or DB corrupt?" >&2; exit 1; }
elif [ -x "$UV" ]; then
  (cd "$REPO" && "$UV" run python -c \
    "import sys, duckdb; con = duckdb.connect(sys.argv[1]); con.execute('CHECKPOINT'); con.close()" \
    "$DB") \
    || { echo "backup: checkpoint failed (uv run python) — writer active or DB corrupt?" >&2; exit 1; }
else
  echo "backup: WARN no duckdb CLI and no uv at $UV — copying without checkpoint" >&2
fi

ts="$(date -u +%Y%m%dT%H%M%SZ)"
out="$DEST/forecast_lab_${ts}.duckdb"

cp -p "$DB" "${out}.tmp.$$"
mv "${out}.tmp.$$" "$out"
echo "backup: wrote $out ($(du -h "$out" | cut -f1))"
if [ -f "${DB}.wal" ]; then
  cp -p "${DB}.wal" "${out}.wal.tmp.$$"
  mv "${out}.wal.tmp.$$" "${out}.wal"
  echo "backup: + wal sidecar"
fi

# Prune: keep the newest $KEEP .duckdb backups (and their .wal siblings).
ls -1t "$DEST"/forecast_lab_*.duckdb | tail -n +"$((KEEP + 1))" | while read -r old; do
  rm -f "$old" "${old}.wal"
  echo "backup: pruned $(basename "$old")"
done
