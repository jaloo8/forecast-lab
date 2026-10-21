"""Explicit offline commands for separate local paper accounting books.

No command collects prices, generates a strategy signal, contacts a broker or
starts a scheduler. Observing a quote and simulating a fill are separate actions.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from kq.equities import local_paper

_SECRET_FIELD = re.compile(
    r"^(password|passphrase|api_?key|access_?token|refresh_?token|private_?key|"
    r"client_?secret|secret|credentials?|authorization|cookie)$",
    re.I,
)
_MAX_INPUT_BYTES = 1024 * 1024


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _nonfinite(_: str) -> None:
    raise ValueError("nonfinite JSON constants are not allowed")


def _check_fields(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if _SECRET_FIELD.fullmatch(key):
                raise ValueError("credential fields are not paper input")
            _check_fields(item)
    elif isinstance(value, list):
        for item in value:
            _check_fields(item)


def read_input(path: Path) -> dict[str, Any]:
    """Read a bounded ordinary JSON file without echoing its contents on error."""
    if path.suffix.lower() != ".json" or any(
        word in path.name.lower() for word in ("credential", "secret", ".env")
    ):
        raise ValueError("an ordinary noncredential .json input is required")
    if any(p.is_symlink() or p.is_junction() for p in (path.absolute(), *path.absolute().parents)):
        raise ValueError("linked input paths are not supported")
    with path.open("rb") as handle:
        raw = handle.read(_MAX_INPUT_BYTES + 1)
    if len(raw) > _MAX_INPUT_BYTES:
        raise ValueError("input exceeds the one MiB limit")
    value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_pairs, parse_constant=_nonfinite)
    if not isinstance(value, dict):
        raise ValueError("a JSON object is required")
    _check_fields(value)
    return value


def registration_template(asset_type: str) -> dict[str, Any]:
    """Require completed fields; supplied evidence authenticity remains unverified."""
    instrument: dict[str, Any] = {
        "instrument_id": "SPY" if asset_type == "stock" else "SELECT_CONTRACT",
        "symbol": "SPY" if asset_type == "stock" else "SELECT_CONTRACT",
        "definition_sha256": None,
        "definition_source": "REPLACE_WITH_REVIEWED_DEFINITION_REFERENCE",
        "multiplier": 1 if asset_type == "stock" else 100,
    }
    if asset_type == "option":
        instrument.update(
            underlying="SPY",
            right="call",
            strike=None,
            expiration_date=None,
            last_tradable_at=None,
            standard_deliverable=None,
        )
    return {
        "schema_version": 1,
        "book_id": f"local-{asset_type}-prep-v1",
        "strategy_id": "unregistered",
        "strategy_sha256": None,
        "initial_cash": "1000.00",
        "asset_type": asset_type,
        "instruments": [instrument],
        "allowed_sources": ["REPLACE_WITH_REVIEWED_SOURCE"],
        "stock_slippage_bps": "10",
        "stock_fee_per_order": "0.00",
        "option_slippage_per_unit": "0.01",
        "option_fee_per_contract": "0.65",
        "max_entry_debit": "1000.00" if asset_type == "stock" else "100.00",
        "max_quote_age_seconds": 60,
        "max_capture_delay_seconds": 5,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    template = sub.add_parser("template", help="Print an incomplete registration; creates no book")
    template.add_argument("--asset-type", required=True, choices=("stock", "option"))
    create = sub.add_parser("create", help="Create a NEW local simulation book; never resets")
    create.add_argument("--root", required=True, type=Path)
    create.add_argument("--registration", required=True, type=Path)
    status = sub.add_parser("status", help="Inspect an existing book; never fills an order")
    status.add_argument("--book", required=True, type=Path)
    for name in ("intent", "quote"):
        command = sub.add_parser(name, help=f"Explicitly record one {name} JSON object")
        command.add_argument("--book", required=True, type=Path)
        command.add_argument("--input", required=True, type=Path)
    fill = sub.add_parser("fill", help="Explicitly simulate a previously recorded intent/quote")
    fill.add_argument("--book", required=True, type=Path)
    fill.add_argument("--intent-id", required=True)
    fill.add_argument("--quote-id", required=True)
    cancel = sub.add_parser("cancel", help="Cancel an unfilled intent and release its reservation")
    cancel.add_argument("--book", required=True, type=Path)
    cancel.add_argument("--intent-id", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "template":
            result = registration_template(args.asset_type)
        elif args.command == "create":
            result = local_paper.create_book(args.root, read_input(args.registration))
        elif args.command == "status":
            result = local_paper.inspect_book(args.book)
        elif args.command == "intent":
            result = local_paper.submit_intent(args.book, read_input(args.input))
        elif args.command == "quote":
            result = local_paper.observe_quote(args.book, read_input(args.input))
        elif args.command == "fill":
            result = local_paper.fill_intent(args.book, args.intent_id, args.quote_id)
        else:
            result = local_paper.cancel_intent(args.book, args.intent_id)
        print(json.dumps(result, indent=2, allow_nan=False))
        if result.get("accepted") is False:
            return 2
    except local_paper.PaperError as exc:
        # Engine errors contain controlled field names and reasons, never payloads.
        print(f"Local paper command stopped: {exc}", file=sys.stderr)
        return 2
    except (ValueError, OSError) as exc:
        # Do not include malformed input values or file contents in CLI diagnostics.
        print(
            f"Local paper command stopped ({type(exc).__name__}); no success claimed.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
