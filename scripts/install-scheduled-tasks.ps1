<#
.SYNOPSIS
    Register the forecast-lab cron schedule as Windows Scheduled Tasks on a
    native-Windows 24/7 host (no WSL, no cron).

.DESCRIPTION
    Reproduces the 17 jobs that ran in the WSL2 crontab. Idempotent: every task
    is registered with -Force, so re-running updates in place. Nothing is
    removed except by -Uninstall.

    ------------------------------------------------------------------------
    TIMEZONE: the whole point of this script
    ------------------------------------------------------------------------
    The crontab ran in UTC. Windows Task Scheduler triggers fire in the
    machine's LOCAL wall-clock time. Every schedule below is therefore stored
    as its original UTC time-of-day and converted at install time by building
    a real UTC [datetime] and calling .ToLocalTime() -- never by subtracting a
    hardcoded offset. That also means weekly jobs can land on a DIFFERENT
    WEEKDAY locally (Sun 02:00 UTC is Sat 19:00 in Pacific daylight time), and
    the script computes that shift rather than assuming it away. A UTC -> local
    table is printed on every run; read it.

    ------------------------------------------------------------------------
    DST CAVEAT -- READ THIS, IT IS THE KNOWN SHARP EDGE
    ------------------------------------------------------------------------
    Task Scheduler keeps LOCAL wall-clock time. Conversion happens once, here,
    at install time. After each daylight-saving transition every task still
    fires at the same local time, which means it fires ONE HOUR EARLIER OR
    LATER IN UTC than the cron job it replaced.

    Re-run this installer after every DST change to re-align to UTC.

    The pollers (metar / weather / ndfd / kalshi / odds) do not care -- a one
    hour drift on a 15-minute or 6-hourly poll is noise. The ones that matter
    are the paper-trading windows, because they are pinned to when Kalshi
    markets open and settle:

        kq-paper-submit      14:30 UTC
        kq-paper-settle      16:00 UTC
        kq-paper-nba-settle  12:30 UTC

    If those drift an hour they can submit before markets are quotable or
    settle before results post. US DST changes are the second Sunday in March
    and the first Sunday in November; put a reminder on both.

.PARAMETER RepoPath
    Repo root on the host. Must contain scripts\kq-job.cmd.

.PARAMETER UvPath
    Full path to uv.exe. Jobs run `uv run python -m kq <subcommand>`.

.PARAMETER TaskFolder
    Task Scheduler folder to create the tasks under. Single level.

.PARAMETER RunAsUser
    Account the tasks run as. Registered with LogonType S4U, i.e. "run whether
    the user is logged on or not" without this script ever handling a password.

.PARAMETER DryRun
    Print the full plan -- UTC -> local table, task names, actions, triggers --
    and register nothing. Equivalent to -WhatIf, which is also supported.

.PARAMETER Uninstall
    Unregister every task in -TaskFolder and delete the folder. Reversible exit.

.PARAMETER WithBashJobs
    Opt in to registering the three bash-based jobs (backup / health / rotate).
    Off by default: those scripts hardcode the Linux layout ($HOME/forecast-lab,
    $HOME/.local/bin/uv) and will fail every run on a Windows host until they
    are ported. See the report the script prints at the end.

.PARAMETER BashPath
    Explicit bash.exe to use with -WithBashJobs. Auto-detected if omitted.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\install-scheduled-tasks.ps1 -DryRun

.EXAMPLE
    # elevated
    .\scripts\install-scheduled-tasks.ps1 -RepoPath C:\Users\jloo1\Documents\forecast-lab

.EXAMPLE
    .\scripts\install-scheduled-tasks.ps1 -Uninstall

.NOTES
    Windows PowerShell 5.1 compatible: no ternary, no null-coalescing, no
    pwsh-only syntax. Registration requires an elevated shell.
