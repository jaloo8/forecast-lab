<#
.SYNOPSIS
Registers the native-Windows ops safety net + dashboard service that
install-scheduled-tasks.ps1 deliberately skips (its bash originals).

Registers under the same task folder, principal, and settings conventions:
  kq-backup-duckdb   daily, cron parity 09:50 UTC  -> scripts\backup-duckdb.ps1
  kq-cron-health     every 30 min                  -> scripts\cron-health.ps1
  kq-rotate-logs     daily, cron parity 00:10 UTC  -> scripts\rotate-logs.ps1
  kq-dashboard       at boot + kept alive          -> streamlit on -DashboardAddr:8501

Same DST caveat as the main installer: triggers are LOCAL wall clock; after a
DST change the UTC firing time shifts an hour. Re-run to re-align.

.PARAMETER DashboardAddr
Bind address for Streamlit. Default is the a8 Tailscale IP so the dashboard is
reachable from the tailnet (any of your machines/phone) but NOT the open LAN.
A scoped inbound firewall rule for the port is created (idempotent).
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$RepoPath      = 'C:\Users\jloo1\Documents\forecast-lab',
    [string]$UvPath        = 'C:\Users\jloo1\.local\bin\uv.exe',
    [string]$TaskFolder    = '\forecast-lab',
    [string]$DashboardAddr = '100.108.199.57',
    [int]$DashboardPort    = 8501,
    [string]$RunAsUser     = $(
        if ($env:USERDOMAIN -and $env:USERDOMAIN -ne 'WORKGROUP') {
            "$env:USERDOMAIN\$env:USERNAME"
        } else {
            "$env:COMPUTERNAME\$env:USERNAME"
        }
    ),
    [switch]$DryRun,
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'
$taskPath = $TaskFolder.TrimEnd('\') + '\'
$log = Join-Path $RepoPath 'logs\cron.log'

function ConvertTo-LocalFromUtcTimeOfDay([int]$H, [int]$M) {
    $todayUtc = [datetime]::UtcNow.Date
    $utc = [datetime]::SpecifyKind($todayUtc.AddHours($H).AddMinutes($M), 'Utc')
    return $utc.ToLocalTime()
}

# kq-daily-report is the retired once-a-day predecessor of kq-status-report;
# it stays in this list so -Uninstall also cleans up older installs.
$names = @('kq-backup-duckdb', 'kq-cron-health', 'kq-rotate-logs', 'kq-dashboard', 'kq-status-report', 'kq-daily-report')

if ($Uninstall) {
    foreach ($n in $names) {
        $t = Get-ScheduledTask -TaskPath $taskPath -TaskName $n -ErrorAction SilentlyContinue
        if ($t) {
            if (-not $DryRun) { Unregister-ScheduledTask -TaskPath $taskPath -TaskName $n -Confirm:$false }
            Write-Host "removed $n"
        }
    }
    exit 0
}

if (-not (Test-Path $RepoPath)) { throw "RepoPath not found: $RepoPath" }
if (-not (Test-Path $UvPath)) { throw "UvPath not found: $UvPath" }

$principal = New-ScheduledTaskPrincipal -UserId $RunAsUser -LogonType S4U -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 2) `
    -ExecutionTimeLimit (New-TimeSpan -Hours 12) -MultipleInstances IgnoreNew

function Register-OpsTask([string]$Name, $Trigger, [string]$CmdLine, [string]$Desc, $TaskSettings) {
    if (-not $TaskSettings) { $TaskSettings = $settings }
    $action = New-ScheduledTaskAction -Execute 'cmd.exe' `
        -Argument "/c $CmdLine" -WorkingDirectory $RepoPath
    if ($DryRun) {
        Write-Host "WOULD ADD $Name -> $CmdLine"
        return
    }
    Register-ScheduledTask -TaskName $Name -TaskPath $taskPath -Action $action `
        -Trigger $Trigger -Settings $TaskSettings -Principal $principal -Description $Desc -Force | Out-Null
    Write-Host "REGISTERED $Name"
}

# The dashboard is a long-running SERVICE: the shared 12h ExecutionTimeLimit
# would kill it mid-day. PT0S (zero) disables the limit entirely.
$serviceSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 2) `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -MultipleInstances IgnoreNew

