"""Refusing repeated attempts at the unauthenticated write endpoints.

Registration and sign-in are the only two, and both cost real work: password
hashing is argon2id and deliberately expensive, which defends a stolen hash and
funds an attacker who calls the endpoint in a loop. A ceiling turns credential
stuffing into something slow and account creation into something bounded.

One process, one counter. A shared store would be the right answer for several
replicas and the wrong amount of machinery for the one that is deployed; what
matters is that the limit exists and that it cannot grow without bound.

Counted per account rather than per caller, and the reason is the topology. The
browser never reaches the API directly: it posts to the frontend, which
re-issues the call server-side, so every browser-originated attempt arrives from
one address. Keying on that address made the limit a single shared budget —
ten failed sign-ins from anybody would have refused sign-in for everybody, which
is the denial of service the limit exists to prevent, introduced by the limit.

What that bounds and what it does not is worth being exact about. Guessing one
account's password is bounded, whatever address the guesses come from, which is
the attack. Creating many accounts under many addresses is not: the only signal
that would bound it is a caller identity this process cannot see, so it belongs
at the edge, and the deployment note says so rather than leaving the claim
implied.
"""

import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from math import ceil

from app.modules.accounts.models import normalize_email

# Above what a person typing their own password reaches, below what a script
# needs to be useful.
DEFAULT_ATTEMPTS = 10
DEFAULT_WINDOW_SECONDS = 60.0

# Bounded so a caller varying its address cannot make this the memory leak it
# was added to prevent. The oldest key is dropped, which at worst gives an
# attacker back the attempts they had already spent.
DEFAULT_CAPACITY = 4096


@dataclass(frozen=True, slots=True)
class AttemptLimit:
    """How many attempts a client gets, and over how long."""

    attempts: int = DEFAULT_ATTEMPTS
    window_seconds: float = DEFAULT_WINDOW_SECONDS

    def __post_init__(self) -> None:
        if self.attempts < 1:
            raise ValueError("attempts must be at least 1")
        if self.window_seconds <= 0:
            raise ValueError("window_seconds must be positive")


class AttemptThrottle:
    """A fixed window of attempts per key, bounded in memory.

    Fixed rather than sliding: a sliding window needs the timestamps of every
    attempt, and the extra precision buys nothing here — the question is whether
    a caller is hammering an endpoint, not exactly when they started.
    """

    def __init__(
        self,
        limit: AttemptLimit | None = None,
        *,
        capacity: int = DEFAULT_CAPACITY,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        self._limit = limit if limit is not None else AttemptLimit()
        self._capacity = capacity
        self._clock = clock
        self._windows: OrderedDict[str, tuple[float, int]] = OrderedDict()

    def retry_after(self, key: str) -> int | None:
        """Whole seconds the caller must wait, or None when it may proceed."""
        window = self._windows.get(key)
        if window is None:
            return None
        started, attempts = window
        remaining = self._limit.window_seconds - (self._clock() - started)
        if remaining <= 0:
            del self._windows[key]
            return None
        if attempts < self._limit.attempts:
            return None
        return max(1, ceil(remaining))

    def record(self, key: str) -> None:
        """Count one attempt against this key."""
        now = self._clock()
        window = self._windows.get(key)
        if window is None or now - window[0] >= self._limit.window_seconds:
            self._windows[key] = (now, 1)
        else:
            self._windows[key] = (window[0], window[1] + 1)
        self._windows.move_to_end(key)
        while len(self._windows) > self._capacity:
            self._windows.popitem(last=False)


def account_key(purpose: str, email: str) -> str:
    """The account being attempted, normalized the way the account itself is.

    Normalized, or `Ada@Example.com` and `ada@example.com` would be two budgets
    for one account. Keyed per purpose too, so exhausting the sign-in budget
    does not also refuse registration.
    """
    return f"{purpose}:{normalize_email(email)}"
