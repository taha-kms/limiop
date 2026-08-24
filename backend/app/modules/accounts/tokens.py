"""Session tokens.

A token carries who the session belongs to and which generation of that
account's sessions it belongs to. The generation is what makes revocation
possible without storing every issued token: bumping the number on the user row
invalidates everything signed before it.

Every failure to read a token returns None. A caller is deciding whether
somebody is signed in, and an expired token, a forged one, and a truncated one
all mean the same thing to that decision.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

import jwt

ALGORITHM = "HS256"


@dataclass(frozen=True)
class SessionClaims:
    """What a session token asserts."""

    user_id: UUID
    token_version: int


def issue_token(claims: SessionClaims, *, secret: str, lifetime_minutes: int, now: datetime) -> str:
    expires = now + timedelta(minutes=lifetime_minutes)
    return jwt.encode(
        {
            "sub": str(claims.user_id),
            "ver": claims.token_version,
            "iat": int(now.timestamp()),
            "exp": int(expires.timestamp()),
        },
        secret,
        algorithm=ALGORITHM,
    )


def read_token(token: str, *, secret: str, now: datetime) -> SessionClaims | None:
    """The claims, or None for any reason the token cannot be trusted."""
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[ALGORITHM],
            # exp is compared against the caller's `now` below rather than
            # PyJWT's own clock, and iat needs the same treatment: PyJWT
            # validates iat against the real wall clock by default, which
            # would reject a token minted with a caller-supplied `now` that
            # doesn't match the system clock exactly (as every test here does).
            options={"require": ["sub", "ver", "exp"], "verify_exp": False, "verify_iat": False},
        )
    except jwt.InvalidTokenError:
        return None
    try:
        if int(payload["exp"]) < int(now.timestamp()):
            return None
        return SessionClaims(user_id=UUID(payload["sub"]), token_version=int(payload["ver"]))
    except (ValueError, TypeError):
        return None
