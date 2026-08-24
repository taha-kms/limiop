from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt

from app.modules.accounts.tokens import ALGORITHM, SessionClaims, issue_token, read_token

SECRET = "s" * 32
NOW = datetime(2026, 8, 24, 12, tzinfo=UTC)


def test_a_token_round_trips() -> None:
    claims = SessionClaims(user_id=uuid4(), token_version=3)
    token = issue_token(claims, secret=SECRET, lifetime_minutes=60, now=NOW)
    assert read_token(token, secret=SECRET, now=NOW) == claims


def test_an_expired_token_is_refused() -> None:
    token = issue_token(
        SessionClaims(user_id=uuid4(), token_version=1),
        secret=SECRET,
        lifetime_minutes=60,
        now=NOW,
    )
    assert read_token(token, secret=SECRET, now=NOW + timedelta(minutes=61)) is None


def test_a_token_signed_with_another_secret_is_refused() -> None:
    token = issue_token(
        SessionClaims(user_id=uuid4(), token_version=1),
        secret=SECRET,
        lifetime_minutes=60,
        now=NOW,
    )
    assert read_token(token, secret="other" * 8, now=NOW) is None


def test_rubbish_is_refused_rather_than_raising() -> None:
    assert read_token("not.a.token", secret=SECRET, now=NOW) is None
    assert read_token("", secret=SECRET, now=NOW) is None


def test_a_validly_signed_token_with_a_non_uuid_subject_is_refused() -> None:
    token = jwt.encode(
        {"sub": "not-a-uuid", "ver": 1, "exp": int((NOW + timedelta(minutes=60)).timestamp())},
        SECRET,
        algorithm=ALGORITHM,
    )
    assert read_token(token, secret=SECRET, now=NOW) is None


def test_a_validly_signed_token_with_a_malformed_expiry_is_refused() -> None:
    token = jwt.encode(
        {"sub": str(uuid4()), "ver": 1, "exp": "banana"},
        SECRET,
        algorithm=ALGORITHM,
    )
    assert read_token(token, secret=SECRET, now=NOW) is None


def test_an_unsigned_alg_none_token_is_refused() -> None:
    claims = {
        "sub": str(uuid4()),
        "ver": 1,
        "exp": int((NOW + timedelta(minutes=60)).timestamp()),
    }
    token = jwt.encode(claims, key=None, algorithm="none")
    assert read_token(token, secret=SECRET, now=NOW) is None


def test_a_token_signed_with_a_different_algorithm_is_refused() -> None:
    claims = {
        "sub": str(uuid4()),
        "ver": 1,
        "exp": int((NOW + timedelta(minutes=60)).timestamp()),
    }
    token = jwt.encode(claims, SECRET, algorithm="HS512")
    assert read_token(token, secret=SECRET, now=NOW) is None
