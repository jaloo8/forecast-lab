"""Typed runtime settings. Source of truth: `.env` (+ real OS env)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """All runtime configuration. Read from `.env` by default."""

    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    # ---- Kalshi ----
    kalshi_api_key_id: str = ""
    kalshi_private_key_path: Path = REPO_ROOT / "secrets" / "kalshi.pem"
    kalshi_env: Literal["demo", "prod"] = "demo"

    # ---- Weather ----
    open_meteo_api_key: str = ""
    noaa_user_agent: str = "forecast-lab (set NOAA_USER_AGENT in .env)"

    # ---- Odds / sports ----
    odds_api_key: str = ""
    balldontlie_api_key: str = ""

    # ---- LLM (v2 only; unused in v1) ----
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    voyage_api_key: str = ""

    # ---- Storage ----
    database_url: str = f"duckdb:///{REPO_ROOT / 'data' / 'forecast_lab.duckdb'}"
    sqlite_ops_url: str = f"sqlite:///{REPO_ROOT / 'data' / 'ops.sqlite'}"

    # ---- Runtime ----
    log_level: str = "INFO"
    tz: str = "UTC"
    # Directory the cron jobs write `ingest-*.log` files to. The dashboard
    # tails these for the data-freshness panel. Default is platform-
    # specific via .env; on the always-on Windows box it should be a
    # Tailscale-reachable path (typically `/var/log/cron` under WSL2).
    cron_log_dir: Path = REPO_ROOT / "data" / "cron-logs"

    # ---- Trading safety gates (CLAUDE.md §5) ----
    kq_live: bool = Field(default=False)
    kq_max_position_usd: float = Field(default=200.0, gt=0)
    kq_max_daily_loss_pct: float = Field(default=3.0, gt=0, le=100)
    kq_kelly_fraction: float = Field(default=0.15, gt=0, le=1)

    # ---- v2 agent budget gates ----
    agent_daily_usd_cap: float = Field(default=10.0, ge=0)
    agent_per_run_usd_cap: float = Field(default=2.0, ge=0)
    agent_per_run_max_iter: int = Field(default=20, ge=1)
    agent_per_run_wall_clock_s: int = Field(default=1800, ge=1)

    # ---- Notifications ----
    pushover_user_key: str = ""
    pushover_app_token: str = ""
    ntfy_topic: str = ""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached singleton. Import and call, don't import the instance."""
    return Settings()
