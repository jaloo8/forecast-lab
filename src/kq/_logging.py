"""Centralized logging configuration.

structlog is used throughout the codebase (`log = structlog.get_logger(__name__)`)
but no central call to `structlog.configure(...)` existed, so:

- ``Settings.log_level`` was decorative — nothing wired it up.
- there was no way to switch to JSON output for cron / aggregators.
- there was no per-invocation ``trace_id`` to correlate one command's lines.
- there was no rotating file handler for cron.

This module fixes those gaps with a single :func:`setup_logging` called from
``kq.__main__`` before any subcommand runs. The defaults preserve pretty
console output in interactive shells while emitting JSON in non-TTY contexts
(cron, CI, container stdout pipes).

Routing (2026-07-01 audit fix): structlog events are emitted through the
stdlib ``logging`` tree via ``structlog.stdlib.LoggerFactory`` +
``ProcessorFormatter``, so the stderr handler AND the ``--log-file`` handler
both receive application logs. The pre-audit wiring used
``PrintLoggerFactory`` (stdout only) — the file handler only ever saw
foreign stdlib records (httpx, urllib3), never our own events.

Usage:

    from kq._logging import setup_logging, bind_trace_id
    setup_logging(level="info")           # CLI default
    bind_trace_id()                        # fresh uuid for this run
    log = structlog.get_logger(__name__)
    log.info("starting")                   # → trace_id=abc123 starting

The trace_id rides on a contextvar, so it propagates across asyncio tasks
and threads automatically.
"""

from __future__ import annotations

import logging
import sys
import uuid
from contextvars import ContextVar
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Final

import structlog

_LEVEL_BY_NAME: Final[dict[str, int]] = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
}

# Common shorthand accepted with a nudge toward the canonical name. Pre-audit,
# LOG_LEVEL=warn (or any typo) silently demoted to INFO — the operator thought
# they had quieted the logs and instead got MORE output.
_LEVEL_ALIASES: Final[dict[str, str]] = {
    "warn": "warning",
    "err": "error",
    "crit": "critical",
    "fatal": "critical",
}

_TRACE_ID: ContextVar[str | None] = ContextVar("kq_trace_id", default=None)


def setup_logging(
    *,
    level: str = "info",
    log_file: Path | None = None,
    json_output: bool | None = None,
) -> None:
    """Configure structlog + the standard logging module process-wide.

    Idempotent — safe to call multiple times (clears prior handlers first
    so test runs don't accumulate output streams).

    ``json_output``:
        - ``None`` (default): auto-detect from stderr.isatty() — JSON in
          non-TTY (cron, pipes, CI), pretty in interactive shells.
        - ``True``: force JSON.
        - ``False``: force pretty console output.
    """
    numeric_level = _level_to_int(level)
    use_json = json_output if json_output is not None else not sys.stderr.isatty()

    _configure_structlog(numeric_level=numeric_level)
    _configure_stdlib(numeric_level=numeric_level, log_file=log_file, use_json=use_json)


def bind_trace_id(trace_id: str | None = None) -> str:
    """Bind a fresh ``trace_id`` to the current context.

    Returns the bound id. Every subsequent ``log.info(...)`` from any module
    will include ``trace_id=<value>`` because the structlog config merges
    contextvars into every event.
    """
    tid = trace_id or uuid.uuid4().hex[:12]
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(trace_id=tid)
    _TRACE_ID.set(tid)
    return tid


def current_trace_id() -> str | None:
    """Return the currently bound trace_id (or None if no run is active)."""
    return _TRACE_ID.get()


# ----------------------------------------------------------------- internals


def _level_to_int(level: str) -> int:
    """Permissive level parser — case-insensitive, accepts common aliases
    ('warn' → 'warning', 'err' → 'error', 'fatal'/'crit' → 'critical').

    An unrecognized level falls back to INFO **loudly** (stderr): the
    pre-audit silent fallback meant a LOG_LEVEL typo changed verbosity
    without any hint why.
    """
    name = level.lower().strip()
    name = _LEVEL_ALIASES.get(name, name)
    numeric = _LEVEL_BY_NAME.get(name)
    if numeric is None:
        print(
            f"kq: unknown log level {level!r} — falling back to 'info' "
            f"(valid: {', '.join(_LEVEL_BY_NAME)})",
            file=sys.stderr,
        )
        return logging.INFO
    return numeric


def _shared_processors() -> list[structlog.types.Processor]:
    """Processors applied to structlog-native events (at configure time) and
    to foreign stdlib records (via the formatter's ``foreign_pre_chain``), so
    both render identically through the same handlers."""
    return [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]


def _configure_structlog(*, numeric_level: int) -> None:
    structlog.configure(
        processors=[
            *_shared_processors(),
            # Hand the event dict to the stdlib handlers' ProcessorFormatter —
            # this is what makes --log-file actually receive structlog output.
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,  # let level changes take effect on subsequent calls
    )


def _make_formatter(*, use_json: bool) -> logging.Formatter:
    """One ProcessorFormatter shared by the stderr + file handlers. Renders
    structlog-native events AND foreign stdlib records (httpx, scipy, ...)
    through the same renderer, so the log file is uniform."""
    renderer: structlog.types.Processor
    tail: list[structlog.types.Processor]
    if use_json:
        renderer = structlog.processors.JSONRenderer()
        tail = [structlog.processors.format_exc_info, renderer]
    else:
        # ConsoleRenderer formats exc_info itself (pretty tracebacks).
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
        tail = [renderer]
    return structlog.stdlib.ProcessorFormatter(
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, *tail],
        foreign_pre_chain=_shared_processors(),
    )


def _configure_stdlib(
    *,
    numeric_level: int,
    log_file: Path | None,
    use_json: bool,
) -> None:
    """Wire stdlib logging so httpx / scipy / urllib3 also respect level + file."""
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    # Clear prior handlers so repeat calls don't duplicate output.
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    formatter = _make_formatter(use_json=use_json)

    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setLevel(numeric_level)
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        # KNOWN LIMITATION: TimedRotatingFileHandler's midnight rotation is
        # not multi-process safe — concurrent cron processes sharing one
        # --log-file can race the delete/rename at rollover (worst case: one
        # process's lines land in a just-rotated file). ``delay=True`` keeps
        # processes that never log from opening (and rotating) the file at
        # all, which removes the common cron case of N idle processes racing.
        # For fully concurrent schedules, give each job its own --log-file
        # (see docs/SCHEDULED-RUNS.md — per-flow log paths).
        file_handler = TimedRotatingFileHandler(
            log_file,
            when="midnight",
            backupCount=14,
            encoding="utf-8",
            utc=True,
            delay=True,
        )
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
