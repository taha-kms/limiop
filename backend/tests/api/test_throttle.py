"""The ceiling on registration and sign-in.

Both endpoints are unauthenticated and both cost an argon2id hash, which is
expensive on purpose. These tests are about the ceiling existing, about it being
spent only on what should spend it, about it belonging to one account rather
than to everybody, and about it never becoming the memory leak it was added to
prevent.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import PostgresDsn
from sqlalchemy import create_engine, text

from app.api.throttle import AttemptLimit, AttemptThrottle, account_key
from app.core.config import Environment, Settings
from app.main import create_app
from app.modules.accounts.passwords import verify_password_in_thread

CREDENTIALS = {"email": "ada@example.com", "password": "correct horse battery staple"}
WRONG = {"email": CREDENTIALS["email"], "password": "not the password at all"}


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def throttle(attempts: int = 2, window: float = 60.0, **extra: object) -> AttemptThrottle:
    clock = FakeClock()
    made = AttemptThrottle(
        AttemptLimit(attempts=attempts, window_seconds=window),
        clock=clock,
        **extra,  # type: ignore[arg-type]
    )
    made.clock = clock  # type: ignore[attr-defined]
    return made


def test_a_caller_under_the_limit_proceeds() -> None:
    limiter = throttle(attempts=2)

    limiter.record("a")

    assert limiter.retry_after("a") is None


def test_a_caller_at_the_limit_is_told_how_long_to_wait() -> None:
    limiter = throttle(attempts=2, window=30.0)

    limiter.record("a")
    limiter.record("a")

    assert limiter.retry_after("a") == 30


def test_the_window_expires_rather_than_refusing_forever() -> None:
    limiter = throttle(attempts=1, window=30.0)
    limiter.record("a")

    limiter.clock.now += 30.0  # type: ignore[attr-defined]

    assert limiter.retry_after("a") is None


def test_the_wait_shrinks_as_the_window_runs_down() -> None:
    limiter = throttle(attempts=1, window=30.0)
    limiter.record("a")

    limiter.clock.now += 20.0  # type: ignore[attr-defined]

    assert limiter.retry_after("a") == 10


def test_two_callers_do_not_share_a_budget() -> None:
    limiter = throttle(attempts=1)

    limiter.record("a")

    assert limiter.retry_after("a") is not None
    assert limiter.retry_after("b") is None


def test_the_counter_cannot_grow_without_bound() -> None:
    """A caller varying its address must not become the leak this prevents."""
    limiter = throttle(attempts=1, capacity=8)

    for index in range(100):
        limiter.record(f"caller-{index}")

    assert len(limiter._windows) == 8
    assert limiter.retry_after("caller-99") is not None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        pytest.param("attempts", 0, id="a limit of no attempts"),
        pytest.param("window_seconds", 0.0, id="a window of no time"),
    ],
)
def test_a_limit_without_a_bound_is_refused(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        AttemptLimit(**{field: value})  # type: ignore[arg-type]


def test_a_counter_with_no_room_is_refused() -> None:
    with pytest.raises(ValueError):
        AttemptThrottle(capacity=0)


@pytest.fixture
def throttled_client(database_url: PostgresDsn) -> Iterator[TestClient]:
    """A client that gets two attempts, so a test can spend them."""
    engine = create_engine(str(database_url))
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM users"))
    application = create_app(
        Settings(
            environment=Environment.TEST,
            database_url=database_url,
            auth_attempts=2,
            auth_attempt_window_seconds=60.0,
        )
    )
    with TestClient(application) as client:
        yield client
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM users"))
    engine.dispose()


pytestmark = pytest.mark.integration


def test_the_key_is_the_account_rather_than_the_caller() -> None:
    """Every browser attempt arrives from the frontend, so an address is not a
    caller: keying on one made the limit a single budget for everybody."""
    assert account_key("sessions", "Ada@Example.com ") == account_key("sessions", "ada@example.com")
    assert account_key("sessions", "ada@example.com") != account_key("accounts", "ada@example.com")


def test_repeated_failed_sign_ins_are_refused(throttled_client: TestClient) -> None:
    assert throttled_client.post("/api/v1/accounts", json=CREDENTIALS).status_code == 201

    assert throttled_client.post("/api/v1/sessions", json=WRONG).status_code == 401
    assert throttled_client.post("/api/v1/sessions", json=WRONG).status_code == 401
    refused = throttled_client.post("/api/v1/sessions", json=WRONG)

    assert refused.status_code == 429
    assert int(refused.headers["retry-after"]) > 0


def test_a_refusal_says_nothing_about_the_account(throttled_client: TestClient) -> None:
    """Whether the address is registered is not information this can buy."""
    unknown = {"email": "nobody@example.com", "password": "whatever it might be"}

    for _ in range(2):
        throttled_client.post("/api/v1/sessions", json=unknown)
    refused = throttled_client.post("/api/v1/sessions", json=unknown)

    assert refused.status_code == 429
    assert refused.json()["detail"] == "too many attempts; try again later"
    assert "nobody@example.com" not in refused.text


def test_a_refused_attempt_never_reaches_the_hasher(
    throttled_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The work being protected is the password hash."""
    assert throttled_client.post("/api/v1/accounts", json=CREDENTIALS).status_code == 201
    calls = 0

    async def counted(password: str, password_hash: str) -> bool:
        nonlocal calls
        calls += 1
        return await verify_password_in_thread(password, password_hash)

    monkeypatch.setattr("app.modules.accounts.service.verify_password_in_thread", counted)

    for _ in range(4):
        throttled_client.post("/api/v1/sessions", json=WRONG)

    assert calls == 2


