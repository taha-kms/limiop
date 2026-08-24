import asyncio
import threading
import time

import anyio
import pytest

from app.modules.accounts import passwords
from app.modules.accounts.passwords import hash_password, verify_password


def test_a_hash_does_not_contain_the_password() -> None:
    hashed = hash_password("correct horse battery staple")
    assert "correct horse battery staple" not in hashed


def test_the_same_password_hashes_differently_every_time() -> None:
    # argon2 salts each call, so hashing one password twice must not repeat.
    first = hash_password("hunter2")
    second = hash_password("hunter2")
    assert first != second


def test_the_right_password_verifies() -> None:
    assert verify_password("hunter2", hash_password("hunter2")) is True


def test_the_wrong_password_does_not() -> None:
    assert verify_password("hunter3", hash_password("hunter2")) is False


def test_a_malformed_hash_is_a_failure_rather_than_a_crash() -> None:
    assert verify_password("hunter2", "not-a-hash") is False


def test_hashing_runs_off_the_event_loop_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    """Argon2 costs ~60 ms of CPU. Called straight from `async def` code that
    is 60 ms in which the worker answers nobody, and it is reachable without
    credentials, so it is a denial of service and not only a slow login."""
    hashing_threads: list[int] = []
    real_hash = passwords.hash_password

    def recording_hash(plain: str) -> str:
        hashing_threads.append(threading.get_ident())
        return real_hash(plain)

    monkeypatch.setattr(passwords, "hash_password", recording_hash)

    async def run() -> int:
        await passwords.hash_password_in_thread("hunter2")
        return threading.get_ident()

    loop_thread = asyncio.run(run())

    assert hashing_threads
    assert loop_thread not in hashing_threads


def test_verifying_runs_off_the_event_loop_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    verifying_threads: list[int] = []
    real_verify = passwords.verify_password

    def recording_verify(plain: str, hashed: str) -> bool:
        verifying_threads.append(threading.get_ident())
        return real_verify(plain, hashed)

    monkeypatch.setattr(passwords, "verify_password", recording_verify)
    hashed = hash_password("hunter2")

    async def run() -> tuple[bool, int]:
        matched = await passwords.verify_password_in_thread("hunter2", hashed)
        return matched, threading.get_ident()

    matched, loop_thread = asyncio.run(run())

    assert matched is True
    assert verifying_threads
    assert loop_thread not in verifying_threads


def test_no_more_hashes_run_at_once_than_the_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    """A worker thread alone would only trade the stall for a memory ceiling:
    anyio's default limiter allows 40 concurrent threads, and argon2 reserves
    64 MiB per call. The bound is what keeps a flood queueing instead of
    allocating ~2.5 GiB.

    Nothing here asserts an elapsed time: the stand-in hash blocks until as
    many calls as the bound allows are inside it at once, and what is measured
    is peak concurrency, so a working limiter reaches exactly the bound and an
    absent one overshoots it.
    """
    saturated = threading.Event()
    counter = threading.Lock()
    in_flight = 0
    peak = 0

    def blocking_hash(plain: str) -> str:
        nonlocal in_flight, peak
        with counter:
            in_flight += 1
            peak = max(peak, in_flight)
            if in_flight >= passwords.MAX_CONCURRENT_HASHES:
                saturated.set()
        saturated.wait(timeout=5)
        # Long enough that a limiter that had been removed would let the
        # stragglers pile in and be counted, rather than arriving after the
        # first group has already drained.
        time.sleep(0.05)
        with counter:
            in_flight -= 1
        return "not a real hash"

    monkeypatch.setattr(passwords, "hash_password", blocking_hash)

    async def run() -> None:
        async with anyio.create_task_group() as group:
            for _ in range(passwords.MAX_CONCURRENT_HASHES * 2):
                group.start_soon(passwords.hash_password_in_thread, "hunter2")

    asyncio.run(run())

    assert saturated.is_set(), "the bound never filled, so nothing was measured"
    assert peak == passwords.MAX_CONCURRENT_HASHES
