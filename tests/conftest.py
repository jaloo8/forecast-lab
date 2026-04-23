"""Shared pytest fixtures for the forecast-lab test suite."""

from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey


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
