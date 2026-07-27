# Native-Windows port of backup-duckdb.sh (same PR-G semantics): CHECKPOINT
# first, fail LOUDLY if it fails (never copy a torn snapshot), timestamped
# copy, prune to the newest N. Interface parity via the same env knobs:
#   KQ_BACKUP_DIR  (default: $HOME\forecast-lab-backups)
#   KQ_BACKUP_KEEP (default: 14)
#   KQ_UV          (default: $HOME\.local\bin\uv.exe) - runs the CHECKPOINT
# Repo root is derived from this script's location, so it works from any clone.
$ErrorActionPreference = 'Stop'

$repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$db = Join-Path $repo 'data\forecast_lab.duckdb'
$dest = if ($env:KQ_BACKUP_DIR) { $env:KQ_BACKUP_DIR } else { Join-Path $env:USERPROFILE 'forecast-lab-backups' }
$keep = if ($env:KQ_BACKUP_KEEP) { [int]$env:KQ_BACKUP_KEEP } else { 14 }
$uv = if ($env:KQ_UV) { $env:KQ_UV } else { Join-Path $env:USERPROFILE '.local\bin\uv.exe' }

if (-not (Test-Path $db)) {
    Write-Error "backup: no DB at $db"
    exit 1
}
if (-not (Test-Path $dest)) { New-Item -ItemType Directory -Path $dest -Force | Out-Null }

# CHECKPOINT flushes the WAL so the file copy is a consistent snapshot. A
# failure here usually means a writer holds the lock -- abort rather than
# copy a torn file; the next daily run retries.
Set-Location $repo
& $uv run python -c "import duckdb; con = duckdb.connect(r'$db'); con.execute('CHECKPOINT'); con.close(); print('CHECKPOINT ok')"
if ($LASTEXITCODE -ne 0) {
    Write-Error "backup: CHECKPOINT failed (exit $LASTEXITCODE) -- refusing to copy a possibly-torn snapshot"
    exit 1
}

$ts = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$out = Join-Path $dest "forecast_lab_$ts.duckdb"
$tmp = "$out.tmp"
Copy-Item $db $tmp
Move-Item $tmp $out
Write-Output ("backup: wrote {0} ({1:N0} bytes)" -f $out, (Get-Item $out).Length)
$wal = "$db.wal"
if (Test-Path $wal) {
    Copy-Item $wal "$out.wal"
    Write-Output "backup: + wal sidecar"
}

# Prune: newest $keep .duckdb backups survive (and their .wal siblings).
$all = Get-ChildItem $dest -Filter 'forecast_lab_*.duckdb' | Sort-Object LastWriteTime -Descending
if ($all.Count -gt $keep) {
    $all | Select-Object -Skip $keep | ForEach-Object {
        Remove-Item $_.FullName -Force
        if (Test-Path "$($_.FullName).wal") { Remove-Item "$($_.FullName).wal" -Force }
        Write-Output ("backup: pruned {0}" -f $_.Name)
    }
}
exit 0
