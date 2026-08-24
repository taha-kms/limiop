"""Password hashing.

Argon2id, with the library's current defaults rather than numbers pinned here:
the parameters are a moving target and the library tracks them better than a
constant in this file would.
"""

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error

_hasher = PasswordHasher()


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Whether the password matches.

    A malformed stored hash is a failed verification rather than an exception.
    Callers are authenticating, and a corrupt row should deny access rather
    than return a 500 that distinguishes it from a wrong password.
    """
    try:
        return _hasher.verify(hashed, plain)
    except (Argon2Error, ValueError):
        return False
