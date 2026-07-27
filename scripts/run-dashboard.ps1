# Launcher for the Streamlit dashboard as a Scheduled Task. Exists because a
# cmd.exe /c action whose command line STARTS with a quoted path trips cmd's
# quote-stripping rule and the task dies instantly with no log; starting with
# `powershell -File <this>` sidesteps that entirely.
#   KQ_DASH_ADDR / KQ_DASH_PORT override the bind (default: Tailscale IP :8501).
$ErrorActionPreference = 'Stop'

$repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$uv = if ($env:KQ_UV) { $env:KQ_UV } else { Join-Path $env:USERPROFILE '.local\bin\uv.exe' }
$addr = if ($env:KQ_DASH_ADDR) { $env:KQ_DASH_ADDR } else { '100.108.199.57' }
$port = if ($env:KQ_DASH_PORT) { $env:KQ_DASH_PORT } else { '8501' }
$log = Join-Path $repo 'logs\dashboard.log'

Set-Location $repo
if (-not (Test-Path (Split-Path $log))) { New-Item -ItemType Directory -Path (Split-Path $log) -Force | Out-Null }
Add-Content -Path $log -Value ("=== {0} launching dashboard on {1}:{2}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $addr, $port)

# *>> appends every stream; this blocks for the life of the server (the task
# stays 'Running', which is exactly what we want for a service).
& $uv run streamlit run src\kq\dashboard\streamlit_app.py `
    --server.headless true --server.address $addr --server.port $port *>> $log
exit $LASTEXITCODE
