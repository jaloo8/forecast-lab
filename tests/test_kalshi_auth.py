"""Tests for Kalshi RSA-PSS request signing."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

from kq.clients._kalshi_auth import auth_headers, load_private_key, sign_request


def test_signature_verifies_with_public_key(rsa_private_key: RSAPrivateKey) -> None:
    ts_ms = 1_700_000_000_000
    method = "GET"
    path = "/trade-api/v2/markets"
    sig_b64 = sign_request(rsa_private_key, timestamp_ms=ts_ms, method=method, path=path)

    signature = base64.b64decode(sig_b64)
    message = f"{ts_ms}{method}{path}".encode()
    # Verify with the matching public key — should not raise.
    rsa_private_key.public_key().verify(
        signature,
        message,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.DIGEST_LENGTH,
        ),
        hashes.SHA256(),
    )


def test_signature_rejects_tampered_message(rsa_private_key: RSAPrivateKey) -> None:
    ts_ms = 1_700_000_000_000
    sig_b64 = sign_request(
        rsa_private_key, timestamp_ms=ts_ms, method="GET", path="/trade-api/v2/markets"
    )
    tampered = f"{ts_ms}GET/trade-api/v2/portfolio/fills".encode()

    with pytest.raises(InvalidSignature):
        rsa_private_key.public_key().verify(
            base64.b64decode(sig_b64),
            tampered,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH,
            ),
            hashes.SHA256(),
        )


def test_auth_headers_shape(rsa_private_key: RSAPrivateKey) -> None:
    headers = auth_headers(
        api_key_id="test-key-id",
        private_key=rsa_private_key,
        method="GET",
        path="/trade-api/v2/markets",
        now_ms=1_700_000_000_000,
    )
    assert headers["KALSHI-ACCESS-KEY"] == "test-key-id"
    assert headers["KALSHI-ACCESS-TIMESTAMP"] == "1700000000000"
    assert headers["KALSHI-ACCESS-SIGNATURE"]
    # base64 decodes without error
    base64.b64decode(headers["KALSHI-ACCESS-SIGNATURE"])


def test_auth_headers_default_timestamp_is_millis(
    rsa_private_key: RSAPrivateKey, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("kq.clients._kalshi_auth.time.time", lambda: 1_700_000_000.123)
    headers = auth_headers(
        api_key_id="id",
        private_key=rsa_private_key,
        method="GET",
        path="/x",
    )
    assert headers["KALSHI-ACCESS-TIMESTAMP"] == "1700000000123"


def test_load_private_key_round_trip(rsa_private_key_file: Path) -> None:
    key = load_private_key(rsa_private_key_file)
    assert key.key_size >= 2048


def test_load_private_key_rejects_non_rsa(tmp_path: Path) -> None:
    ed_key = ed25519.Ed25519PrivateKey.generate()
    pem = ed_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    path = tmp_path / "ed.pem"
    path.write_bytes(pem)
    with pytest.raises(TypeError):
        load_private_key(path)
