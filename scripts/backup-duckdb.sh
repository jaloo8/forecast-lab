#!/usr/bin/env bash
# Nightly DuckDB backup with rotation. v1 = local timestamped copy (cheap
# insurance against an `rm` / corruption). The external-drive + Backblaze B2
# leg from CLAUDE.md §10 is the next step once a target is configured.
#
# Env knobs: KQ_BACKUP_DIR (default ~/forecast-lab-backups), KQ_BACKUP_KEEP
# (default 14 most-recent copies).
#
# Caveat: this `cp`s the live single-file DB. Schedule it at a quiet minute
# (the cron entry uses a low-activity hour) so it doesn't race a writer; the
# short per-tick cron jobs check-point on close, so between ticks the file is
# consistent. Also copies the .wal sidecar if one is present.
set -u
REPO="$HOME/forecast-lab"
DB="$REPO/data/forecast_lab.duckdb"
DEST="${KQ_BACKUP_DIR:-$HOME/forecast-lab-backups}"
KEEP="${KQ_BACKUP_KEEP:-14}"

[ -f "$DB" ] || { echo "backup: no DB at $DB" >&2; exit 1; }
mkdir -p "$DEST"

ts="$(date -u +%Y%m%dT%H%M%SZ)"
out="$DEST/forecast_lab_${ts}.duckdb"
cp -p "$DB" "$out" && echo "backup: wrote $out ($(du -h "$out" | cut -f1))"
[ -f "${DB}.wal" ] && cp -p "${DB}.wal" "${out}.wal" && echo "backup: + wal sidecar"

# Prune: keep the newest $KEEP .duckdb backups (and their .wal siblings).
ls -1t "$DEST"/forecast_lab_*.duckdb 2>/dev/null | tail -n +"$((KEEP + 1))" | while read -r old; do
  rm -f "$old" "${old}.wal" && echo "backup: pruned $(basename "$old")"
done
exit 0
