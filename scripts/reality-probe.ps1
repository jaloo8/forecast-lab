# Native-Windows port of reality-probe.sh: the WEEKLY reality-contact probe.
#
# Runs `kq doctor` against the live venue and pushes an ntfy alert on CRIT
# (exit >= 2), i.e. when the venue's reality has drifted away from what the
# code assumes. The 2026-06-11 audit found wire-format drift can silently zero
# the system for weeks; this probe makes the next drift loud within a week.
#
# It was documented in docs/SCHEDULED-RUNS.md (`0 13 * * 1`) but never ported
# during the native-Windows cutover, so from the a8 migration until 2026-07-28
# NOTHING on the host checked reality-contact unattended -- `kq doctor` is the
# only automated check that would notice a dead ingest lane or a Kalshi payload
# change. Registered by scripts\install-ops-tasks.ps1.
#
# Output goes to logs\reality-probe.log (NOT cron.log -- a task that redirects
# into cron.log holds it open, which is what broke log rotation; see
# scripts\rotate-logs.ps1). The ntfy topic comes from NTFY_TOPIC in the repo's
# .env, exactly like cron-health.ps1 -- never hardcode a topic here.
#
# Exits with kq doctor's own code so Task Scheduler's Last Run Result is
# meaningful: 0 healthy, 1 WARN, >= 2 CRIT.
$ErrorActionPreference = 'Continue'

$repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$uv = if ($env:KQ_UV) { $env:KQ_UV } else { Join-Path $env:USERPROFILE '.local\bin\uv.exe' }
$logDir = Join-Path $repo 'logs'
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
$probeLog = Join-Path $logDir 'reality-probe.log'

Set-Location $repo
# UTF-8 so a non-cp437 character in doctor's output cannot kill the probe
# (see the PYTHONUTF8 note in scripts\kq-job.cmd -- same trap, same fix).
$env:PYTHONUTF8 = '1'

$stampLine = '=== reality-probe ' + (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ') + ' ==='
Add-Content -Path $probeLog -Value $stampLine -Encoding utf8

$out = & $uv run python -m kq doctor 2>&1 | Out-String
$rc = $LASTEXITCODE
Add-Content -Path $probeLog -Value $out.TrimEnd() -Encoding utf8
Add-Content -Path $probeLog -Value "=== exit $rc ===" -Encoding utf8

if ($rc -ge 2) {
    $topic = $null
    $envFile = Join-Path $repo '.env'
    if (Test-Path $envFile) {
        $line = Select-String -Path $envFile -Pattern '^NTFY_TOPIC=' | Select-Object -First 1
        if ($line) { $topic = ($line.Line -replace '^NTFY_TOPIC=', '').Trim() }
    }
    if ($topic) {
        $crits = ($out -split "`r?`n" | Where-Object { $_ -match '^\s*\[CRIT\]' } | Select-Object -First 5) -join '; '
        if (-not $crits) { $crits = "kq doctor exited $rc" }
        $msg = "REALITY DRIFT on $env:COMPUTERNAME - kq doctor found CRIT reality-contact failures: $crits"
        # curl.exe ships with Windows 10+; -f so HTTP errors surface in the log.
        & curl.exe -fsS -m 10 -H 'Title: forecast-lab reality probe' -H 'Priority: high' `
            -H 'Tags: rotating_light' -d $msg "https://ntfy.sh/$topic" | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Add-Content -Path $probeLog -Value 'reality-probe: ntfy push failed (network?)' -Encoding utf8
        }
    }
    else {
        Add-Content -Path $probeLog `
            -Value 'reality-probe: CRIT but NTFY_TOPIC not set in .env; no push sent' -Encoding utf8
    }
}
exit $rc
