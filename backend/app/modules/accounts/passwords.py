"""Password hashing.

Argon2id, with the library's current defaults rather than numbers pinned here:
the parameters are a moving target and the library tracks them better than a
constant in this file would.

Those defaults cost roughly 60 ms of CPU and 64 MiB of memory per call, which
is the whole point of them -- but that cost is paid on whichever thread makes
the call, and on the event loop it is 60 ms in which the worker serves nobody
at all, the public job catalogue included. Ten concurrent logins measured a
934 ms worst-case stall. Async callers must therefore use the awaitable forms
here; the plain functions are the primitives those run in a worker thread, and
calling them directly is only safe where no event loop is waiting.
"""

import anyio.to_thread
from anyio import CapacityLimiter
from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error

_hasher = PasswordHasher()

# A worker thread stops the stall; on its own it converts the stall into a
# memory ceiling, because anyio's default limiter allows 40 concurrent threads
# and 40 hashes at 64 MiB each is ~2.5 GiB resident. Past this many, hashing
# queues rather than fanning out. Slower under a flood is the right answer for
# an endpoint whose cost is deliberate and whose trigger is unauthenticated --
# a login for an address that does not exist hashes too, by design.
MAX_CONCURRENT_HASHES = 4
_hashing_limiter = CapacityLimiter(MAX_CONCURRENT_HASHES)


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


async def hash_password_in_thread(plain: str) -> str:
    return await anyio.to_thread.run_sync(hash_password, plain, limiter=_hashing_limiter)


async def verify_password_in_thread(plain: str, hashed: str) -> bool:
    return await anyio.to_thread.run_sync(verify_password, plain, hashed, limiter=_hashing_limiter)
