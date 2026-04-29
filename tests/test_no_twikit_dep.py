"""Defensive guard: ensure twikit and similar TOS-violating Twitter scrapers
never end up in our dependency tree.

Rationale documented in `docs/EXTERNAL_RESOURCES.md` (rejected list) and
`ROADMAP.md` (non-goals). Twitter/X account-ban risk is real even for personal
use, and predictive lift on weather/NBA is near-zero per Pass 1 §1d.

If a future "let's just try it" attempt sneaks twikit in, this test fails
at CI before the dep gets merged.
"""

from __future__ import annotations

import importlib
import importlib.util

BANNED_TWITTER_SCRAPERS: tuple[str, ...] = (
    "twikit",
    "snscrape",
    "tweety",
)


def test_no_twitter_scrapers_installed() -> None:
    """None of the known Twitter scraping libraries are installed."""
    found: list[str] = []
    for module_name in BANNED_TWITTER_SCRAPERS:
        if importlib.util.find_spec(module_name) is not None:
            found.append(module_name)
    assert not found, (
        f"Twitter scraping libraries detected in environment: {found}. "
        "These violate Twitter's TOS and create account-ban risk. "
        "See docs/EXTERNAL_RESOURCES.md for the rejected-resources list."
    )


def test_official_twitter_api_not_in_deps() -> None:
    """The official tweepy lib isn't installed either; v1 has no Twitter integration."""
    assert importlib.util.find_spec("tweepy") is None, (
        "tweepy detected. v1 explicitly doesn't ingest Twitter "
        "(see CLAUDE.md §2 non-goals). If a v2 use case emerges, "
        "document it in ROADMAP.md before adding the dep."
    )
