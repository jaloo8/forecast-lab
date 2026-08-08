# Status report, every 8 hours (00:00 / 08:00 / 16:00 local) -- prediction
# markets run 24/7, so one morning briefing was not enough. Each edition
# carries the standing status (pipeline health, paper totals, ops vitals)
# plus a SINCE-LAST-REPORT section computed against a small state file
# (logs\report-state.json): trades submitted/settled with P&L in the window,
# per-table ingest volume, fresh error lines in cron.log, and code deploys.
#
# Delivery (config from .env):
#   1. ntfy push to NTFY_TOPIC - always. NO ntfy `Email:` header on purpose:
#      measured 2026-07-27, anonymous ntfy.sh 400-rejects publishes carrying
#      one, which kills the push too.
#   2. Real email when KQ_REPORT_EMAIL + KQ_SMTP_HOST/USER/PASS are all set
#      (e.g. Yahoo: smtp.mail.yahoo.com, 587, an APP password). Optional
#      KQ_SMTP_PORT defaults to 587. Skipped silently while unset.
#
# Hard-won PS 5.1 rules honored here (do not "simplify" these away):
#   - multiline bodies to curl go via --data-binary @tempfile (argv newlines
#     fragment the command line)
#   - kq output is captured through cmd /c stream-merge (PS decorates native
#     stderr with ErrorRecord noise otherwise)
#   - LastTaskResult compares as [long] (0x8007xxxx overflows [int]) and
#     Running services are healthy by definition
#
# -Preview renders both bodies to the console and sends NOTHING (no push, no
# email, no state write). Use it to check the phone rendering after changing
# the layout, instead of spamming the topic to find out.
param([switch]$Preview)
$ErrorActionPreference = 'Continue'

$repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$uv = if ($env:KQ_UV) { $env:KQ_UV } else { Join-Path $env:USERPROFILE '.local\bin\uv.exe' }
Set-Location $repo
$logDir = Join-Path $repo 'logs'
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
$stateFile = Join-Path $logDir 'report-state.json'

function Get-DotenvValue([string]$Key) {
    $envFile = Join-Path $repo '.env'
    if (-not (Test-Path $envFile)) { return $null }
    $line = Select-String -Path $envFile -Pattern "^$Key=" | Select-Object -First 1
    if (-not $line) { return $null }
    return (($line.Line -replace "^$Key=", '') -replace '\s+#.*$', '').Trim()
}

# --- edition + window ------------------------------------------------------
$nowLocal = Get-Date
$nowUtc = $nowLocal.ToUniversalTime()
$edition = switch ($nowLocal.Hour) {
    { $_ -ge 4 -and $_ -lt 12 } { 'morning'; break }
    { $_ -ge 12 -and $_ -lt 20 } { 'afternoon'; break }
    default { 'overnight' }
}

$prev = $null
if (Test-Path $stateFile) {
    try { $prev = Get-Content $stateFile -Raw | ConvertFrom-Json } catch { $prev = $null }
}
$windowStartUtc = if ($prev -and $prev.last_run_utc) { [datetime]$prev.last_run_utc } else { $nowUtc.AddHours(-8) }
$windowStr = $windowStartUtc.ToString('yyyy-MM-dd HH:mm:ss')

# --- DB snapshot + window activity (one JSON line from a temp python) ------
$py = @'
import json, sys
import duckdb
since = sys.argv[1]
con = duckdb.connect("data/forecast_lab.duckdb", read_only=True)
out = {"rows": {}, "sub": [], "set": []}
for t in ("weather_forecast", "metar_obs", "ndfd_forecast", "kalshi_book_snap", "paper_trade"):
    try:
        out["rows"][t] = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
    except Exception:
        out["rows"][t] = -1
try:
    out["n_settled"] = con.execute("SELECT count(*) FROM paper_trade WHERE settled_at IS NOT NULL").fetchone()[0]
    out["pnl_total"] = con.execute("SELECT coalesce(sum(pnl_usd),0) FROM paper_trade").fetchone()[0]
    out["sub"] = [
        {"ticker": r[0], "side": r[1], "px": r[2], "qty": r[3]}
        for r in con.execute(
            "SELECT ticker, side, limit_price, qty FROM paper_trade "
            "WHERE submitted_at >= ? ORDER BY submitted_at DESC LIMIT 8", [since]).fetchall()
    ]
    out["set"] = [
        {"ticker": r[0], "res": r[1], "pnl": r[2]}
        for r in con.execute(
            "SELECT ticker, settlement, pnl_usd FROM paper_trade "
            "WHERE settled_at >= ? ORDER BY settled_at DESC LIMIT 8", [since]).fetchall()
    ]
