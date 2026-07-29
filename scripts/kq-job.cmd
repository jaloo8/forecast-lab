@echo off
rem ============================================================================
rem  kq-job.cmd -- Windows Task Scheduler wrapper for one forecast-lab job.
rem
rem  Usage:   kq-job.cmd <path-to-uv.exe> <kq-subcommand> [args...]
rem  Example: kq-job.cmd "C:\Users\jloo1\.local\bin\uv.exe" paper --settle-only
rem
rem  Registered by scripts\install-scheduled-tasks.ps1. Three things the cron
rem  line `cd repo && uv run python -m kq X >> logs/cron.log 2>&1` got for free
rem  that a scheduled-task action does not:
rem
rem    1. No shell. A task action is CreateProcess, so ">> logs\cron.log 2>&1"
rem       cannot live on the action itself.
rem    2. Windows append handles are not shared for write. Two jobs appending
rem       to cron.log in the same instant (the top-of-hour pile-up of
rem       ingest-metar + ingest-kalshi + cron-health) would make one of them
rem       die on redirection with output lost. Each run therefore buffers to a
rem       private file and merges it under a retry loop.
rem    3. Exit codes. The child's code is propagated so Task Scheduler's
rem       "Last Run Result" and restart-on-failure stay meaningful.
rem ============================================================================
setlocal EnableExtensions

rem  ---------------------------------------------------------------------
rem  UTF-8 or the job dies on a character.
rem
rem  A scheduled task inherits the system OEM code page (437 on this host),
rem  NOT UTF-8, and Python then encodes stdout with it. Any kq command that
rem  prints a non-cp437 character -- the "->" arrow U+2192 is all over the
rem  flow output -- raises UnicodeEncodeError and exits non-zero AFTER doing
rem  its real work. Confirmed live on the host 2026-07-27: `kq router-summary`
rem  died with "'charmap' codec can't encode character '→'".
rem
rem  PYTHONUTF8=1 forces UTF-8 mode for stdout/stderr regardless of the
rem  console code page, so log text stays readable and no job can fail for
rem  a cosmetic reason. It changes no file-format or DB behavior.
rem  ---------------------------------------------------------------------
set "PYTHONUTF8=1"

rem  %0 is shifted too by a bare SHIFT, so resolve the repo before shifting.
set "SCRIPTDIR=%~dp0"

if "%~1"=="" (
    echo kq-job: usage: kq-job.cmd ^<uv.exe^> ^<kq-subcommand^> [args...] 1>&2
    exit /b 64
)
set "UV=%~1"
shift

set "KQARGS="
:collect_args
if "%~1"=="" goto args_done
set "KQARGS=%KQARGS% %1"
shift
goto collect_args
:args_done

if "%KQARGS%"=="" (
    echo kq-job: no kq subcommand given 1>&2
    exit /b 64
)

cd /d "%SCRIPTDIR%.."
if errorlevel 1 (
    echo kq-job: cannot enter repo root "%SCRIPTDIR%.." 1>&2
    exit /b 66
)

set "REPO=%CD%"
if not exist "%REPO%\logs" mkdir "%REPO%\logs"
if not exist "%REPO%\logs\.tmp" mkdir "%REPO%\logs\.tmp"
set "LOG=%REPO%\logs\cron.log"
set "TMPLOG=%REPO%\logs\.tmp\job-%RANDOM%-%RANDOM%.log"

> "%TMPLOG%" echo === %DATE% %TIME% local :: kq%KQARGS%
rem  CALL, not a bare invocation: if %UV% is ever a .cmd/.bat shim rather than
rem  uv.exe, a bare call transfers control and never comes back, so the exit
rem  line, the log append and the cleanup below would all be silently skipped.
rem  CALL behaves identically for a real .exe.
call "%UV%" run python -m kq%KQARGS% >> "%TMPLOG%" 2>&1
set "RC=%ERRORLEVEL%"
>> "%TMPLOG%" echo === exit %RC%

rem  The append MUST be wrapped in parentheses and branched on with && / ||.
rem  Verified empirically: a bare `type x >> y` whose redirect fails because
rem  another job holds the log leaves ERRORLEVEL at 0, so an `if errorlevel 1`
rem  check reports success and the run's output is silently discarded. Inside
rem  a parenthesized block the redirection failure does make the block fail,
rem  which && / || observe (and it suppresses the console error too).
set /a TRIES=0
:append
( type "%TMPLOG%" >> "%LOG%" ) 2>nul && goto appended
set /a TRIES+=1
if %TRIES% GEQ 30 goto append_failed
rem  ~1s backoff; TIMEOUT refuses to run with redirected stdin (i.e. under the
rem  scheduler), so PING is the portable sleep here.
>nul ping -n 2 127.0.0.1
goto append

:append_failed
rem  cron.log stayed locked for ~30s. Keep the output rather than drop it;
rem  rotate-logs / the operator can fold these in later.
move /y "%TMPLOG%" "%REPO%\logs\cron-unmerged-%RANDOM%.log" >nul 2>&1
goto finish

:appended
del /q "%TMPLOG%" >nul 2>&1

:finish
exit /b %RC%
