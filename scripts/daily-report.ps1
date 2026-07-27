# Daily status report: one email (+ ntfy push) summarizing the host, the
# pipeline, and how paper trading is going. Scheduled for 08:00 LOCAL --
# deliberately local, not UTC parity: it is a human briefing, and 08:00 sits
# after the 07:30 paper-submit pass so the morning's trades are included.
#
# Delivery, in order of preference (config from .env):
#   1. ntfy push to NTFY_TOPIC - always, when the topic is set. NOTE: we
#      deliberately do NOT attach ntfy's `Email:` header - measured 2026-07-27,
#      anonymous ntfy.sh rejects any publish carrying it with HTTP 400, which
#      kills the push as well. Push-only via ntfy.
#   2. Real email via SMTP - only when ALL of KQ_REPORT_EMAIL, KQ_SMTP_HOST,
#      KQ_SMTP_USER, KQ_SMTP_PASS are set (e.g. Yahoo: smtp.mail.yahoo.com,
#      port 587, an app password - NOT the account password). Optional
#      KQ_SMTP_PORT defaults to 587. Skipped silently when unset.
$ErrorActionPreference = 'Continue'

$repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$uv = if ($env:KQ_UV) { $env:KQ_UV } else { Join-Path $env:USERPROFILE '.local\bin\uv.exe' }
Set-Location $repo

function Get-DotenvValue([string]$Key) {
    $envFile = Join-Path $repo '.env'
    if (-not (Test-Path $envFile)) { return $null }
    $line = Select-String -Path $envFile -Pattern "^$Key=" | Select-Object -First 1
    if (-not $line) { return $null }
    $v = ($line.Line -replace "^$Key=", '')
    # Strip a trailing inline comment, then whitespace.
    return ($v -replace '\s+#.*$', '').Trim()
}

# --- 1. pipeline health ---------------------------------------------------
# Route through cmd /c so stderr merges into stdout BEFORE PowerShell sees it:
# PS 5.1 wraps native stderr lines in ErrorRecords, which stringify with
# "uv.exe : ... CategoryInfo ..." decoration and wreck the report body.
$health = & cmd.exe /c "`"$uv`" run python -m kq health-check 2>&1" | Out-String
$healthRc = $LASTEXITCODE
$healthWord = @('OK', 'WARN', 'CRIT')[[Math]::Min($healthRc, 2)]

# --- 2. paper trading -----------------------------------------------------
$paper = & cmd.exe /c "`"$uv`" run python -m kq paper-summary 2>&1" | Out-String
$settled = '?'
if ($paper -match 'Trades settled\s*:\s*(\d+)') { $settled = $Matches[1] }

# --- 3. scheduled-task sweep: anything failing? ---------------------------
# 0 = last run OK; 267009 = currently running; 267011 = has not run yet.
# LastTaskResult is a UInt32: codes like 0x80070520 (2147946720) overflow a
# [int] cast and throw InvalidCast mid-pipeline -- compare as [long]. A task
# in the Running state is healthy by definition (long-running services keep
# the PREVIOUS run's code, e.g. the dashboard after a deliberate restart).
$okCodes = @([long]0, [long]267009, [long]267011)
$badTasks = @()
Get-ScheduledTask -TaskPath '\forecast-lab\' -ErrorAction SilentlyContinue | ForEach-Object {
    $i = $_ | Get-ScheduledTaskInfo
    if ($_.State -ne 'Running' -and $okCodes -notcontains [long]$i.LastTaskResult) {
        $badTasks += ('{0} rc={1} last={2:MM-dd HH:mm}' -f $_.TaskName, $i.LastTaskResult, $i.LastRunTime)
    }
}

# --- 4. host vitals -------------------------------------------------------
$os = Get-CimInstance Win32_OperatingSystem
$disk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
$backupDir = if ($env:KQ_BACKUP_DIR) { $env:KQ_BACKUP_DIR } else { Join-Path $env:USERPROFILE 'forecast-lab-backups' }
$lastBackup = '(none found)'
if (Test-Path $backupDir) {
    $b = Get-ChildItem $backupDir -Filter '*.duckdb' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($b) { $lastBackup = '{0:.1f}h ago ({1:N1} MB)' -f ((Get-Date) - $b.LastWriteTime).TotalHours, ($b.Length / 1MB) }
}

# --- compose --------------------------------------------------------------
$taskLine = if ($badTasks.Count -eq 0) { 'all scheduled tasks healthy' }
else { "FAILING TASKS:`n" + ($badTasks -join "`n") }
$overall = if ($badTasks.Count -gt 0 -or $healthRc -ge 2) { 'ATTENTION' } else { $healthWord }

$body = @"
forecast-lab daily report -- $env:COMPUTERNAME -- $((Get-Date).ToString('ddd yyyy-MM-dd HH:mm')) local

PIPELINE: $healthWord
$($health.TrimEnd())

PAPER TRADING
$($paper.TrimEnd())

OPS
$taskLine
uptime since : $($os.LastBootUpTime.ToString('yyyy-MM-dd HH:mm'))
disk C: free : $([Math]::Round($disk.FreeSpace/1GB)) GB
last backup  : $lastBackup

dashboard: http://100.108.199.57:8501  (tailnet)
"@
if ($body.Length -gt 3800) { $body = $body.Substring(0, 3800) + "`n[truncated]" }

# --- deliver --------------------------------------------------------------
$topic = Get-DotenvValue 'NTFY_TOPIC'
$email = Get-DotenvValue 'KQ_REPORT_EMAIL'
$title = "forecast-lab daily: $overall -- $settled settled trades"

$logDir = Join-Path $repo 'logs'
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
Add-Content -Path (Join-Path $logDir 'health.log') -Value "daily-report: $title" -Encoding utf8

# 1. ntfy push (no Email header -- see module header for why).
# The multiline body goes via a temp file + --data-binary: PowerShell 5.1
# cannot pass argv containing newlines to a native exe intact (the command
# line fragments and curl sees body lines as extra URLs -> "Bad hostname").
if ($topic) {
    $bodyFile = Join-Path $env:TEMP 'kq-daily-report-body.txt'
    Set-Content -Path $bodyFile -Value $body -Encoding utf8 -NoNewline
    & curl.exe -fsS -m 20 -H "Title: $title" -H 'Tags: bar_chart' `
        --data-binary "@$bodyFile" "https://ntfy.sh/$topic" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Add-Content -Path (Join-Path $logDir 'health.log') -Value 'daily-report: ntfy push failed' -Encoding utf8
    }
    Remove-Item $bodyFile -Force -ErrorAction SilentlyContinue
}
else {
    Write-Output 'daily-report: NTFY_TOPIC not set; skipping push'
}

# 2. Real email, only when SMTP creds are configured.
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
        Add-Content -Path (Join-Path $logDir 'health.log') -Value "daily-report: email sent to $email" -Encoding utf8
    }
    catch {
        Add-Content -Path (Join-Path $logDir 'health.log') -Value "daily-report: email send failed: $($_.Exception.Message)" -Encoding utf8
    }
}
exit 0