except Exception as exc:
    out["err"] = str(exc)
con.close()
print(json.dumps(out, default=str))
'@
$pyFile = Join-Path $env:TEMP 'kq-status-query.py'
Set-Content -Path $pyFile -Value $py -Encoding ascii
$dbJson = & cmd.exe /c "`"$uv`" run python `"$pyFile`" `"$windowStr`" 2>&1" | Select-Object -Last 1
$db = $null
try { $db = $dbJson | ConvertFrom-Json } catch { $db = $null }

# --- pipeline health + paper totals ---------------------------------------
# Health check, with a bounded retry.
#
# A single attempt conflates "the pipeline is broken" with "we couldn't ask".
# Both DuckDB (single-writer file lock) and uv (venv lock during a re-sync
# right after a deploy) can transiently refuse for a few seconds, and the
# report then rendered the WORST verdict off zero evidence. Retry a couple of
# times; only if we still parsed nothing do we report UNKNOWN (below).
$healthAttempts = 0
$healthParsed = $false
foreach ($attempt in 1..3) {
    $healthAttempts = $attempt
    $health = & cmd.exe /c "`"$uv`" run python -m kq health-check 2>&1" | Out-String
    $healthRc = $LASTEXITCODE
    if (($health -split "`r?`n" | Where-Object { $_ -match '\[(OK|WRN|CRT)' }).Count -gt 0) {
        $healthParsed = $true
        break
    }
    if ($attempt -lt 3) { Start-Sleep -Seconds 15 }
}
$healthWord = @('OK', 'WARN', 'CRIT')[[Math]::Min($healthRc, 2)]
$paper = & cmd.exe /c "`"$uv`" run python -m kq paper-summary 2>&1" | Out-String

# --- since-last-report deltas ---------------------------------------------
$deltaLines = @()
if ($db) {
    $settledNow = [long]$db.n_settled
    $pnlNow = [double]$db.pnl_total
    if ($prev) {
        $dSettled = $settledNow - [long]$prev.n_settled
        $dPnl = $pnlNow - [double]$prev.pnl_total
        $deltaLines += ('settled {0:+#;-#;+0} in window -> {1} total | P&L {2:+0.00;-0.00;+0.00} -> {3:0.00} USD' -f $dSettled, $settledNow, $dPnl, $pnlNow)
        foreach ($t in @('weather_forecast', 'metar_obs', 'ndfd_forecast', 'kalshi_book_snap')) {
            $n = [long]$db.rows.$t; $p = [long]$prev.rows.$t
            if ($p -ge 0 -and $n -ge $p) { $deltaLines += ('{0,-18} +{1} rows' -f $t, ($n - $p)) }
        }
    }
    else {
        $deltaLines += "first run -- baseline established ($settledNow settled, P&L $([Math]::Round($pnlNow,2)) USD)"
    }
    if ($db.sub.Count -gt 0) {
        $deltaLines += 'submitted:'
        $db.sub | ForEach-Object { $deltaLines += ('  {0} {1} {2}x @ {3:0.00}' -f $_.ticker, $_.side, $_.qty, [double]$_.px) }
    }
    if ($db.set.Count -gt 0) {
        $deltaLines += 'settled:'
        $db.set | ForEach-Object { $deltaLines += ('  {0} -> {1}  P&L {2:+0.00;-0.00;0.00}' -f $_.ticker, $_.res, [double]$_.pnl) }
    }
    if ($db.sub.Count -eq 0 -and $db.set.Count -eq 0 -and $prev) { $deltaLines += 'no trade activity in this window' }
}
else { $deltaLines += 'db query failed -- see cron.log' }

# fresh error lines in cron.log since the window start (rotation-safe: the
# active file only ever holds today)
$errCount = 0; $errSample = @()
$cronLog = Join-Path $logDir 'cron.log'
if (Test-Path $cronLog) {
    # -CaseSensitive matters: Select-String defaults to case-INSENSITIVE, so
    # bare `FAILED` also matched the social lane's routine
    # `"n_sources_failed": 3` telemetry and inflated the count with non-errors.
    # Reddit 429s are a designed, self-healing condition (the flow rotates
    # subreddits and retries next tick), so they are excluded outright --
    # counting them trains the reader to ignore this number.
    $errs = Select-String -Path $cronLog -CaseSensitive `
            -Pattern '"level": "error"|Traceback|FAILED|exit [1-9]' |
        Where-Object { $_.Line -notmatch 'exit 0' -and $_.Line -notmatch 'social\.source_failed' }
    $errCount = ($errs | Measure-Object).Count
    $errSample = $errs | Select-Object -Last 2 | ForEach-Object { $_.Line.Substring(0, [Math]::Min(110, $_.Line.Length)) }
}

# deploys: did HEAD move since last report?
$head = (& git -C $repo rev-parse --short HEAD 2>$null | Out-String).Trim()
$deployLine = ''
if ($prev -and $prev.head -and $head -and $head -ne $prev.head) {
    $deployLine = "deployed: $($prev.head) -> $head"
    $deltaLines += "code deployed: $($prev.head) -> $head"
}

# --- task sweep + vitals ---------------------------------------------------
$okCodes = @([long]0, [long]267009, [long]267011)
$badTasks = @()
Get-ScheduledTask -TaskPath '\forecast-lab\' -ErrorAction SilentlyContinue | ForEach-Object {
    $i = $_ | Get-ScheduledTaskInfo
    if ($_.State -ne 'Running' -and $okCodes -notcontains [long]$i.LastTaskResult) {
        $badTasks += ('{0} rc={1} last={2:MM-dd HH:mm}' -f $_.TaskName, $i.LastTaskResult, $i.LastRunTime)
    }
}
$os = Get-CimInstance Win32_OperatingSystem
$disk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
$backupDir = if ($env:KQ_BACKUP_DIR) { $env:KQ_BACKUP_DIR } else { Join-Path $env:USERPROFILE 'forecast-lab-backups' }
$lastBackup = '(none found)'
if (Test-Path $backupDir) {
    $b = Get-ChildItem $backupDir -Filter '*.duckdb' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    # '{0:0.1}' was a BUG, not a typo-free format: in a .NET custom numeric
    # format a '.' with no digit placeholder after it is DROPPED and the '1'
    # is a literal, so a healthy 20.3h-old backup rendered as "201h ago" and
    # looked 8 days stale. Use '0.0' (a real one-decimal placeholder).
    # Backups are timestamped by Copy-Item from the source DB, so CreationTime
    # is when the backup was actually taken; LastWriteTime is inherited from
    # the database file and understates freshness.
    if ($b) { $lastBackup = '{0:0.0}h ago' -f ((Get-Date) - $b.CreationTime).TotalHours }
}

# --- compose ---------------------------------------------------------------
$settledTitle = if ($db) { $db.n_settled } else { '?' }
$taskLine = if ($badTasks.Count -eq 0) { 'all scheduled tasks healthy' } else { "FAILING TASKS:`n" + ($badTasks -join "`n") }
$errLine = if ($errCount -eq 0) { 'no new errors in cron.log' } else { "$errCount error line(s) in cron.log, newest:`n" + ($errSample -join "`n") }
# `-not $healthParsed` counts as ATTENTION on purpose: three failed attempts
# over ~30s is itself unusual. But the PIPELINE line will say UNKNOWN with the
# reason rather than asserting CRIT — "we couldn't ask" and "it's broken" are
# different facts and the report now distinguishes them.
$overall = if ($badTasks.Count -gt 0 -or -not $healthParsed -or $healthRc -ge 2) {
    'ATTENTION'
}
else { $healthWord }
$title = "forecast-lab $edition report: $overall -- $settledTitle settled"

# --- two renderings, on purpose ------------------------------------------
# The phone and the terminal are different media and the same text cannot
# serve both. ntfy renders push bodies in a PROPORTIONAL font, so every
# column-aligned block we used to paste straight through (`kq health-check`
# and `kq paper-summary` are fixed-width tables, and the delta lines used
# '{0,-18}' padding) arrived on the phone as ragged nonsense -- reported by
# the owner 2026-07-28: "nothing is lining up".
#
#   $bodyMobile - short label: value lines, NO padding, NO tables, ~1 screen.
#                 Goes to ntfy. Must stay readable in a proportional font.
#   $bodyFull   - the existing detail (raw tool output, monospace-friendly).
#                 Goes to email and the log, where a fixed-width font is the
#                 norm and the extra depth is worth having.

# Condense the health table to a verdict + only the checks that aren't OK.
#
# The glyph for critical is `CRT`, not `CRIT` (health_check.render_human).
# The old pattern matched (WRN|CRIT), so a CRT line matched NEITHER branch:
# the single most severe condition was the one whose detail never reached the
# phone. It showed only as the verdict word with no explanation. Match the
# glyphs the renderer actually emits.
$healthLines = $health -split "`r?`n"
$healthProblems = @($healthLines | Where-Object { $_ -match '\[(WRN|CRT)\]' } |
    ForEach-Object { ($_ -replace '^\s*\[(WRN|CRT)\]\s*', '') -replace '\s{2,}', ' ' })
$healthOkCount = @($healthLines | Where-Object { $_ -match '\[OK' }).Count

# UNKNOWN is not CRIT. If health-check produced no parseable check lines at
# all, we did not learn that the pipeline is broken — we learned nothing, and
# saying CRIT there is a lie in the alarming direction (observed 2026-08-08:
# "CRIT - 0 checks OK" while the system was in fact WARN with 5 checks OK).
# `Invoke-HealthCheck` above already retried; if it still parsed nothing, say
# so honestly and name the cause instead of inventing a verdict.
if (-not $healthParsed) {
    $healthWord = 'UNKNOWN'
    $healthProblems = @(
        "health-check produced no readable checks after $healthAttempts attempts (rc=$healthRc)"
    )
    $firstErr = @($healthLines | Where-Object { $_.Trim() } | Select-Object -First 1)
    if ($firstErr) { $healthProblems += $firstErr.Trim() }
}

# Pull the headline numbers out of paper-summary rather than pasting its
# 20-station table (which is almost entirely zeros while nothing has settled).
function Get-PaperField([string]$pattern) {
    $m = [regex]::Match($paper, $pattern)
    if ($m.Success) { return $m.Groups[1].Value.Trim() }
    return $null
}
$pSettled = Get-PaperField 'Trades settled\s*:\s*(\S+)'
$pFilled = Get-PaperField 'Trades filled\s*:\s*(\S+)'
$pPnl = Get-PaperField 'Total PnL\s*:\s*\$?\s*(\S+)'
$pWin = Get-PaperField 'Win rate[^:]*:\s*(\S+)'
$pGate = Get-PaperField 'Settled trades\s*:\s*(\d+\s*/\s*500)'

$mobileLines = @()
$mobileLines += "$edition report - $overall"
$mobileLines += $nowLocal.ToString('ddd MMM d, HH:mm') + ' local'
$mobileLines += ''
$mobileLines += 'TRADES'
$mobileLines += "open: $(if ($db) { [long]$db.rows.paper_trade - [long]$db.n_settled } else { '?' })  settled: $(if ($pSettled) { $pSettled } else { $settledTitle })"
if ($pPnl) { $mobileLines += "P&L: `$$pPnl" + $(if ($pWin) { "  win rate: $pWin" } else { '' }) }
if ($pFilled) { $mobileLines += "filled all-time: $pFilled" }
if ($pGate) { $mobileLines += "Phase 5 gate: $pGate" }
# Window activity, one short line each -- no column padding.
if ($db) {
    $nSub = @($db.sub).Count
    $nSet = @($db.set).Count
    $mobileLines += "this window: +$nSub new, $nSet settled"
    if ($nSet -gt 0) {
        $wp = ($db.set | Measure-Object -Property pnl -Sum).Sum
        $mobileLines += ('window P&L: {0:+0.00;-0.00;0.00}' -f [double]$wp)
    }
}
$mobileLines += ''
$mobileLines += 'PIPELINE'
$mobileLines += "$healthWord - $healthOkCount checks OK"
foreach ($p in $healthProblems) { $mobileLines += "! $p" }
$mobileLines += ''
$mobileLines += 'OPS'
if ($badTasks.Count -eq 0) { $mobileLines += 'all tasks healthy' }
else {
    $mobileLines += "FAILING: $($badTasks.Count) task(s)"
    foreach ($b in $badTasks) { $mobileLines += "! $b" }
}
$mobileLines += $(if ($errCount -eq 0) { 'no new errors' } else { "$errCount error line(s) in log" })
$mobileLines += "disk: $([Math]::Round($disk.FreeSpace/1GB)) GB free"
$mobileLines += "backup: $lastBackup"
if ($deployLine) { $mobileLines += $deployLine }
$bodyMobile = ($mobileLines -join "`n")

$bodyFull = @"
forecast-lab $edition report -- $env:COMPUTERNAME -- $($nowLocal.ToString('ddd yyyy-MM-dd HH:mm')) local
window: since $($windowStartUtc.ToString('MM-dd HH:mm'))Z

SINCE LAST REPORT
$($deltaLines -join "`n")
$errLine

PIPELINE: $healthWord
$($health.TrimEnd())

PAPER TOTALS
$($paper.TrimEnd())

OPS
$taskLine
uptime since : $($os.LastBootUpTime.ToString('MM-dd HH:mm'))  |  disk C: free: $([Math]::Round($disk.FreeSpace/1GB)) GB  |  last backup: $lastBackup
dashboard: http://100.108.199.57:8501  (tailnet)
"@
if ($bodyFull.Length -gt 3800) { $bodyFull = $bodyFull.Substring(0, 3800) + "`n[truncated]" }
# ntfy hard-caps the body; the mobile rendering should never come close, but
# truncate defensively rather than have the push silently rejected.
if ($bodyMobile.Length -gt 3800) { $bodyMobile = $bodyMobile.Substring(0, 3800) + "`n[truncated]" }
$body = $bodyFull

if ($Preview) {
    Write-Output ('=' * 46)
    Write-Output "TITLE: $title"
    Write-Output ('=' * 46)
    Write-Output '--- MOBILE (ntfy push, proportional font) ---'
    Write-Output $bodyMobile
    Write-Output ''
    Write-Output '--- FULL (email + log, monospace) ---'
    Write-Output $bodyFull
    Write-Output ('=' * 46)
    Write-Output 'preview only: nothing sent, no state written'
    exit 0
}

Add-Content -Path (Join-Path $logDir 'health.log') -Value "status-report: $title" -Encoding utf8

# --- persist state ---------------------------------------------------------
if ($db) {
    @{ last_run_utc = $nowUtc.ToString('yyyy-MM-ddTHH:mm:ssZ'); n_settled = $db.n_settled
       pnl_total = $db.pnl_total; rows = $db.rows; head = $head } |
        ConvertTo-Json -Depth 4 | Set-Content -Path $stateFile -Encoding utf8
}

# --- deliver ---------------------------------------------------------------
$topic = Get-DotenvValue 'NTFY_TOPIC'
$email = Get-DotenvValue 'KQ_REPORT_EMAIL'
if ($topic) {
    # PHONE gets $bodyMobile: ntfy renders in a proportional font, where the
    # fixed-width tables in $bodyFull do not line up (owner report 2026-07-28).
    $bodyFile = Join-Path $env:TEMP 'kq-status-report-body.txt'
    Set-Content -Path $bodyFile -Value $bodyMobile -Encoding utf8 -NoNewline
    & curl.exe -fsS -m 20 -H "Title: $title" -H 'Tags: bar_chart' `
        --data-binary "@$bodyFile" "https://ntfy.sh/$topic" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Add-Content -Path (Join-Path $logDir 'health.log') -Value 'status-report: ntfy push failed' -Encoding utf8
    }
    Remove-Item $bodyFile -Force -ErrorAction SilentlyContinue
}
$smtpHost = Get-DotenvValue 'KQ_SMTP_HOST'
$smtpUser = Get-DotenvValue 'KQ_SMTP_USER'
$smtpPass = Get-DotenvValue 'KQ_SMTP_PASS'
$smtpPort = Get-DotenvValue 'KQ_SMTP_PORT'
if (-not $smtpPort) { $smtpPort = '587' }
if ($email -and $smtpHost -and $smtpUser -and $smtpPass) {
    try {
        $msg = New-Object System.Net.Mail.MailMessage
        $msg.From = $smtpUser
        $msg.To.Add($email)
        $msg.Subject = $title
        $msg.Body = $body
        $client = New-Object System.Net.Mail.SmtpClient($smtpHost, [int]$smtpPort)
        $client.EnableSsl = $true
        $client.Credentials = New-Object System.Net.NetworkCredential($smtpUser, $smtpPass)
        $client.Send($msg)
        Add-Content -Path (Join-Path $logDir 'health.log') -Value "status-report: email sent to $email" -Encoding utf8
    }
    catch {
        Add-Content -Path (Join-Path $logDir 'health.log') -Value "status-report: email send failed: $($_.Exception.Message)" -Encoding utf8
    }
}
exit 0
