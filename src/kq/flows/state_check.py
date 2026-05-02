"""Operator-state geofence check for Kalshi sports contracts.

Run via ``kq state-check [--state TX]`` to surface whether the operator's
state currently allows Kalshi NBA/NFL contracts. Weather contracts are
uncontested in all 50 states as of May 2026 — no geofence applies.

Source for the per-state status table: the May 2026 Claude Research
report ("Frontier Edge for Retail-Scale Prediction-Market Forecasting")
which cross-references AgentBets state tracker, Holland & Knight's
"Prediction Markets at a Crossroads" Feb 2026, Epstein Becker Green
2026, and the iGamingBusiness class-action coverage. State law in this
area is moving fast — the table is a snapshot. The 3rd Circuit ruled
for Kalshi (NJ); 9th Circuit looks likely to rule against (NV); SCOTUS
path is plausible. Re-run after major court rulings.

Severity model:

  * **green**   — Kalshi sports contracts unambiguously available.
  * **contested** — letters issued / case in flight; live trading is
    legally risky. Paper-trading only until the case resolves.
  * **blocked** — court has ordered Kalshi to halt sports contracts in
    state. No live trading; paper-trading possible if Kalshi still
    serves the markets to your account, but expect that to change.
  * **criminal** — Arizona filed criminal charges against Kalshi
    March 2026. Highest risk. Do not trade sports there even on paper.

Exit codes:
  * 0 — sports unambiguously green
  * 1 — sports contested (live blocked, paper OK to continue) — informational
  * 2 — sports blocked or criminal-risk; or operator state unset
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from typing import Literal

import structlog

from kq.config import get_settings

log = structlog.get_logger(__name__)

Status = Literal["green", "contested", "blocked", "criminal"]


@dataclass(frozen=True, slots=True)
class StateRow:
    """One state's Kalshi sports-contract availability."""

    state: str
    status: Status
    notes: str
    citation: str


# Snapshot as of 2026-05-02. Update when the legal landscape shifts.
SNAPSHOT_DATE: date = date(2026, 5, 2)


# Default = "green" for any state not listed below. Per the research, ~38-40
# states have no active Kalshi-sports challenge as of May 2026.
_NON_GREEN: dict[str, StateRow] = {
    state.state: state
    for state in [
        StateRow(
            state="MA",
            status="blocked",
            notes=(
                "Suffolk County Superior Court preliminary injunction Jan 20 2026 "
                "(Judge Barry-Smith); Kalshi must comply within 30 days. MA Appeals "
                "Court briefly stayed; case headed to MA SJC."
            ),
            citation="NBC News Jan 2026; SBC Americas Feb 9 2026; ZwillGen analysis",
        ),
        StateRow(
            state="NV",
            status="blocked",
            notes=(
                "April 2025 prelim injunction granted Kalshi; **dissolved Nov 2025** "
                "(Judge Gordon, D. Nev.); 9th Cir. denied stay; sports contracts "
                "blocked via state registration system. Pending 9th Cir. appeal."
            ),
            citation="Holland & Knight; PYMNTS",
        ),
        StateRow(
            state="AZ",
            status="criminal",
            notes=(
                "BLOCKED + criminal charges filed March 17 2026 (20 misdemeanor "
                "counts); fed. TRO denied; 9th Cir. denied stay. Highest-risk state."
            ),
            citation="AgentBets; CFTC chair Selig response quoted",
        ),
        StateRow(
            state="MD",
            status="blocked",
            notes="TRO denied 2024-2025; sports contracts blocked.",
            citation="ZwillGen analysis",
        ),
        StateRow(
            state="MT",
            status="contested",
            notes="Active cease-and-desist; case in flight.",
            citation="PYMNTS",
        ),
        # Active cease-and-desist letters / contested but not yet adjudicated.
        StateRow(
            state="OH",
            status="contested",
            notes="Active cease-and-desist letters; CFTC sued OH Apr 2 2026.",
            citation="Saturday Down South tracker",
        ),
        StateRow(
            state="MI",
            status="contested",
            notes="Cease-and-desist; case pending.",
            citation="Saturday Down South tracker",
        ),
        StateRow(
            state="IL",
            status="contested",
            notes="CFTC sued IL Apr 2 2026; case in flight.",
            citation="PYMNTS",
        ),
        StateRow(
            state="CT",
            status="contested",
            notes="CFTC sued CT Apr 2 2026; case in flight.",
            citation="PYMNTS",
        ),
        StateRow(
            state="NY",
            status="contested",
            notes="State challenge in flight; not yet adjudicated.",
            citation="Saturday Down South tracker",
        ),
        # Specifically green states with citations (favorable rulings).
        StateRow(
            state="NJ",
            status="green",
            notes=(
                "3rd Circuit ruled in Kalshi's favor early 2026 — sports "
                "contracts deemed CFTC-regulated swaps."
            ),
            citation="PYMNTS reporting",
        ),
        StateRow(
            state="TN",
            status="green",
            notes=(
                "Feb 19 2026 prelim injunction granted Kalshi (Judge Trauger, "
                "M.D. Tenn.) — strongest preemption ruling."
            ),
            citation="Holland & Knight",
        ),
    ]
}

