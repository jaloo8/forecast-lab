"""Dry-run estimator for the planned GEFSv12 reforecast pull.

Phase 1 of three for ROADMAP item #6 — see
``docs/research/GEFSV12-REFORECAST-INTEGRATION.md``. This flow does NOT
download anything; it just prints what a future ``kq pull-gefsv12-reforecasts``
(phase 2) would fetch given a config, so the user can size up the
operation before approving the system-dep additions phase 2 needs.
"""

from __future__ import annotations

import structlog

from kq.clients.gefs_reforecast import (
    ARCHIVE_FIRST_YEAR,
    ARCHIVE_LAST_YEAR,
    DEFAULT_DAYS_RANGE,
    DEFAULT_MEMBERS,
    TMAX_VARIABLE,
    estimate_pull_volume,
)

log = structlog.get_logger(__name__)


def main(
    *,
    start_year: int = ARCHIVE_FIRST_YEAR,
    end_year: int = ARCHIVE_LAST_YEAR,
    n_stations: int = 6,
    n_target_records_per_file: int = 1,
) -> None:
    """`python -m kq plan-gefsv12-pull` entrypoint."""
    plan = estimate_pull_volume(
        start_year=start_year,
        end_year=end_year,
        members=DEFAULT_MEMBERS,
        variables=(TMAX_VARIABLE,),
        days_ranges=(DEFAULT_DAYS_RANGE,),
        n_stations=n_stations,
        n_target_records_per_file=n_target_records_per_file,
    )

    log.info(
        "gefsv12.plan",
        start_year=start_year,
        end_year=end_year,
        n_stations=n_stations,
        n_target_records_per_file=n_target_records_per_file,
        n_files=plan.n_files,
        n_http_requests=plan.n_http_requests,
        megabytes_total=round(plan.megabytes_total, 1),
    )
    print("GEFSv12 reforecast pull plan (dry run — nothing downloaded):")
    print(f"  archive years           : {start_year} → {end_year}")
    print(f"  members                 : {', '.join(DEFAULT_MEMBERS)}")
    print(f"  variables               : {TMAX_VARIABLE}")
    print(f"  days_ranges             : {DEFAULT_DAYS_RANGE}")
    print(f"  stations                : {n_stations}")
    print(f"  records per file        : {n_target_records_per_file}")
    print()
    print(f"  unique cycles           : {plan.n_unique_cycles:>10,}")
    print(f"  total files indexed     : {plan.n_files:>10,}")
    print(f"  total HTTP requests     : {plan.n_http_requests:>10,}")
    print(f"  bytes (.idx files)      : {plan.bytes_idx / 1_000_000:>10,.1f} MB")
    print(f"  bytes (range records)   : {plan.bytes_records / 1_000_000:>10,.1f} MB")
    print(f"  bytes (total)           : {plan.bytes_total / 1_000_000:>10,.1f} MB")
    print()
    print("phase 2 prerequisites:")
    print("  - cfgrib + xarray + system eccodes (CLAUDE.md §9 — needs user signoff)")
    print("  - throttling: ~10 concurrent HTTP at most; AWS Open Data is unauthenticated")
    print("  - storage: extend models/weather_forecast schema with gefsv12_reforecast model rows")


if __name__ == "__main__":  # pragma: no cover
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--start-year", type=int, default=ARCHIVE_FIRST_YEAR)
    parser.add_argument("--end-year", type=int, default=ARCHIVE_LAST_YEAR)
    parser.add_argument("--n-stations", type=int, default=6)
    parser.add_argument("--records-per-file", type=int, default=1)
    args = parser.parse_args()
    main(
        start_year=args.start_year,
        end_year=args.end_year,
        n_stations=args.n_stations,
        n_target_records_per_file=args.records_per_file,
    )