def test_signing_in_successfully_does_not_spend_the_budget(
    throttled_client: TestClient,
) -> None:
    assert throttled_client.post("/api/v1/accounts", json=CREDENTIALS).status_code == 201

    for _ in range(5):
        assert throttled_client.post("/api/v1/sessions", json=CREDENTIALS).status_code == 204


def test_spending_the_sign_in_budget_does_not_refuse_registration(
    throttled_client: TestClient,
) -> None:
    for _ in range(3):
        throttled_client.post("/api/v1/sessions", json=WRONG)

    assert throttled_client.post("/api/v1/accounts", json=CREDENTIALS).status_code == 201


def test_one_account_being_attacked_does_not_lock_out_another(
    throttled_client: TestClient,
) -> None:
    """The defect this keying exists to avoid.

    Every browser attempt reaches the API from the frontend, so an address
    identifies the hop rather than the caller. Keyed on it, ten failed sign-ins
    from anybody refused sign-in for everybody.
    """
    other = {"email": "grace@example.com", "password": "another correct horse"}
    assert throttled_client.post("/api/v1/accounts", json=other).status_code == 201

    for _ in range(3):
        throttled_client.post("/api/v1/sessions", json=WRONG)

    assert throttled_client.post("/api/v1/sessions", json=other).status_code == 204


def test_registering_one_address_does_not_refuse_another(throttled_client: TestClient) -> None:
    for index in range(3):
        throttled_client.post(
            "/api/v1/accounts",
            json={"email": f"taken{index}@example.com", "password": "correct horse battery"},
        )

    assert throttled_client.post("/api/v1/accounts", json=CREDENTIALS).status_code == 201


def test_one_address_cannot_be_registered_over_and_over(throttled_client: TestClient) -> None:
    """Each attempt costs a password hash, whether or not it succeeds."""
    assert throttled_client.post("/api/v1/accounts", json=CREDENTIALS).status_code == 201
    assert throttled_client.post("/api/v1/accounts", json=CREDENTIALS).status_code == 409

    assert throttled_client.post("/api/v1/accounts", json=CREDENTIALS).status_code == 429
