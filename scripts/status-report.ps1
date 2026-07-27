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
$health = & cmd.exe /c "`"$uv`" run python -m kq health-check 2>&1" | Out-String
$healthRc = $LASTEXITCODE
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
    $errs = Select-String -Path $cronLog -Pattern '"level": "error"|Traceback|FAILED|exit [1-9]' |
        Where-Object { $_.Line -notmatch 'exit 0' }
    $errCount = ($errs | Measure-Object).Count
    $errSample = $errs | Select-Object -Last 2 | ForEach-Object { $_.Line.Substring(0, [Math]::Min(110, $_.Line.Length)) }
}

# deploys: did HEAD move since last report?
$head = (& git -C $repo rev-parse --short HEAD 2>$null | Out-String).Trim()
if ($prev -and $prev.head -and $head -and $head -ne $prev.head) {
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
    if ($b) { $lastBackup = '{0:0.1}h ago' -f ((Get-Date) - $b.LastWriteTime).TotalHours }
}

# --- compose ---------------------------------------------------------------
$settledTitle = if ($db) { $db.n_settled } else { '?' }
$taskLine = if ($badTasks.Count -eq 0) { 'all scheduled tasks healthy' } else { "FAILING TASKS:`n" + ($badTasks -join "`n") }
$errLine = if ($errCount -eq 0) { 'no new errors in cron.log' } else { "$errCount error line(s) in cron.log, newest:`n" + ($errSample -join "`n") }
$overall = if ($badTasks.Count -gt 0 -or $healthRc -ge 2) { 'ATTENTION' } else { $healthWord }
$title = "forecast-lab $edition report: $overall -- $settledTitle settled"

$body = @"
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
if ($body.Length -gt 3800) { $body = $body.Substring(0, 3800) + "`n[truncated]" }

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
    $bodyFile = Join-Path $env:TEMP 'kq-status-report-body.txt'
    Set-Content -Path $bodyFile -Value $body -Encoding utf8 -NoNewline
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
