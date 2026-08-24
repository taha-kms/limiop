"""Properties of `current_user` that the HTTP tests cannot see.

`tests/api/test_current_user.py` pins what a rejected caller receives. This
file pins what the process is left holding afterwards.
"""

import asyncio
from typing import cast

import pytest
from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import current_user
from app.core.config import Environment, Settings


def reject_once() -> HTTPException:
    """Drive `current_user` down its no-cookie branch and return what it raised.

    The branch returns before the session is touched, so a real one would only
    add a database to a test that is not about the database.
    """
    request = Request({"type": "http", "method": "GET", "path": "/api/v1/me", "headers": []})
    settings = Settings(environment=Environment.TEST)

    async def reject() -> HTTPException:
        no_session = cast(AsyncSession, None)
        with pytest.raises(HTTPException) as raised:
            await current_user(request, no_session, settings)
        return raised.value

    return asyncio.run(reject())


def test_each_rejection_raises_a_fresh_exception() -> None:
    """A single module-level `HTTPException` raised from every branch would be
    a memory leak: CPython appends a frame to an exception's `__traceback__` on
    every `raise` of that object, and a module global is never collected, so
    each 401 would pin that request's `Request`, ASGI scope and resolved
    dependencies for the life of the process. Measured at ~27 KB per 401 --
    reachable without credentials, and reached by every ordinary expired
    session too.
    """
    first = reject_once()
    second = reject_once()

    assert first is not second


def traceback_depth(error: BaseException) -> int:
    depth = 0
    frame = error.__traceback__
    while frame is not None:
        depth += 1
        frame = frame.tb_next
    return depth


def test_the_retained_traceback_does_not_grow_across_rejections() -> None:
    """The object identity above is the mechanism; this is the consequence.
    A reused instance arrives at each raise still carrying the previous
    request's frames, so the chain -- and everything its frames pin -- gets
    longer with every 401.
    """
    depth_after_one_rejection = traceback_depth(reject_once())

    assert traceback_depth(reject_once()) == depth_after_one_rejection


def test_every_rejection_still_says_the_same_thing() -> None:
    """Building the exception per raise must not let the wording drift between
    branches -- that is the whole point of the single detail string.
    """
    first = reject_once()
    second = reject_once()

    assert first.status_code == second.status_code == status.HTTP_401_UNAUTHORIZED
    assert first.detail == second.detail
