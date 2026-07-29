# Native-Windows port of rotate-logs.sh. Daily: roll each *.log to a
# date-stamped .old, then prune stamped logs older than KQ_LOG_KEEP_DAYS
# (default 14).
#
# ---------------------------------------------------------------------------
# WHY COPY-TRUNCATE AND NOT RENAME -- this script used to be broken
# ---------------------------------------------------------------------------
# The original port assumed a rename was safe because "every job invocation
# opens/closes the log via cmd's >> append, so a between-runs rename never
# strands an open handle". That assumption was wrong twice over, and rotation
# of cron.log therefore failed EVERY night from the a8 cutover until
# 2026-07-28 -- while still reporting success:
#
#   1. The rotate task itself was registered with `>> logs\cron.log 2>&1`, so
#      THIS SCRIPT held cron.log open with one hand while trying to rename it
#      with the other. A guaranteed, self-inflicted, permanent failure.
#      (Fixed on the registration side in install-ops-tasks.ps1.)
#   2. dashboard.log is held open continuously by the long-running Streamlit
#      service, so it can never be renamed while the dashboard is up.
#
# health.log was the only log that rotated -- and its task is the only one
# that does not redirect into cron.log, which was the tell.
#
# Windows refuses a rename on an open file but DOES allow copy-then-truncate,
# which is exactly what logrotate's `copytruncate` does on Linux and what the
# canonical cron recipe in docs/SCHEDULED-RUNS.md specifies. Truncating in
# place keeps every existing writer's handle valid.
#
# Failures are now reported honestly: the success line only prints when the
# rotation actually happened, and the script exits non-zero if any log could
# not be rotated, so Task Scheduler's Last Run Result and the status report's
# failing-task sweep can see it.
$ErrorActionPreference = 'Continue'

$repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$logDir = Join-Path $repo 'logs'
$keepDays = if ($env:KQ_LOG_KEEP_DAYS) { [int]$env:KQ_LOG_KEEP_DAYS } else { 14 }

if (-not (Test-Path $logDir)) {
    Write-Output "rotate-logs: no log dir at $logDir"
    exit 0
}

function Copy-ThenTruncate {
    <#
      Copy $Path's current contents onto $Dest (appending if $Dest exists),
      then truncate $Path to zero IN PLACE so open writer handles stay valid.
      Returns $true only when the truncation actually succeeded.
    #>
    param([string]$Path, [string]$Dest)

    # FileShare ReadWrite|Delete so this open does not disturb -- and is not
    # blocked by -- jobs appending concurrently.
    $share = [System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete
    try {
        $fs = [System.IO.File]::Open(
            $Path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::ReadWrite, $share)
    }
    catch {
        Write-Output ("rotate-logs: FAILED to open {0}: {1}" -f (Split-Path $Path -Leaf), $_.Exception.Message)
        return $false
    }

    try {
        $fs.Position = 0
        $reader = New-Object System.IO.StreamReader($fs, [System.Text.Encoding]::UTF8, $true, 4096, $true)
        $content = $reader.ReadToEnd()
        $reader.Dispose()

        if ($content.Length -gt 0) {
            # Append rather than clobber: a second rotation on the same day
            # (e.g. an installer re-run) must not discard the first.
            Add-Content -Path $Dest -Value $content -Encoding utf8 -NoNewline
        }

        $fs.SetLength(0)
        $fs.Flush()
        return $true
    }
    catch {
        Write-Output ("rotate-logs: FAILED to rotate {0}: {1}" -f (Split-Path $Path -Leaf), $_.Exception.Message)
        return $false
    }
    finally {
        $fs.Dispose()
    }
}

$stamp = (Get-Date).ToString('yyyyMMdd')
$failed = 0

Get-ChildItem $logDir -Filter '*.log' | Where-Object { $_.Length -gt 0 } | ForEach-Object {
    $rotated = Join-Path $logDir ($_.BaseName + "-$stamp" + $_.Extension + '.old')
    if (Copy-ThenTruncate -Path $_.FullName -Dest $rotated) {
        Write-Output ("rotate-logs: {0} -> {1}" -f $_.Name, (Split-Path $rotated -Leaf))
    }
    else {
        $failed++
    }
}

$cutoff = (Get-Date).AddDays(-$keepDays)
Get-ChildItem $logDir -Filter '*.old' | Where-Object { $_.LastWriteTime -lt $cutoff } | ForEach-Object {
    Remove-Item $_.FullName -Force
    Write-Output ("rotate-logs: pruned {0}" -f $_.Name)
}

if ($failed -gt 0) {
    Write-Output "rotate-logs: $failed log(s) could not be rotated"
    exit 1
}
exit 0
