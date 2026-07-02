"""Bot Framework inbound authentication for the Teams messaging endpoint.

Requests from the Bot Framework / Teams carry a bearer JWT signed by the Bot
Framework OpenID issuer. :func:`verify_bot_framework_jwt` validates the signature
(RS256 via JWKS), the issuer, the audience (your Microsoft App ID), and expiry.

Auth is gated by configuration so local development stays easy:
- ``MICROSOFT_APP_ID`` set  -> require and validate a Bot Framework JWT
- else ``TEAMS_OUTGOING_WEBHOOK_SECRET`` set -> HMAC (outgoing-webhook mode)
- else                       -> open (dev only)
"""

from __future__ import annotations

import logging
import os

import jwt

logger = logging.getLogger(__name__)

# Bot Framework (public cloud) token issuer + JWKS endpoint.
BOT_FRAMEWORK_ISSUER = "https://api.botframework.com"
BOT_FRAMEWORK_JWKS_URL = "https://login.botframework.com/v1/.well-known/keys"


def bearer_token(authorization_header: str | None) -> str | None:
    """Extract the token from an 'Authorization: Bearer <token>' header."""
    if not authorization_header:
        return None
    parts = authorization_header.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip() or None
    return None


def verify_bot_framework_jwt(
    token: str,
    app_id: str,
    *,
    jwk_client=None,
    jwks_url: str = BOT_FRAMEWORK_JWKS_URL,
    issuer: str = BOT_FRAMEWORK_ISSUER,
    leeway: int = 300,
) -> bool:
    """Validate a Bot Framework JWT for this bot.

    @param token - the bearer JWT from the request
    @param app_id - this bot's Microsoft App ID (expected audience)
    @param jwk_client - optional signing-key resolver (injected in tests)
    @param jwks_url - JWKS endpoint (defaults to the Bot Framework public cloud)
    @param issuer - expected token issuer
    @param leeway - clock-skew allowance in seconds
    @returns True when the token is valid for this bot, False otherwise
    """
    try:
        client = jwk_client or jwt.PyJWKClient(jwks_url)
        signing_key = client.get_signing_key_from_jwt(token).key
        jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience=app_id,
            issuer=issuer,
            leeway=leeway,
        )
        return True
    except Exception as exc:  # signature/aud/iss/expiry/JWKS errors
        logger.warning("Bot Framework JWT validation failed: %s", exc)
        return False


def bot_app_id() -> str:
    """Return the configured Microsoft App ID, or empty string."""
    return os.getenv("MICROSOFT_APP_ID", "").strip()
