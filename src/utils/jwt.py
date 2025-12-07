"""JWT token utilities."""

import base64
import json
from datetime import datetime, timezone
from typing import Any


def decode_jwt_payload(token: str) -> dict[str, Any] | None:
    """
    Decode JWT token payload without verification.

    Args:
        token: JWT token string

    Returns:
        Decoded payload dict or None if decoding fails
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None

        payload = parts[1]
        # Add padding if needed
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += "=" * padding

        decoded = base64.urlsafe_b64decode(payload)
        return json.loads(decoded)
    except Exception:
        return None


def check_token_expiry(auth_token: str, account_name: str = "Unknown") -> tuple[bool, str]:
    """
    Check if token is expired or expiring soon.

    Args:
        auth_token: JWT token string
        account_name: Account identifier for logging

    Returns:
        Tuple of (is_valid, message)
    """
    payload = decode_jwt_payload(auth_token)
    if not payload:
        return False, "Could not decode token"

    exp_timestamp = payload.get("exp")
    if not exp_timestamp:
        return False, "Token has no expiry"

    exp_date = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)
    now = datetime.now(timezone.utc)

    if exp_date < now:
        return False, f"Token EXPIRED on {exp_date.strftime('%Y-%m-%d %H:%M:%S UTC')}"

    hours_until_expiry = (exp_date - now).total_seconds() / 3600

    if hours_until_expiry < 24:
        return True, f"Token expires in {hours_until_expiry:.1f} hours - refresh soon"

    return True, f"Token valid until {exp_date.strftime('%Y-%m-%d %H:%M:%S UTC')}"


def get_token_expiry_hours(auth_token: str) -> float | None:
    """
    Get hours until token expiry.

    Args:
        auth_token: JWT token string

    Returns:
        Hours until expiry or None if cannot determine
    """
    payload = decode_jwt_payload(auth_token)
    if not payload:
        return None

    exp_timestamp = payload.get("exp")
    if not exp_timestamp:
        return None

    exp_date = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)
    now = datetime.now(timezone.utc)

    return (exp_date - now).total_seconds() / 3600
