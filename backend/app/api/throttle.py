"""Refusing repeated attempts at the unauthenticated write endpoints.

Registration and sign-in are the only two, and both cost real work: password
hashing is argon2id and deliberately expensive, which defends a stolen hash and
funds an attacker who calls the endpoint in a loop. A ceiling turns credential
stuffing into something slow and account creation into something bounded.

One process, one counter. A shared store would be the right answer for several
replicas and the wrong amount of machinery for the one that is deployed; what
matters is that the limit exists and that it cannot grow without bound.
"""

import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from math import ceil

from fastapi import Request

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


@dataclass(frozen=True, slots=True)
class AttemptRecorder:
    """One endpoint's budget for one caller, already checked.

    Handed to a handler that has been let through, so it can say whether the
    attempt was worth counting. Sign-in counts failures; registration counts
    every attempt, because creating accounts in a loop is the abuse there.
    """

    throttle: AttemptThrottle
    key: str

    def record(self) -> None:
        self.throttle.record(self.key)


def client_key(request: Request, purpose: str) -> str:
    """Who is asking, as far as this process can honestly tell.

    The peer address, not `X-Forwarded-For`: a header the caller sets is a
    header the caller varies, and reading it without a trusted proxy in front
    would make the limit opt-out. Behind a proxy the deployment must have the
    server populate the peer address from it — uvicorn's `--proxy-headers` —
    which is where trust belongs.

    Keyed per purpose, so exhausting the sign-in budget does not also refuse
    registration.
    """
    client = request.client
    return f"{purpose}:{client.host if client is not None else 'unknown'}"
