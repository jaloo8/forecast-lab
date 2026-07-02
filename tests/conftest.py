"""Shared pytest fixtures for the forecast-lab test suite."""

from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey


@pytest.fixture(autouse=True)
def _no_network(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail any non-``integration`` test that opens a real network socket.

    The unit + mocked-integration suite is meant to be hermetic — every
    external client is exercised through ``httpx.MockTransport`` or a
    ``patch``ed ``nba_api``, never a live endpoint (CLAUDE.md §7, #26). This
    autouse guard makes that invariant *enforceable*: a future test that
    forgets to mock turns into a loud, deterministic failure here instead of
    a flaky network-dependent test (or silent data egress) in CI.

    Tests that legitimately hit real APIs opt out with
    ``@pytest.mark.integration`` (deselected by default via the ``-m 'not
    integration'`` addopts); they skip this guard. We patch the egress entry
    points (``socket.socket.connect`` / ``connect_ex`` and the
    ``socket.create_connection`` helper) rather than blocking socket
    *creation*, so in-process consumers that merely construct sockets (or
    use the AF_UNIX / file-backed paths DuckDB and the sqlite request cache
    rely on) are unaffected — only an actual outbound connect is blocked.
    ``monkeypatch`` reverts all three at teardown.

    Loopback is exempt: it cannot reach an external endpoint, and on
    Windows asyncio's ProactorEventLoop bootstraps its internal self-pipe
    through a real ``127.0.0.1`` connect (CPython ``_fallback_socketpair``)
    — blocking it kills every async test before it runs.
    """
    if request.node.get_closest_marker("integration"):
        return

    real_connect = socket.socket.connect

    def _is_loopback(address: Any) -> bool:
        if not isinstance(address, tuple) or not address:
            return False
        host = address[0]
        return isinstance(host, str) and (host in ("localhost", "::1") or host.startswith("127."))

    def _blocked(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError(
            "Real network egress attempted in a non-integration test. Mock the "
            "transport (httpx.MockTransport) or patch the client, or mark the "
            "test @pytest.mark.integration if it must reach a live endpoint."
        )

    def _connect_guard(self: socket.socket, address: Any) -> None:
        if _is_loopback(address):
            real_connect(self, address)
            return
        _blocked()

    monkeypatch.setattr(socket.socket, "connect", _connect_guard)
    monkeypatch.setattr(socket.socket, "connect_ex", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)


@pytest.fixture(scope="session")
def rsa_private_key() -> RSAPrivateKey:
    """Generate a fresh RSA-2048 private key once per test session."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def rsa_private_key_file(tmp_path: Path, rsa_private_key: RSAPrivateKey) -> Path:
    """Write the session RSA key to a PEM file under a tmp path."""
    pem = rsa_private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    path = tmp_path / "kalshi-test.pem"
    path.write_bytes(pem)
    return path