# All US states + DC, for unknown-state validation.
_ALL_US_STATES: frozenset[str] = frozenset(
    {
        "AL",
        "AK",
        "AZ",
        "AR",
        "CA",
        "CO",
        "CT",
        "DE",
        "FL",
        "GA",
        "HI",
        "ID",
        "IL",
        "IN",
        "IA",
        "KS",
        "KY",
        "LA",
        "ME",
        "MD",
        "MA",
        "MI",
        "MN",
        "MS",
        "MO",
        "MT",
        "NE",
        "NV",
        "NH",
        "NJ",
        "NM",
        "NY",
        "NC",
        "ND",
        "OH",
        "OK",
        "OR",
        "PA",
        "RI",
        "SC",
        "SD",
        "TN",
        "TX",
        "UT",
        "VT",
        "VA",
        "WA",
        "WV",
        "WI",
        "WY",
        "DC",
    }
)


def look_up(state_code: str) -> StateRow:
    """Return the StateRow for `state_code` (case-insensitive 2-letter code).

    States not in `_NON_GREEN` are returned as `green` with a generic note.
    Unknown codes raise ``ValueError``.
    """
    s = state_code.upper().strip()
    if s not in _ALL_US_STATES:
        raise ValueError(f"unknown state code {state_code!r}; expected 2-letter US code")
    if s in _NON_GREEN:
        return _NON_GREEN[s]
    return StateRow(
        state=s,
        status="green",
        notes=(
            "No active Kalshi-sports challenge known in this state. "
            "Re-check after any major court ruling."
        ),
        citation="Default green per the May 2026 snapshot",
    )


def render_human(row: StateRow, *, weather_note: bool = True) -> str:
    """Pretty-print a StateRow + (optionally) weather availability note."""
    glyph = {
        "green": "OK ",
        "contested": "WRN",
        "blocked": "ERR",
        "criminal": "ERR",
    }[row.status]
    lines = [
        f"=== Kalshi state-availability check ({SNAPSHOT_DATE.isoformat()}) ===",
        "",
        f"State: {row.state}",
        f"Sports contracts (NBA/NFL): [{glyph}] {row.status.upper()}",
        f"  {row.notes}",
        f"  source: {row.citation}",
    ]
    if weather_note:
        lines.append("")
        lines.append(
            "Weather contracts (KX-HIGH-*): [OK ] AVAILABLE in all 50 states "
            "(uncontested as of the snapshot date)."
        )
    if row.status in ("blocked", "criminal"):
        lines.append("")
        lines.append(
            "Recommendation: paper-trade sports only; do NOT enable `--live` for "
            "NBA/NFL until court status changes. Weather track is unaffected."
        )
    elif row.status == "contested":
        lines.append("")
        lines.append(
            "Recommendation: paper-trade sports OK; live sports trading is "
            "legally risky until the case resolves. Weather track is unaffected."
        )
    return "\n".join(lines)


def main(*, state: str | None = None, json_output: bool = False) -> int:
    """`python -m kq state-check` entrypoint.

    Reads operator's state from CLI flag or `OPERATOR_STATE` env var; warns
    if neither is set.
    """
    settings = get_settings()
    code = (state or settings.operator_state).strip()
    if not code:
        msg = (
            "OPERATOR_STATE is unset. Set it in `.env` (e.g. "
            "`OPERATOR_STATE=CA`) or pass `--state TX`. Sports geofence "
            "cannot be evaluated without it."
        )
        log.warning("state_check.unset")
        print(msg)
        return 2
    try:
        row = look_up(code)
    except ValueError as exc:
        log.error("state_check.invalid_state", state=code, error=str(exc))
        print(f"state_check failed: {exc}")
        return 2

    if json_output:
        out = asdict(row)
        out["snapshot_date"] = SNAPSHOT_DATE.isoformat()
        print(json.dumps(out))
    else:
        print(render_human(row))

    log.info(
        "state_check.computed",
        state=row.state,
        status=row.status,
        snapshot=SNAPSHOT_DATE.isoformat(),
    )

    return {
        "green": 0,
        "contested": 1,
        "blocked": 2,
        "criminal": 2,
    }[row.status]


__all__ = [
    "SNAPSHOT_DATE",
    "StateRow",
    "Status",
    "look_up",
    "main",
    "render_human",
]
