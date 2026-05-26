"""Self-test for the autouse network-egress guard (``conftest._no_network``).

#26's invariant — "the non-integration suite never touches a live endpoint"
— is only worth anything if the guard enforcing it actually fires. These
tests prove it does: a real outbound connect from a normal (non-integration)
test raises the guard's ``RuntimeError`` instead of opening a socket. If the
guard is ever removed or broken, these fail.

(The corollary — that real client tests still pass *with* the guard active —
is verified by the whole rest of the suite running green under it.)
"""

from __future__ import annotations

import socket

import pytest


def test_create_connection_is_blocked() -> None:
    """`socket.create_connection` (the helper httpx/requests ultimately use
    for real egress) must raise the guard error, not attempt a connection."""
    with pytest.raises(RuntimeError, match="Real network egress attempted"):
        socket.create_connection(("example.com", 80), timeout=1)


def test_socket_connect_method_is_blocked() -> None:
    """A raw `socket.connect` is blocked too — constructing the socket is
    fine (no egress), but the outbound connect fails loudly."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(RuntimeError, match="non-integration test"):
            sock.connect(("example.com", 80))
    finally:
        sock.close()
