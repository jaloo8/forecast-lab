# Native-Windows port of rotate-logs.sh. No copytruncate needed here: on the
# Windows host every job invocation opens/closes the log via cmd's >> append,
# so a between-runs rename never strands an open handle (unlike Linux cron's
# long-lived redirection). Daily: date-stamp each *.log, then delete stamped
# logs older than KQ_LOG_KEEP_DAYS (default 14).
$ErrorActionPreference = 'Continue'

$repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$logDir = Join-Path $repo 'logs'
$keepDays = if ($env:KQ_LOG_KEEP_DAYS) { [int]$env:KQ_LOG_KEEP_DAYS } else { 14 }

if (-not (Test-Path $logDir)) {
    Write-Output "rotate-logs: no log dir at $logDir"
    exit 0
}

$stamp = (Get-Date).ToString('yyyyMMdd')
Get-ChildItem $logDir -Filter '*.log' | Where-Object { $_.Length -gt 0 } | ForEach-Object {
    $rotated = Join-Path $logDir ($_.BaseName + "-$stamp" + $_.Extension + '.old')
    if (Test-Path $rotated) {
        # Second rotation same day (e.g. installer re-run): append instead of clobber.
        Add-Content -Path $rotated -Value (Get-Content $_.FullName -Raw) -Encoding utf8
        Remove-Item $_.FullName -Force
    }
    else {
        Move-Item $_.FullName $rotated
    }
    Write-Output ("rotate-logs: {0} -> {1}" -f $_.Name, (Split-Path $rotated -Leaf))
}

$cutoff = (Get-Date).AddDays(-$keepDays)
Get-ChildItem $logDir -Filter '*.old' | Where-Object { $_.LastWriteTime -lt $cutoff } | ForEach-Object {
    Remove-Item $_.FullName -Force
    Write-Output ("rotate-logs: pruned {0}" -f $_.Name)
}
exit 0
