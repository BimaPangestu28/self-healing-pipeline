"""Tests for Bot Framework JWT validation and bearer parsing."""

from __future__ import annotations

import time

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from src.approvals.bot_auth import (
    BOT_FRAMEWORK_ISSUER,
    bearer_token,
    verify_bot_framework_jwt,
)

APP_ID = "app-123"


class _FakeJWKClient:
    """Returns a fixed public key as the signing key (bypasses JWKS fetch)."""

    def __init__(self, public_key) -> None:
        self._public_key = public_key

    def get_signing_key_from_jwt(self, token: str):
        class _Key:
            key = self._public_key

        return _Key()


def _keys():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


def _token(private_key, **overrides) -> str:
    now = int(time.time())
    claims = {"aud": APP_ID, "iss": BOT_FRAMEWORK_ISSUER, "iat": now, "exp": now + 600}
    claims.update(overrides)
    return jwt.encode(claims, private_key, algorithm="RS256")


def test_bearer_token_parsing():
    assert bearer_token("Bearer abc.def") == "abc.def"
    assert bearer_token("bearer abc") == "abc"
    assert bearer_token("Basic abc") is None
    assert bearer_token(None) is None
    assert bearer_token("Bearer ") is None


def test_valid_token_accepted():
    private_key, public_key = _keys()
    token = _token(private_key)
    assert verify_bot_framework_jwt(token, APP_ID, jwk_client=_FakeJWKClient(public_key)) is True


def test_wrong_audience_rejected():
    private_key, public_key = _keys()
    token = _token(private_key, aud="another-app")
    assert verify_bot_framework_jwt(token, APP_ID, jwk_client=_FakeJWKClient(public_key)) is False


def test_wrong_issuer_rejected():
    private_key, public_key = _keys()
    token = _token(private_key, iss="https://evil.example")
    assert verify_bot_framework_jwt(token, APP_ID, jwk_client=_FakeJWKClient(public_key)) is False


def test_expired_token_rejected():
    private_key, public_key = _keys()
    now = int(time.time())
    token = _token(private_key, iat=now - 2000, exp=now - 1000)
    assert (
        verify_bot_framework_jwt(token, APP_ID, jwk_client=_FakeJWKClient(public_key), leeway=0)
        is False
    )


def test_token_signed_by_wrong_key_rejected():
    signing_key, _ = _keys()
    _, other_public_key = _keys()  # unrelated key the verifier will use
    token = _token(signing_key)
    assert (
        verify_bot_framework_jwt(token, APP_ID, jwk_client=_FakeJWKClient(other_public_key))
        is False
    )
