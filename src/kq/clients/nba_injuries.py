"""NBA injury-report parser + typed dataclass.

v1 imports injury data from a CSV file (or any iterable of
dict-shaped rows). The actual scraping / API ingest is deferred until
a data-source decision is made -- options are:

- ``nbainjuries`` PyPI package (scrapes nbainjuries.com): clean API,
  but a new dep gated on CLAUDE.md §9 signoff.
- Official NBA injury-report PDF: stable URL, no dep, but PDF
  parsing is fragile.
- Scraping nba.com / espn.com: TOS-fragile.

The schema + parser layer is designed so any of these can drop in
without changing downstream code. v1 ships the typed parser + the
CSV-import flow so the pipeline is functional today (manual data
entry is acceptable for low-cadence injury data).

CSV input format -- columns required:
    player_id, player_name, team_abbr, status, reason, as_of

``as_of`` parses ISO-8601 (with or without ``Z`` / offset). ``reason``
may be empty. Status is normalized to upper-case and validated
against the canonical set.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from typing import Final

import structlog

log = structlog.get_logger(__name__)

# Canonical status set, in approximate order of severity. Validated at
# parse time so downstream queries can rely on the discrete vocabulary.
INJURY_STATUSES: Final[frozenset[str]] = frozenset(
    {"OUT", "DOUBTFUL", "QUESTIONABLE", "PROBABLE", "AVAILABLE"}
)

# Required CSV columns, in arbitrary order in the file but all must be present.
REQUIRED_COLUMNS: Final[tuple[str, ...]] = (
    "player_id",
    "player_name",
    "team_abbr",
    "status",
    "reason",
    "as_of",
)


@dataclass(frozen=True, slots=True)
class InjuryRow:
    """One injury-report line. Mirrors the ``nba_injury`` table schema
    minus ``fetched_at`` (set by the repository at upsert time)."""

    player_id: str
    player_name: str
    team_abbr: str
    status: str  # one of INJURY_STATUSES
    reason: str | None
    as_of: datetime  # tz-aware preferred; naive interpreted as UTC


def parse_status(raw: str) -> str:
    """Normalize a status string to the canonical upper-case form.

    Tolerates the common variants seen in injury reports:
        'Out'             -> 'OUT'
        'Day-To-Day'      -> 'QUESTIONABLE'  (rare; conservative map)
        'Game Time Decision' -> 'QUESTIONABLE'

    Raises ``ValueError`` on anything we can't map.
    """
    cleaned = raw.strip().upper().replace("-", " ").replace("_", " ")
    direct = cleaned.replace(" ", "")
    if direct in INJURY_STATUSES:
        return direct
    # Common synonyms.
    synonyms = {
        "DAYTODAY": "QUESTIONABLE",
        "GAMETIMEDECISION": "QUESTIONABLE",
        "GTD": "QUESTIONABLE",
        "ACTIVE": "AVAILABLE",
        "CLEARED": "AVAILABLE",
        "NOTAVAILABLE": "OUT",
        "INACTIVE": "OUT",
    }
    if direct in synonyms:
        return synonyms[direct]
    raise ValueError(f"unknown injury status {raw!r}")


def parse_as_of(raw: str) -> datetime:
    """Parse ISO-8601 datetime; fall back to date-only as midnight UTC.

    Tolerates the ``Z`` suffix that some sources emit instead of an
    explicit ``+00:00`` offset.
    """
    text = raw.strip()
    if not text:
        raise ValueError("as_of cannot be empty")
    text = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        # Try date-only -> midnight.
        try:
            parsed = datetime.strptime(text, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError(f"unparseable as_of {raw!r}: {exc}") from exc
    # Naive datetimes (e.g. date-only inputs) get stamped with UTC so
    # downstream comparisons / DB writes have a single tz convention.
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def parse_csv_rows(rows: list[dict[str, str]]) -> list[InjuryRow]:
    """Parse iterable of CSV-style dict rows into typed ``InjuryRow``s.

    Missing required *columns* (a file-level schema problem) raise
    immediately. A malformed *row* — unrecognized status or unparseable
    ``as_of`` — is skipped and counted with a structured
    ``nba_injuries.malformed_row`` warning instead of aborting the whole
    ingest (2026-07-01 audit, Tier 2: one bad row must not discard a
    full report). Only when EVERY row is malformed does the function
    raise, so a systematically-broken export still fails loudly.

    Rows with an empty player_id/player_name/team_abbr remain silently
    skipped (pre-existing tolerant behavior for blank filler lines).
    """
    out: list[InjuryRow] = []
    n_malformed = 0
    for i, raw_row in enumerate(rows):
        missing = [c for c in REQUIRED_COLUMNS if c not in raw_row]
        if missing:
            raise ValueError(
                f"missing required CSV columns: {missing}; got {sorted(raw_row.keys())}"
            )
        player_id = raw_row["player_id"].strip()
        player_name = raw_row["player_name"].strip()
        team_abbr = raw_row["team_abbr"].strip().upper()
        if not (player_id and player_name and team_abbr):
            continue  # incomplete row; silently skip
        try:
            status = parse_status(raw_row["status"])
            as_of = parse_as_of(raw_row["as_of"])
        except ValueError as exc:
            n_malformed += 1
            log.warning(
                "nba_injuries.malformed_row",
                row_index=i,
                player_id=player_id,
                error=str(exc),
            )
            continue
        reason_raw = raw_row.get("reason", "").strip()
        reason: str | None = reason_raw or None
        out.append(
            InjuryRow(
                player_id=player_id,
                player_name=player_name,
                team_abbr=team_abbr,
                status=status,
                reason=reason,
                as_of=as_of,
            )
        )
    if rows and n_malformed == len(rows):
        raise ValueError(
            f"all {n_malformed} rows malformed (unrecognized status or unparseable as_of); "
            "refusing to ingest an empty result from a systematically-broken CSV"
        )
    if n_malformed:
        log.warning(
            "nba_injuries.malformed_rows_skipped",
            n_malformed=n_malformed,
            n_parsed=len(out),
            n_total=len(rows),
        )
    return out


def parse_csv_text(text: str) -> list[InjuryRow]:
    """Parse a CSV string (DictReader-driven). Convenience for tests
    + the CLI's --csv path."""
    reader = csv.DictReader(StringIO(text))
    rows = [dict(r) for r in reader]
    return parse_csv_rows(rows)


def parse_csv_file(path: Path) -> list[InjuryRow]:
    """Parse a CSV file from disk."""
    return parse_csv_text(path.read_text(encoding="utf-8"))


__all__ = [
    "INJURY_STATUSES",
    "REQUIRED_COLUMNS",
    "InjuryRow",
    "parse_as_of",
    "parse_csv_file",
    "parse_csv_rows",
    "parse_csv_text",
    "parse_status",
]
