# Native-Windows port of cron-health.sh: append a health-check JSON snapshot
# to logs\health.log and push an ntfy alert ONLY on CRIT (exit >= 2), so a
# standing WARN (e.g. the calibration bar) never spams the phone. Always exits
# 0 so Task Scheduler never flags the heartbeat itself as failed.
# The ntfy topic comes from NTFY_TOPIC in the repo's .env (gitignored); if it
# is absent this degrades to log-only, same as the bash version.
$ErrorActionPreference = 'Continue'

$repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$uv = if ($env:KQ_UV) { $env:KQ_UV } else { Join-Path $env:USERPROFILE '.local\bin\uv.exe' }
$logDir = Join-Path $repo 'logs'
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }

Set-Location $repo
$out = & $uv run python -m kq health-check --json 2>&1 | Out-String
$rc = $LASTEXITCODE
Add-Content -Path (Join-Path $logDir 'health.log') -Value $out.TrimEnd() -Encoding utf8

if ($rc -ge 2) {
    $topic = $null
    $envFile = Join-Path $repo '.env'
    if (Test-Path $envFile) {
        $line = Select-String -Path $envFile -Pattern '^NTFY_TOPIC=' | Select-Object -First 1
        if ($line) { $topic = ($line.Line -replace '^NTFY_TOPIC=', '').Trim() }
    }
    if ($topic) {
        $msg = "forecast-lab health-check CRIT (exit $rc) on $env:COMPUTERNAME at " +
            (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
        # curl.exe ships with Windows 10+; -f so HTTP errors surface in the log.
        & curl.exe -fsS -m 10 -H 'Title: forecast-lab' -H 'Priority: high' `
            -H 'Tags: rotating_light' -d $msg "https://ntfy.sh/$topic" | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Add-Content -Path (Join-Path $logDir 'health.log') `
                -Value 'cron-health: ntfy push failed (network?)' -Encoding utf8
        }
    }
    else {
        Add-Content -Path (Join-Path $logDir 'health.log') `
            -Value 'cron-health: CRIT but NTFY_TOPIC not set in .env; no push sent' -Encoding utf8
    }
}
exit 0
