"""JWT blacklist -- supports active logout by revoking tokens before expiry.

When a user logs out, their JWT is added to the blacklist with a TTL equal
to the remaining token lifetime. On each authenticated request, the auth
dependency checks the blacklist.
"""

from __future__ import annotations

import logging

from app.infrastructure.redis_client import cache_get, cache_set

logger = logging.getLogger(__name__)

BLACKLIST_KEY_PREFIX = "jwt:blacklist:"


def blacklist_token(jti: str, remaining_seconds: int) -> None:
    """Add a JWT ID to the blacklist."""
    if remaining_seconds <= 0:
        return
    cache_set(f"{BLACKLIST_KEY_PREFIX}{jti}", True, remaining_seconds)


def is_blacklisted(jti: str) -> bool:
    """Check if a JWT ID is blacklisted."""
    return cache_get(f"{BLACKLIST_KEY_PREFIX}{jti}") is not None