#>
#Requires -Version 5.1
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$RepoPath   = 'C:\Users\jloo1\Documents\forecast-lab',
    [string]$UvPath     = 'C:\Users\jloo1\.local\bin\uv.exe',
    [string]$TaskFolder = '\forecast-lab',
    # On a workgroup (non-domain) machine $env:USERDOMAIN is literally
    # "WORKGROUP", which is not a security authority: Register-ScheduledTask
    # then fails with 0x80070534 "No mapping between account names and
    # security IDs was done". Fall back to COMPUTERNAME\USERNAME, which
    # resolves on both workgroup and domain hosts.
    [string]$RunAsUser  = $(
        if ($env:USERDOMAIN -and $env:USERDOMAIN -ne 'WORKGROUP') {
            "$env:USERDOMAIN\$env:USERNAME"
        } else {
            "$env:COMPUTERNAME\$env:USERNAME"
        }
    ),
    [switch]$DryRun,
    [switch]$Uninstall,
    [switch]$WithBashJobs,
    [string]$BashPath
)

$ErrorActionPreference = 'Stop'

if ($DryRun) { $WhatIfPreference = $true }
# Belt and braces: -DryRun must never reach Register-ScheduledTask even if the
# ShouldProcess plumbing behaves differently on some host.
$isPlanOnly = ($DryRun -or $WhatIfPreference)

# Load the task modules with WhatIf forced off. Auto-loading them later while
# $WhatIfPreference is $true makes their internal Set-Alias calls emit a dozen
# bogus "What if: Performing the operation Set Alias" lines into the plan.
$savedWhatIf = $WhatIfPreference
$WhatIfPreference = $false
Import-Module CimCmdlets -ErrorAction SilentlyContinue
Import-Module ScheduledTasks -ErrorAction SilentlyContinue
$WhatIfPreference = $savedWhatIf