$ps = 'powershell -NoProfile -ExecutionPolicy Bypass -File'

# --- backup: cron parity 50 9 * * * (UTC) ---
$t = ConvertTo-LocalFromUtcTimeOfDay 9 50
Register-OpsTask 'kq-backup-duckdb' (New-ScheduledTaskTrigger -Daily -At $t) `
    "$ps `"$RepoPath\scripts\backup-duckdb.ps1`" >> `"$log`" 2>&1" `
    "forecast-lab: daily DuckDB backup (09:50 UTC parity). LOCAL time; re-run installer after DST."

# --- health heartbeat: cron parity */30 * * * * ---
$anchor = (Get-Date).Date.AddHours((Get-Date).Hour)
$ht = New-ScheduledTaskTrigger -Once -At $anchor -RepetitionInterval (New-TimeSpan -Minutes 30)
Register-OpsTask 'kq-cron-health' $ht `
    "$ps `"$RepoPath\scripts\cron-health.ps1`"" `
    "forecast-lab: health-check heartbeat every 30 min; ntfy push on CRIT only."

# --- log rotation: cron parity 10 0 * * * (UTC) ---
$t = ConvertTo-LocalFromUtcTimeOfDay 0 10
Register-OpsTask 'kq-rotate-logs' (New-ScheduledTaskTrigger -Daily -At $t) `
    "$ps `"$RepoPath\scripts\rotate-logs.ps1`" >> `"$log`" 2>&1" `
    "forecast-lab: daily log rotation (00:10 UTC parity). LOCAL time; re-run installer after DST."

# --- dashboard: at boot, kept alive by RestartCount; reachable over the tailnet ---
# Via run-dashboard.ps1: a cmd /c line that STARTS with a quoted exe path trips
# cmd's quote-stripping rule and the task dies instantly with no log. Starting
# with an unquoted `powershell` avoids it; the launcher owns its own logging.
Register-OpsTask 'kq-dashboard' (New-ScheduledTaskTrigger -AtStartup) `
    "$ps `"$RepoPath\scripts\run-dashboard.ps1`"" `
    "forecast-lab: Streamlit dashboard on http://${DashboardAddr}:$DashboardPort (tailnet). Long-running; restarts on failure." `
    $serviceSettings

# --- status report: every 8h anchored at 00/08/16 LOCAL (prediction markets
# are 24/7; the 08:00 edition still lands after the 07:30 paper-submit).
# Migrate away the retired once-daily task if a previous install left it. ---
$oldDaily = Get-ScheduledTask -TaskPath $taskPath -TaskName 'kq-daily-report' -ErrorAction SilentlyContinue
if ($oldDaily -and -not $DryRun) {
    Unregister-ScheduledTask -TaskPath $taskPath -TaskName 'kq-daily-report' -Confirm:$false
    Write-Host 'migrated: removed retired kq-daily-report (superseded by kq-status-report)'
}
$now = Get-Date
$anchorTimes = @(0, 8, 16) | ForEach-Object { $now.Date.AddHours($_) }
$nextAnchor = $anchorTimes | Where-Object { $_ -gt $now } | Select-Object -First 1
if (-not $nextAnchor) { $nextAnchor = $now.Date.AddDays(1) }
$srTrigger = New-ScheduledTaskTrigger -Once -At $nextAnchor -RepetitionInterval (New-TimeSpan -Hours 8)
Register-OpsTask 'kq-status-report' $srTrigger `
    "$ps `"$RepoPath\scripts\status-report.ps1`" >> `"$log`" 2>&1" `
    "forecast-lab: status report every 8h (00/08/16 local): health, trades since last report, ops. Push via ntfy; email when SMTP creds set in .env."

# Scoped firewall allow so tailnet clients can reach the port (idempotent).
if (-not $DryRun) {
    $ruleName = 'forecast-lab dashboard (TCP 8501)'
    if (-not (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Protocol TCP `
            -LocalPort $DashboardPort -Action Allow | Out-Null
        Write-Host "firewall rule added: $ruleName"
    }
    else { Write-Host "firewall rule already present: $ruleName" }
}

Write-Host 'Done. Start the dashboard now with:'
Write-Host "  Start-ScheduledTask -TaskPath '$taskPath' -TaskName kq-dashboard"
