#!/usr/bin/env sh
# ============================================================
#  forecast-lab one-command installer (Mac / Linux / WSL)
#  Run:  ./install.sh
#  It installs the package manager (uv) if needed, downloads
#  the project's dependencies, then walks you through setup.
# ============================================================
set -e
cd "$(dirname "$0")"

if ! command -v uv >/dev/null 2>&1; then
    echo "Installing the package manager (uv) — one time only..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Put uv on PATH for the rest of this script.
    export PATH="$HOME/.local/bin:$PATH"
fi

echo "Downloading project dependencies..."
uv sync

uv run python -m kq setup
echo
echo "To open the app later, run:  uv run kq dashboard"