$folderLeaf = $TaskFolder.Trim('\')
if ([string]::IsNullOrWhiteSpace($folderLeaf)) {
    throw "-TaskFolder must name a folder, e.g. '\forecast-lab'."
}
if ($folderLeaf -match '\\') {
    throw "-TaskFolder must be a single level (got '$TaskFolder')."
}
$taskPath = '\' + $folderLeaf + '\'

# ---------------------------------------------------------------------------
# The schedule. Utc is the cron time-of-day in UTC and is the single source of
# truth; local times are derived, never stored.
#   Repeat -> cron "*/N" or "M */H": anchor time-of-day + repetition interval
#   Daily  -> cron "M H * * *"
#   Weekly -> cron "M H * * D"
#   Shell  -> bash script, not a kq subcommand
# ---------------------------------------------------------------------------
$Jobs = @(
    @{ Name = 'kq-ingest-weather';            Cron = '5 */6 * * *';  Utc = '00:05'; Kind = 'Repeat'; EveryMinutes = 360; KqArgs = @('ingest-weather') }
    @{ Name = 'kq-ingest-metar';              Cron = '*/15 * * * *'; Utc = '00:00'; Kind = 'Repeat'; EveryMinutes = 15;  KqArgs = @('ingest-metar') }
    @{ Name = 'kq-ingest-ndfd';               Cron = '20 */6 * * *'; Utc = '00:20'; Kind = 'Repeat'; EveryMinutes = 360; KqArgs = @('ingest-ndfd') }
    # 15-min book snapshots (was hourly): prediction markets move continuously,
    # and denser snapshots sharpen CLV measurement. Offset to :07 so this
    # WRITER never launches on the :00/:15/:30/:45 grid with metar (DuckDB is
    # single-writer) nor on the :05/:35 heartbeat reads.
    @{ Name = 'kq-ingest-kalshi';             Cron = '7,22,37,52 * * * *'; Utc = '00:07'; Kind = 'Repeat'; EveryMinutes = 15; KqArgs = @('ingest-kalshi') }
    @{ Name = 'kq-ingest-nba-schedule';       Cron = '0 11 * * *';   Utc = '11:00'; Kind = 'Daily';                      KqArgs = @('ingest-nba-schedule') }
    @{ Name = 'kq-ingest-nba-odds';           Cron = '30 */6 * * *'; Utc = '00:30'; Kind = 'Repeat'; EveryMinutes = 360; KqArgs = @('ingest-nba-odds') }
    @{ Name = 'kq-build-nba-crosswalk';       Cron = '30 11 * * *';  Utc = '11:30'; Kind = 'Daily';                      KqArgs = @('build-nba-crosswalk') }
    @{ Name = 'kq-paper-nba-settle';          Cron = '30 12 * * *';  Utc = '12:30'; Kind = 'Daily';                      KqArgs = @('paper-nba', '--settle-only') }
    @{ Name = 'kq-paper-submit';              Cron = '30 14 * * *';  Utc = '14:30'; Kind = 'Daily';                      KqArgs = @('paper') }
    @{ Name = 'kq-paper-settle';              Cron = '0 16 * * *';   Utc = '16:00'; Kind = 'Daily';                      KqArgs = @('paper', '--settle-only') }
    @{ Name = 'kq-backtest-weather-v1';       Cron = '0 2 * * 0';    Utc = '02:00'; Kind = 'Weekly'; Dow = 'Sunday';     KqArgs = @('backtest', '--strategy', 'weather_v1') }
    @{ Name = 'kq-backtest-weather-router';   Cron = '30 2 * * 0';   Utc = '02:30'; Kind = 'Weekly'; Dow = 'Sunday';     KqArgs = @('backtest', '--strategy', 'weather_router_v1') }
    @{ Name = 'kq-backtest-weather-all-raw';  Cron = '0 3 * * 0';    Utc = '03:00'; Kind = 'Weekly'; Dow = 'Sunday';     KqArgs = @('backtest', '--strategy', 'weather_all_raw_v1') }
    @{ Name = 'kq-decide-router';             Cron = '0 4 * * 0';    Utc = '04:00'; Kind = 'Weekly'; Dow = 'Sunday';     KqArgs = @('decide-router') }
    @{ Name = 'kq-backup-duckdb';             Cron = '50 9 * * *';   Utc = '09:50'; Kind = 'Daily';                      Shell = 'scripts\backup-duckdb.sh' }
    @{ Name = 'kq-cron-health';               Cron = '*/30 * * * *'; Utc = '00:00'; Kind = 'Repeat'; EveryMinutes = 30;  Shell = 'scripts\cron-health.sh' }
    @{ Name = 'kq-rotate-logs';               Cron = '10 0 * * *';   Utc = '00:10'; Kind = 'Daily';                      Shell = 'scripts\rotate-logs.sh' }
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

function Test-JobIsShell {
    param([hashtable]$Job)
    return $Job.ContainsKey('Shell')
}

function ConvertTo-LocalFromUtcTimeOfDay {
    <#
      Build a genuine UTC instant for the given time-of-day (on the next
      occurrence of $Dow when the job is weekly) and let .NET convert it. This
      is what makes the weekday shift and any non-whole-hour offset fall out
      correctly instead of being assumed away.
    #>
    param(
        [Parameter(Mandatory = $true)][int]$Hour,
        [Parameter(Mandatory = $true)][int]$Minute,
        [string]$Dow
    )
    $day = [datetime]::UtcNow.Date
    if ($PSBoundParameters.ContainsKey('Dow') -and -not [string]::IsNullOrEmpty($Dow)) {
        $target = [System.DayOfWeek]$Dow
        while ($day.DayOfWeek -ne $target) { $day = $day.AddDays(1) }
    }
    $utc = [datetime]::SpecifyKind(
        $day.AddHours($Hour).AddMinutes($Minute), [System.DateTimeKind]::Utc)
    return $utc.ToLocalTime()
}

function Get-JobLocalTime {
    param([hashtable]$Job)
    $parts  = $Job.Utc -split ':'
    $hour   = [int]$parts[0]
    $minute = [int]$parts[1]
    if ($Job.Kind -eq 'Weekly') {
        return ConvertTo-LocalFromUtcTimeOfDay -Hour $hour -Minute $minute -Dow $Job.Dow
    }
    return ConvertTo-LocalFromUtcTimeOfDay -Hour $hour -Minute $minute
}

function Get-JobStartBoundary {
    <#
      Push the converted local time forward to the next future occurrence so no
      task is registered with a start boundary in the past. For repeating jobs
      we advance by whole intervals, which preserves the minute-of-hour grid
      (:00/:15/:30/:45) that cron had.
    #>
    param([hashtable]$Job, [datetime]$LocalTime)
    $now  = Get-Date
    $when = $LocalTime
    if ($Job.Kind -eq 'Repeat') {
        $step = [double]$Job.EveryMinutes
        if ($step -le 0) { throw "$($Job.Name): EveryMinutes must be > 0." }
        while ($when -le $now) { $when = $when.AddMinutes($step) }
    }
    elseif ($Job.Kind -eq 'Weekly') {
        while ($when -le $now) { $when = $when.AddDays(7) }
    }
    else {
        while ($when -le $now) { $when = $when.AddDays(1) }
    }
    return $when
}

function New-RepeatingTrigger {
    <#
      "Every N minutes, forever." The trap here is a repetition Duration of one
      day, which silently stops the task after 24h. An absent <Duration> element
      is what Task Scheduler renders as "Repeat ... indefinitely", so the CIM
      path below leaves Duration unset. The [TimeSpan]::MaxValue form is the
      documented fallback; it is known to trip an XML range error on some
      builds, hence the ordering.
    #>
    param([datetime]$At, [int]$IntervalMinutes)

    $iso = 'PT{0}M' -f $IntervalMinutes
    $reason = ''
    try {
        $trigger = New-ScheduledTaskTrigger -Once -At $At
        $repetition = New-CimInstance `
            -ClassName 'MSFT_TaskRepetitionPattern' `
            -Namespace 'Root/Microsoft/Windows/TaskScheduler' `
            -ClientOnly `
            -Property @{ Interval = $iso; StopAtDurationEnd = $false }
        $trigger.Repetition = $repetition
        if ($trigger.Repetition -and ($trigger.Repetition.Interval -eq $iso)) {
            return $trigger
        }
        $reason = 'the assignment did not stick'
    }
    catch {
        $reason = $_.Exception.Message
    }

    $msg = 'Indefinite-repetition CIM path failed ({0}); falling back to TimeSpan::MaxValue. Check the RepeatFor column in the verification table below.' -f $reason
    Write-Warning $msg
    return New-ScheduledTaskTrigger -Once -At $At `
        -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
        -RepetitionDuration ([TimeSpan]::MaxValue)
}

function New-TriggerForJob {
    param([hashtable]$Job, [datetime]$At)
    switch ($Job.Kind) {
        'Repeat' { return New-RepeatingTrigger -At $At -IntervalMinutes $Job.EveryMinutes }
        'Daily'  { return New-ScheduledTaskTrigger -Daily -At $At }
        'Weekly' { return New-ScheduledTaskTrigger -Weekly -DaysOfWeek $At.DayOfWeek -At $At }
        default  { throw "$($Job.Name): unknown Kind '$($Job.Kind)'." }
    }
}

function Get-ScheduleText {
    param([hashtable]$Job, [datetime]$LocalTime)
    switch ($Job.Kind) {
        'Repeat' { return ('every {0} min from {1}' -f $Job.EveryMinutes, $LocalTime.ToString('HH:mm')) }
        'Daily'  { return ('daily {0}' -f $LocalTime.ToString('HH:mm')) }
        'Weekly' { return ('weekly {0} {1}' -f $LocalTime.DayOfWeek, $LocalTime.ToString('HH:mm')) }
        default  { return '?' }
    }
}

function Test-IsElevated {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $pr = New-Object Security.Principal.WindowsPrincipal($id)
    return $pr.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Resolve-BashPath {
    param([string]$Explicit)
    if (-not [string]::IsNullOrWhiteSpace($Explicit)) {
        if (Test-Path -LiteralPath $Explicit) { return $Explicit }
        return $null
    }
    $cmd = Get-Command 'bash.exe' -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidates = @(
        "$env:ProgramFiles\Git\bin\bash.exe",
        "${env:ProgramFiles(x86)}\Git\bin\bash.exe",
        "$env:LOCALAPPDATA\Programs\Git\bin\bash.exe"
    )
    foreach ($c in $candidates) {
        if (-not [string]::IsNullOrWhiteSpace($c) -and (Test-Path -LiteralPath $c)) { return $c }
    }
    return $null
}

function Write-Heading {
    param([string]$Text)
    Write-Host ''
    Write-Host ('=' * 78) -ForegroundColor DarkGray
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ('=' * 78) -ForegroundColor DarkGray
}

# ---------------------------------------------------------------------------
# Uninstall
# ---------------------------------------------------------------------------
if ($Uninstall) {
    Write-Heading "Uninstall: removing every task under $taskPath"

    $existing = @(Get-ScheduledTask -TaskPath $taskPath -ErrorAction SilentlyContinue)
    if ($existing.Count -eq 0) {
        Write-Host "No tasks found under $taskPath -- nothing to remove." -ForegroundColor Yellow
    }
    foreach ($task in $existing) {
        if ((-not $isPlanOnly) -and $PSCmdlet.ShouldProcess($task.TaskName, 'Unregister-ScheduledTask')) {
            Unregister-ScheduledTask -TaskPath $taskPath -TaskName $task.TaskName -Confirm:$false
            Write-Host ("  removed  {0}" -f $task.TaskName)
        }
        else {
            Write-Host ("  WOULD REMOVE  {0}" -f $task.TaskName)
        }
    }

    if ((-not $isPlanOnly) -and $PSCmdlet.ShouldProcess($taskPath, 'Delete task folder')) {
        try {
            $svc = New-Object -ComObject 'Schedule.Service'
            $svc.Connect()
            $svc.GetFolder('\').DeleteFolder($folderLeaf, 0)
            Write-Host ("  removed folder {0}" -f $taskPath)
        }
        catch {
            Write-Warning ("Could not delete folder {0}: {1}" -f $taskPath, $_.Exception.Message)
        }
    }
    else {
        Write-Host ("  WOULD REMOVE folder {0}" -f $taskPath)
    }

    Write-Host ''
    Write-Host 'Uninstall complete.' -ForegroundColor Green
    return
}

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------
Write-Heading 'forecast-lab -- Windows Scheduled Tasks installer'

$wrapper  = Join-Path $RepoPath 'scripts\kq-job.cmd'
$problems = @()

if (-not (Test-Path -LiteralPath $RepoPath))  { $problems += "RepoPath not found: $RepoPath" }
if (-not (Test-Path -LiteralPath $wrapper))   { $problems += "Wrapper not found: $wrapper" }
if (-not (Test-Path -LiteralPath $UvPath))    { $problems += "uv.exe not found: $UvPath" }
if (-not (Test-IsElevated))                   { $problems += 'Not running elevated (Register-ScheduledTask needs Administrator).' }

$tz     = [System.TimeZoneInfo]::Local
$now    = Get-Date
$offset = $tz.GetUtcOffset($now)

Write-Host ("Repo        : {0}" -f $RepoPath)
Write-Host ("uv          : {0}" -f $UvPath)
Write-Host ("Wrapper     : {0}" -f $wrapper)
Write-Host ("Task folder : {0}" -f $taskPath)
Write-Host ("Run as      : {0}  (LogonType S4U -- runs logged on or not)" -f $RunAsUser)
Write-Host ("Time zone   : {0}  (UTC{1}{2:hh\:mm} right now; DST in effect: {3})" -f `
    $tz.Id, $(if ($offset.Ticks -lt 0) { '-' } else { '+' }), $offset.Duration(), $tz.IsDaylightSavingTime($now))
Write-Host ("Mode        : {0}" -f $(if ($isPlanOnly) { 'DRY RUN -- nothing will be registered' } else { 'REGISTER' }))

if ($problems.Count -gt 0) {
    Write-Host ''
    foreach ($p in $problems) { Write-Warning $p }
    if (-not $isPlanOnly) {
        throw 'Preflight failed. Fix the warnings above, or re-run with -DryRun to inspect the plan.'
    }
    Write-Host 'Dry run: continuing despite the warnings above.' -ForegroundColor Yellow
}

# ---------------------------------------------------------------------------
# Plan: UTC -> local for every job
# ---------------------------------------------------------------------------
$bash        = Resolve-BashPath -Explicit $BashPath
$plan        = @()
$skippedShell = @()

foreach ($job in $Jobs) {
    $local = Get-JobLocalTime -Job $job
    $start = Get-JobStartBoundary -Job $job -LocalTime $local

    if (Test-JobIsShell -Job $job) {
        $command = $job.Shell + '  (bash)'
    }
    else {
        $command = 'kq ' + ($job.KqArgs -join ' ')
    }

    $utcLabel = $job.Utc
    if ($job.Kind -eq 'Weekly') { $utcLabel = ('{0} {1}' -f $job.Dow, $job.Utc) }

    $plan += [pscustomobject]@{
        Task      = $job.Name
        CronUTC   = $job.Cron
        UTC       = $utcLabel
        Local     = Get-ScheduleText -Job $job -LocalTime $local
        FirstRun  = $start.ToString('yyyy-MM-dd HH:mm')
        Command   = $command
        _job      = $job
        _start    = $start
    }
}

Write-Heading 'Schedule translation: cron (UTC) -> Task Scheduler (local wall clock)'
$plan | Format-Table Task, CronUTC, UTC, Local, FirstRun, Command -AutoSize | Out-String -Width 200 | Write-Host

Write-Host 'Reminder: these are LOCAL times. After a DST change every one of them' -ForegroundColor Yellow
Write-Host 'moves an hour in UTC terms. Re-run this installer to re-align.' -ForegroundColor Yellow

# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId $RunAsUser -LogonType S4U -RunLevel Limited

Write-Heading 'Registering tasks'

$registered = @()

foreach ($row in $plan) {
    $job = $row._job

    if (Test-JobIsShell -Job $job) {
        if (-not $WithBashJobs) {
            $skippedShell += $job
            Write-Host ("  SKIP      {0}  ({1} -- see the report below)" -f $job.Name, $job.Shell) -ForegroundColor Yellow
            continue
        }
        if (-not $bash) {
            $skippedShell += $job
            Write-Host ("  SKIP      {0}  (-WithBashJobs given but no bash.exe found)" -f $job.Name) -ForegroundColor Yellow
            continue
        }
        $scriptFull = Join-Path $RepoPath $job.Shell
        $action = New-ScheduledTaskAction -Execute $bash `
            -Argument ('"{0}"' -f $scriptFull) -WorkingDirectory $RepoPath
    }
    else {
        $argLine = '"{0}" {1}' -f $UvPath, ($job.KqArgs -join ' ')
        $action = New-ScheduledTaskAction -Execute $wrapper `
            -Argument $argLine -WorkingDirectory $RepoPath
    }

    $trigger = New-TriggerForJob -Job $job -At $row._start

    $description = 'forecast-lab: was cron "{0}" (UTC) in the WSL2 crontab. Converted to local at install time; re-run scripts\install-scheduled-tasks.ps1 after a DST change.' -f $job.Cron

    if ((-not $isPlanOnly) -and $PSCmdlet.ShouldProcess(($taskPath + $job.Name), 'Register-ScheduledTask')) {
        Register-ScheduledTask -TaskName $job.Name -TaskPath $taskPath `
            -Action $action -Trigger $trigger -Settings $settings `
            -Principal $principal -Description $description -Force | Out-Null
        Write-Host ("  OK        {0}" -f $job.Name) -ForegroundColor Green
        $registered += $job.Name
    }
    else {
        Write-Host ("  WOULD ADD {0}" -f $job.Name)
        Write-Host ("              execute : {0}" -f $action.Execute)
        Write-Host ("              argument: {0}" -f $action.Arguments)
        Write-Host ("              trigger : {0} @ {1}" -f $job.Kind, $row._start.ToString('yyyy-MM-dd HH:mm'))
    }
}

# ---------------------------------------------------------------------------
# Read back what the scheduler actually stored. This script cannot be tested
# against a real host from a dev box, so the registered state is printed rather
# than assumed -- especially the repetition Duration, where blank == indefinite.
# ---------------------------------------------------------------------------
if ($registered.Count -gt 0) {
    Write-Heading 'Verification: what Task Scheduler actually stored'
    $verify = @()
    foreach ($name in $registered) {
        $task = Get-ScheduledTask -TaskPath $taskPath -TaskName $name
        $info = Get-ScheduledTaskInfo -TaskPath $taskPath -TaskName $name
        $interval = ''
        $duration = ''
        $trg = @($task.Triggers)[0]
        if ($trg -and $trg.Repetition) {
            $interval = [string]$trg.Repetition.Interval
            $duration = [string]$trg.Repetition.Duration
        }
        $durationText = $duration
        if ([string]::IsNullOrEmpty($duration)) { $durationText = '(indefinite)' }
        if ([string]::IsNullOrEmpty($interval)) { $durationText = '' }

        $verify += [pscustomobject]@{
            Task     = $name
            State    = $task.State
            NextRun  = $info.NextRunTime
            Repeat   = $interval
            RepeatFor = $durationText
        }
    }
    $verify | Format-Table -AutoSize | Out-String -Width 200 | Write-Host
    Write-Host 'RepeatFor must read "(indefinite)" for every repeating task. If any of' -ForegroundColor Yellow
    Write-Host 'them shows a finite duration (e.g. P1D) the job will stop after that'   -ForegroundColor Yellow
    Write-Host 'window -- fix it in Task Scheduler and tell the maintainer.'            -ForegroundColor Yellow
}

# ---------------------------------------------------------------------------
# The three bash jobs: explicit report, never a silent failure
# ---------------------------------------------------------------------------
Write-Heading 'NOT SCHEDULED: the three bash jobs (backup / health / rotate)'

if ($bash) {
    Write-Host ("bash.exe found at: {0}" -f $bash)
    if ($bash -like "$env:SystemRoot\System32\*" -or $bash -like "$env:SystemRoot\Sysnative\*") {
        Write-Host ''
        Write-Host 'CAUTION: that is the WSL launcher shim, not Git Bash. Running the scripts' -ForegroundColor Red
        Write-Host 'through it would execute them INSIDE a WSL distro -- a different filesystem,' -ForegroundColor Red
        Write-Host 'a different uv, and a different DuckDB than the Windows tasks above use.'    -ForegroundColor Red
        Write-Host 'Backups written there would NOT be backups of this host database. Pass an'   -ForegroundColor Red
        Write-Host 'explicit -BashPath to Git Bash if you really mean to use -WithBashJobs.'     -ForegroundColor Red
    }
}
else {
    Write-Host 'bash.exe: NOT FOUND on this host.'
}
Write-Host ''
Write-Host 'These three cron entries are shell scripts, not kq subcommands:'
Write-Host ''
Write-Host '  50 9 * * *    scripts/backup-duckdb.sh    nightly DuckDB backup + rotation'
Write-Host '  */30 * * * *  scripts/cron-health.sh      health-check heartbeat, ntfy push on CRIT'
Write-Host '  10 0 * * *    scripts/rotate-logs.sh      daily log rotation (copytruncate, keep 14)'
Write-Host ''
Write-Host 'They are skipped by default even when bash exists, because they hardcode' -ForegroundColor Yellow
Write-Host 'the Linux layout -- REPO="$HOME/forecast-lab" and UV="$HOME/.local/bin/uv"' -ForegroundColor Yellow
Write-Host 'which do not resolve on this host. Registering them would create three'    -ForegroundColor Yellow
Write-Host 'tasks that fail on every single run.'                                      -ForegroundColor Yellow
Write-Host ''
Write-Host 'TODO for the operator -- pick one per job:'
Write-Host '  1. Port the scripts to honour a KQ_REPO / KQ_UV override (or a .cmd'
Write-Host '     equivalent), then re-run this installer with -WithBashJobs.'
Write-Host '  2. Health: until then the host has NO heartbeat and NO ntfy alerting.'
Write-Host '     `uv run python -m kq health-check --json` is the native half; the'
Write-Host '     ntfy push on CRIT lives in cron-health.sh and has no Windows path yet.'
Write-Host '  3. Backup: until then the DuckDB file is UNBACKED UP on this host. This'
Write-Host '     is the highest-consequence gap of the three.'
Write-Host '  4. Rotate: logs\cron.log grows without bound. Low urgency, but real.'
Write-Host ''
Write-Host 'Do not assume these are running just because the kq tasks are.' -ForegroundColor Yellow

# ---------------------------------------------------------------------------
Write-Heading 'Summary'

$kqCount = @($Jobs | Where-Object { -not (Test-JobIsShell -Job $_) }).Count
Write-Host ("kq tasks in the plan   : {0}" -f $kqCount)
Write-Host ("Registered this run    : {0}" -f $registered.Count)
Write-Host ("Shell jobs not scheduled: {0}" -f @($skippedShell).Count)
Write-Host ''
Write-Host 'Next steps:'
Write-Host ("  Inspect : Get-ScheduledTask -TaskPath '{0}' | Format-Table TaskName,State" -f $taskPath)
Write-Host ("  Next run: Get-ScheduledTask -TaskPath '{0}' | Get-ScheduledTaskInfo | Format-Table TaskName,LastRunTime,LastTaskResult,NextRunTime" -f $taskPath)
Write-Host ("  Smoke   : Start-ScheduledTask -TaskPath '{0}' -TaskName kq-ingest-metar   # then tail logs\cron.log" -f $taskPath)
Write-Host ("  Remove  : .\scripts\install-scheduled-tasks.ps1 -Uninstall")
if ($isPlanOnly) {
    Write-Host ''
    Write-Host 'DRY RUN -- nothing was registered. Re-run elevated without -DryRun to apply.' -ForegroundColor Yellow
}
