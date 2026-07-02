@echo off
rem ============================================================
rem  forecast-lab one-command installer (Windows)
rem  Double-click this file, or run it in a terminal.
rem  It installs the package manager (uv) if needed, downloads
rem  the project's dependencies, then walks you through setup.
rem ============================================================
setlocal
cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
    echo Installing the package manager ^(uv^) — one time only...
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
)

echo Downloading project dependencies...
uv sync
if errorlevel 1 (
    echo.
    echo Something went wrong downloading dependencies. Check your
    echo internet connection and run this installer again.
    pause
    exit /b 1
)

uv run python -m kq setup
echo.
echo To open the app later, run:  uv run kq dashboard
pause
