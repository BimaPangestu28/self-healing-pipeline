"""Microsoft Teams integration for the approval flow.

Handles the Teams Adaptive Card **Universal Action** invoke that fires when a user
clicks Approve/Reject on a card posted by a bot. Teams sends an ``invoke`` activity
named ``adaptiveCard/action``; the bot replies with an invoke response carrying a
refreshed Adaptive Card, which Teams renders in place of the original.

Two auth modes are supported for the messaging endpoint:

- **Outgoing webhook** — Teams signs the request body with HMAC-SHA256 using a
  shared secret; verify it with :func:`verify_hmac`.
- **Bot Framework** — the platform authenticates with a bearer JWT; validation of
  that token is deployment-specific and left to the hosting layer.

Reference: Adaptive Cards Universal Actions / ``adaptiveCard/action`` invoke.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from typing import Any

from src.approvals.cards import build_message_card, build_result_card
from src.approvals.service import DemoService

logger = logging.getLogger(__name__)

_ADAPTIVE_CARD_CONTENT_TYPE = "application/vnd.microsoft.card.adaptive"


def verify_hmac(secret: str, body: bytes, authorization_header: str | None) -> bool:
    """Verify a Teams outgoing-webhook HMAC signature.

    @param secret - Base64 shared secret issued by Teams when creating the webhook
    @param body - Raw request body bytes
    @param authorization_header - The request 'Authorization' header ("HMAC <sig>")
    @returns True when the computed signature matches the provided one
    """
    if not authorization_header or not authorization_header.startswith("HMAC "):
        return False
    provided = authorization_header[len("HMAC "):].strip()
    try:
        key = base64.b64decode(secret)
    except (ValueError, TypeError):
        return False
    digest = hmac.new(key, body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(provided, expected)


def _invoke_response(card: dict[str, Any]) -> dict[str, Any]:
    """Wrap an Adaptive Card as a Teams invoke response body."""
    return {"statusCode": 200, "type": _ADAPTIVE_CARD_CONTENT_TYPE, "value": card}


def _decide(service: DemoService, verb: str | None, request_id: str | None) -> dict[str, Any]:
    """Apply an approve/reject decision and return the refreshed result card."""
    if not request_id:
        return build_message_card("Missing request id in the action payload.", color="Attention")

    request = service.get(request_id)
    if request is None:
        return build_message_card("Unknown or expired approval request.", color="Attention")

    if verb == "approve":
        request = service.approve(request_id)
    elif verb == "reject":
        request = service.reject(request_id)
    else:
        return build_message_card(f"Unsupported action verb: {verb}", color="Attention")

    return build_result_card(request)


def handle_teams_activity(service: DemoService, activity: dict[str, Any]) -> dict[str, Any]:
    """Handle a Teams activity and return an invoke-response body.

    @param service - The approval service that owns pending requests
    @param activity - The parsed Teams Activity JSON
    @returns An invoke-response dict (statusCode/type/value) to serialize back
    """
    if activity.get("type") == "invoke" and activity.get("name") == "adaptiveCard/action":
        value = activity.get("value") or {}
        action = value.get("action") or {}
        data = action.get("data") or {}
        verb = data.get("verb") or action.get("verb")
        request_id = data.get("requestId")
        return _invoke_response(_decide(service, verb, request_id))

    return _invoke_response(
        build_message_card("This bot handles Approve/Reject card actions only.")
    )
