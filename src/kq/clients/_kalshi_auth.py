"""Kalshi RSA-PSS request signing.

Kalshi v2 API uses RSA-PSS (SHA-256, MGF1, salt length = hash length, default
public exponent) over the string `{timestamp_ms}{method}{path}` (no query
string, no body). Signature is base64-encoded and sent as a header.

Required headers:
    KALSHI-ACCESS-KEY         (your API key id)
    KALSHI-ACCESS-TIMESTAMP   (milliseconds since Unix epoch)
    KALSHI-ACCESS-SIGNATURE   (base64(RSA-PSS-SHA256(priv, msg)))

Docs: https://trading-api.readme.io/reference/authentication
"""

from __future__ import annotations

import base64
import time
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey


def load_private_key(path: Path, *, password: bytes | None = None) -> RSAPrivateKey:
    """Load an RSA private key from a PEM file."""
    pem = path.read_bytes()
    key = serialization.load_pem_private_key(pem, password=password)
    if not isinstance(key, RSAPrivateKey):
        raise TypeError(f"expected RSA private key, got {type(key).__name__}")
    return key


def sign_request(
    private_key: RSAPrivateKey,
    *,
    timestamp_ms: int,
    method: str,
    path: str,
) -> str:
    """Return the base64-encoded RSA-PSS signature for a Kalshi request.

    `path` is the request path including `/trade-api/v2` prefix, no query
    string (e.g. `/trade-api/v2/markets`).
    """
    message = f"{timestamp_ms}{method.upper()}{path}".encode()
    signature = private_key.sign(
        message,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.DIGEST_LENGTH,
        ),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode("ascii")


def auth_headers(
    *,
    api_key_id: str,
    private_key: RSAPrivateKey,
    method: str,
    path: str,
    now_ms: int | None = None,
) -> dict[str, str]:
    """Build the 3 required auth headers for a single Kalshi request."""
    ts = now_ms if now_ms is not None else int(time.time() * 1000)
    return {
        "KALSHI-ACCESS-KEY": api_key_id,
        "KALSHI-ACCESS-TIMESTAMP": str(ts),
        "KALSHI-ACCESS-SIGNATURE": sign_request(
            private_key, timestamp_ms=ts, method=method, path=path
        ),
    }
