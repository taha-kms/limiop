# Identity and Sessions Implementation Plan

> Work this plan one task at a time. Each task ends with a passing test and a
> commit, and the checkboxes track where you are.

**Goal:** A visitor can register, log in, be recognised on later requests, and log out — with sessions carried in an HttpOnly cookie and revocable on password change.

**Architecture:** A new `accounts` module holding the user row, password hashing, and token encoding, kept separate from `jobs`. Sessions are a JWT in an HttpOnly cookie, validated against a `token_version` on the user row so a password change ends every session. FastAPI exposes a typed `current_user` dependency that protected routes consume.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic, PostgreSQL, argon2-cffi, PyJWT, pytest.

**Spec:** `docs/superpowers/specs/2026-08-24-candidate-profile-and-auth-design.md`

**Covers:** #38, #39, #40. Tracks 2 (profile) and 3 (CV) get their own plans.

## Global Constraints

- Python 3.12, `mypy --strict` over `app`, `scripts`, `tests`; `ruff` line length 100.
- Every migration must upgrade **and** downgrade. Alembic revision ids are at most 32 characters — the version column enforces it.
- Tests touching PostgreSQL are marked `pytest.mark.integration` and use the `database_url` fixture, which skips when `SKILLSYNC_TEST_DATABASE_URL` is unset.
- Coverage gate is 80% over `app`; the project has been running at 100% and should stay there.
- **Never log a password, a hash, a token, or a cookie value.** Never return a hash in a response.
- **No secret gets a usable default.** The session secret is required outside local/test and the application must refuse to start without it rather than fall back.
- Commit messages and PR text must never mention an AI, model, assistant, or tool.

---

### Task 1: User row and migration

**Files:**
- Create: `backend/app/modules/accounts/__init__.py`
- Create: `backend/app/modules/accounts/models.py`
- Create: `backend/alembic/versions/0011_add_users.py`
- Create: `backend/tests/modules/accounts/__init__.py`
- Test: `backend/tests/modules/accounts/test_models.py`

**Interfaces:**
- Consumes: `app.db.base.Base`
- Produces: `User` with `id: UUID`, `email: str`, `normalized_email: str`, `password_hash: str`, `is_active: bool`, `token_version: int`, `created_at`, `updated_at`; and `normalize_email(value: str) -> str`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/modules/accounts/test_models.py
import asyncio
from collections.abc import Awaitable, Callable

import pytest
from pydantic import PostgresDsn
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.db.session import Database
from app.modules.accounts.models import User, normalize_email

pytestmark = pytest.mark.integration


def run_database_test(
    database_url: PostgresDsn, test: Callable[[Database], Awaitable[None]]
) -> None:
    async def run() -> None:
        database = Database(database_url)
        try:
            async with database.session() as session:
                await session.execute(delete(User))
                await session.commit()
            await test(database)
        finally:
            async with database.session() as session:
                await session.execute(delete(User))
                await session.commit()
            await database.dispose()

    asyncio.run(run())


def test_normalize_email_lowercases_and_trims() -> None:
    assert normalize_email("  Ada@Example.COM ") == "ada@example.com"


def test_the_same_address_cannot_register_twice(database_url: PostgresDsn) -> None:
    async def test(database: Database) -> None:
        async with database.session() as session:
            session.add(User(email="Ada@Example.com", password_hash="x"))
            await session.commit()
        with pytest.raises(IntegrityError):
            async with database.session() as session:
                session.add(User(email="ada@example.COM", password_hash="y"))
                await session.commit()

    run_database_test(database_url, test)


def test_a_new_account_starts_active_at_version_one(database_url: PostgresDsn) -> None:
    async def test(database: Database) -> None:
        async with database.session() as session:
            session.add(User(email="grace@example.com", password_hash="x"))
            await session.commit()
        async with database.session() as session:
            user = (await session.execute(select(User))).scalars().one()
            assert user.is_active is True
            assert user.token_version == 1
            assert user.normalized_email == "grace@example.com"

    run_database_test(database_url, test)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/modules/accounts/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.modules.accounts'`

- [ ] **Step 3: Write the model**

```python
# backend/app/modules/accounts/models.py
"""Persistence for accounts.

The address a person types is kept as they typed it, and a normalised copy
carries the uniqueness constraint, so `Ada@Example.com` and `ada@example.com`
cannot both register.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.db.base import Base

EMAIL_LENGTH = 320
HASH_LENGTH = 255


def normalize_email(value: str) -> str:
    """The form uniqueness is enforced on."""
    return value.strip().lower()


class User(Base):
    """One account. Owns a profile, CVs, and sessions."""

    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("normalized_email", name="uq_users_normalized_email"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(EMAIL_LENGTH), nullable=False)
    normalized_email: Mapped[str] = mapped_column(String(EMAIL_LENGTH), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(HASH_LENGTH), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True,
                                            server_default="true")
    # Bumped to end every session at once. Normal logout clears the cookie and
    # leaves this alone; a password change, a disabled account, or an explicit
    # log-out-everywhere increments it and invalidates tokens already issued.
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1,
                                               server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    @validates("email")
    def derive_normalized_email(self, _key: str, email: str) -> str:
        self.normalized_email = normalize_email(email)
        return email
```

```python
# backend/alembic/versions/0011_add_users.py
"""Add users.

Revision ID: 0011_add_users
Revises: 0010_provenance_retired_at
"""

import sqlalchemy as sa
from alembic import op

revision = "0011_add_users"
down_revision = "0010_provenance_retired_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("normalized_email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("token_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("normalized_email", name="uq_users_normalized_email"),
    )


def downgrade() -> None:
    op.drop_table("users")
```

Confirm `down_revision` matches the current head: `cd backend && .venv/bin/alembic heads`. If it differs, use the reported value.

- [ ] **Step 4: Run tests and the migration both ways**

```bash
cd backend
.venv/bin/alembic upgrade head && .venv/bin/alembic downgrade -1 && .venv/bin/alembic upgrade head
.venv/bin/pytest tests/modules/accounts/test_models.py -v
.venv/bin/ruff check app tests && .venv/bin/ruff format --check app tests && .venv/bin/mypy
```
Expected: migration applies and reverses; tests PASS; lint and types clean.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/accounts backend/alembic/versions/0011_add_users.py backend/tests/modules/accounts
git commit -m "feat: add the account a candidate owns"
```

---

### Task 2: Password hashing

**Files:**
- Modify: `backend/pyproject.toml` (add `argon2-cffi`)
- Create: `backend/app/modules/accounts/passwords.py`
- Test: `backend/tests/modules/accounts/test_passwords.py`

**Interfaces:**
- Produces: `hash_password(plain: str) -> str`, `verify_password(plain: str, hashed: str) -> bool`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/modules/accounts/test_passwords.py
from app.modules.accounts.passwords import hash_password, verify_password


def test_a_hash_does_not_contain_the_password() -> None:
    hashed = hash_password("correct horse battery staple")
    assert "correct horse battery staple" not in hashed


def test_the_same_password_hashes_differently_every_time() -> None:
    assert hash_password("hunter2") != hash_password("hunter2")


def test_the_right_password_verifies() -> None:
    assert verify_password("hunter2", hash_password("hunter2")) is True


def test_the_wrong_password_does_not() -> None:
    assert verify_password("hunter3", hash_password("hunter2")) is False


def test_a_malformed_hash_is_a_failure_rather_than_a_crash() -> None:
    assert verify_password("hunter2", "not-a-hash") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/modules/accounts/test_passwords.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.modules.accounts.passwords'`

- [ ] **Step 3: Add the dependency and write the module**

In `backend/pyproject.toml`, add to `[project] dependencies`:

```toml
  "argon2-cffi>=25.1.0,<26.0.0",
```

Then `cd backend && .venv/bin/pip install -e .`

```python
# backend/app/modules/accounts/passwords.py
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
```

- [ ] **Step 4: Run tests**

```bash
cd backend && .venv/bin/pytest tests/modules/accounts/test_passwords.py -v
.venv/bin/ruff check app tests && .venv/bin/mypy
```
Expected: PASS, clean.

- [ ] **Step 5: Commit**

```bash
git add backend/pyproject.toml backend/app/modules/accounts/passwords.py backend/tests/modules/accounts/test_passwords.py
git commit -m "feat: hash passwords with argon2id"
```

---

### Task 3: Session settings that refuse to start insecure

**Files:**
- Modify: `backend/app/core/config.py`
- Test: `backend/tests/core/test_config.py`

**Interfaces:**
- Produces: `Settings.session_secret: str`, `Settings.session_lifetime_minutes: int`, `Settings.session_cookie_secure: bool`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/core/test_config.py`:

```python
import pytest

from app.core.config import Environment, Settings


def test_local_gets_a_development_secret() -> None:
    assert Settings(environment=Environment.LOCAL).session_secret


def test_production_refuses_to_start_without_a_secret() -> None:
    with pytest.raises(ValueError, match="session secret"):
        Settings(environment=Environment.PRODUCTION)


def test_production_accepts_a_supplied_secret() -> None:
    settings = Settings(environment=Environment.PRODUCTION, session_secret="s" * 32)
    assert settings.session_secret == "s" * 32
    assert settings.session_cookie_secure is True


def test_the_session_lasts_an_hour_by_default() -> None:
    assert Settings(environment=Environment.LOCAL).session_lifetime_minutes == 60
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/core/test_config.py -v`
Expected: FAIL — `Settings` has no `session_secret`.

- [ ] **Step 3: Extend Settings**

In `backend/app/core/config.py`, add the fields inside `Settings` after `database_url`:

```python
    # Empty means unset. A usable default here would be a production
    # credential in the repository, so staging and production refuse to start
    # without one rather than quietly signing tokens with a known key.
    session_secret: str = ""
    session_lifetime_minutes: int = 60

    @property
    def session_cookie_secure(self) -> bool:
        """Whether the cookie is HTTPS-only. Off locally so development works."""
        return self.environment not in (Environment.LOCAL, Environment.TEST)

    @model_validator(mode="after")
    def require_a_session_secret_outside_development(self) -> "Settings":
        if self.session_secret:
            return self
        if self.environment in (Environment.LOCAL, Environment.TEST):
            object.__setattr__(self, "session_secret", "development-only-session-secret")
            return self
        raise ValueError("a session secret is required outside local and test")
```

Add `model_validator` to the pydantic import at the top of the file:

```python
from pydantic import PostgresDsn, field_validator, model_validator
```

- [ ] **Step 4: Run tests**

```bash
cd backend && .venv/bin/pytest tests/core -v && .venv/bin/ruff check app tests && .venv/bin/mypy
```
Expected: PASS, clean.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/config.py backend/tests/core/test_config.py
git commit -m "feat: refuse to start without a session secret outside development"
```

---

### Task 4: Token encoding and decoding

**Files:**
- Modify: `backend/pyproject.toml` (add `pyjwt`)
- Create: `backend/app/modules/accounts/tokens.py`
- Test: `backend/tests/modules/accounts/test_tokens.py`

**Interfaces:**
- Produces: `SessionClaims(user_id: UUID, token_version: int)`, `issue_token(claims, *, secret, lifetime_minutes, now) -> str`, `read_token(token, *, secret, now) -> SessionClaims | None`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/modules/accounts/test_tokens.py
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.modules.accounts.tokens import SessionClaims, issue_token, read_token

SECRET = "s" * 32
NOW = datetime(2026, 8, 24, 12, tzinfo=UTC)


def test_a_token_round_trips() -> None:
    claims = SessionClaims(user_id=uuid4(), token_version=3)
    token = issue_token(claims, secret=SECRET, lifetime_minutes=60, now=NOW)
    assert read_token(token, secret=SECRET, now=NOW) == claims


def test_an_expired_token_is_refused() -> None:
    token = issue_token(
        SessionClaims(user_id=uuid4(), token_version=1),
        secret=SECRET, lifetime_minutes=60, now=NOW,
    )
    assert read_token(token, secret=SECRET, now=NOW + timedelta(minutes=61)) is None


def test_a_token_signed_with_another_secret_is_refused() -> None:
    token = issue_token(
        SessionClaims(user_id=uuid4(), token_version=1),
        secret=SECRET, lifetime_minutes=60, now=NOW,
    )
    assert read_token(token, secret="other" * 8, now=NOW) is None


def test_rubbish_is_refused_rather_than_raising() -> None:
    assert read_token("not.a.token", secret=SECRET, now=NOW) is None
    assert read_token("", secret=SECRET, now=NOW) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/modules/accounts/test_tokens.py -v`
Expected: FAIL — no module `app.modules.accounts.tokens`.

- [ ] **Step 3: Add the dependency and write the module**

In `backend/pyproject.toml` `[project] dependencies`, add:

```toml
  "pyjwt>=2.10.0,<3.0.0",
```

Then `cd backend && .venv/bin/pip install -e .`

```python
# backend/app/modules/accounts/tokens.py
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


def issue_token(
    claims: SessionClaims, *, secret: str, lifetime_minutes: int, now: datetime
) -> str:
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
            options={"require": ["sub", "ver", "exp"]},
        )
    except jwt.InvalidTokenError:
        return None
    if int(payload["exp"]) < int(now.timestamp()):
        return None
    try:
        return SessionClaims(user_id=UUID(payload["sub"]), token_version=int(payload["ver"]))
    except (ValueError, TypeError):
        return None
```

Note: PyJWT checks `exp` against the real clock. The explicit comparison above is what lets tests control `now` without freezing time globally.

- [ ] **Step 4: Run tests**

```bash
cd backend && .venv/bin/pytest tests/modules/accounts/test_tokens.py -v
.venv/bin/ruff check app tests && .venv/bin/mypy
```
Expected: PASS, clean.

- [ ] **Step 5: Commit**

```bash
git add backend/pyproject.toml backend/app/modules/accounts/tokens.py backend/tests/modules/accounts/test_tokens.py
git commit -m "feat: issue and read session tokens"
```

---

### Task 5: Registration

**Files:**
- Create: `backend/app/modules/accounts/schemas.py`
- Create: `backend/app/modules/accounts/service.py`
- Create: `backend/app/api/routes/accounts.py`
- Modify: `backend/app/api/router.py`
- Test: `backend/tests/api/test_accounts.py`

**Interfaces:**
- Consumes: `User`, `normalize_email`, `hash_password`
- Produces: `RegistrationRequest(email, password)`, `AccountRead(id, email)`, `EmailAlreadyRegistered`, `register(session, request) -> User`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/api/test_accounts.py
import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

CREDENTIALS = {"email": "Ada@Example.com", "password": "correct horse battery staple"}


def test_registration_returns_the_account_without_credentials(
    migrated_client: TestClient,
) -> None:
    response = migrated_client.post("/api/v1/accounts", json=CREDENTIALS)
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "Ada@Example.com"
    assert "id" in body
    assert "password" not in body
    assert "password_hash" not in body


def test_the_same_address_cannot_register_twice(migrated_client: TestClient) -> None:
    assert migrated_client.post("/api/v1/accounts", json=CREDENTIALS).status_code == 201
    again = migrated_client.post(
        "/api/v1/accounts", json={"email": "ada@example.COM", "password": "another one entirely"}
    )
    assert again.status_code == 409
    assert "password" not in again.text


def test_a_short_password_is_refused(migrated_client: TestClient) -> None:
    response = migrated_client.post(
        "/api/v1/accounts", json={"email": "grace@example.com", "password": "short"}
    )
    assert response.status_code == 422
```

Add a `migrated_client` fixture to `backend/tests/conftest.py`, after the `database_url` fixture:

```python
@pytest.fixture
def migrated_client(database_url: PostgresDsn) -> Iterator[TestClient]:
    """A client wired to a migrated database, with accounts cleared around it."""
    from sqlalchemy import create_engine, text

    synchronous = str(database_url).replace("postgresql+psycopg", "postgresql+psycopg")
    engine = create_engine(synchronous)
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM users"))
    settings = Settings(environment=Environment.TEST, database_url=database_url)
    with TestClient(create_app(settings)) as test_client:
        yield test_client
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM users"))
    engine.dispose()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/api/test_accounts.py -v`
Expected: FAIL — 404, the route does not exist.

- [ ] **Step 3: Write schemas, service, and route**

```python
# backend/app/modules/accounts/schemas.py
"""The validated shapes accounts are created and read through."""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

MINIMUM_PASSWORD_LENGTH = 12
MAXIMUM_PASSWORD_LENGTH = 200


class RegistrationRequest(BaseModel):
    """What a visitor supplies to create an account."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    # A length floor rather than a character-class rule: length is what
    # actually resists guessing, and composition rules mostly produce
    # predictable substitutions.
    password: Annotated[
        str, Field(min_length=MINIMUM_PASSWORD_LENGTH, max_length=MAXIMUM_PASSWORD_LENGTH)
    ]


class AccountRead(BaseModel):
    """What is safe to send back. No credential material appears here at all."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
```

`EmailStr` needs `email-validator`. Add to `backend/pyproject.toml` `[project] dependencies`:

```toml
  "email-validator>=2.2.0,<3.0.0",
```

Then `cd backend && .venv/bin/pip install -e .`

```python
# backend/app/modules/accounts/service.py
"""Account operations, kept out of the route so they can be tested directly."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.accounts.models import User, normalize_email
from app.modules.accounts.passwords import hash_password
from app.modules.accounts.schemas import RegistrationRequest


class EmailAlreadyRegistered(Exception):
    """Raised rather than returned, so a caller cannot forget to check."""


async def register(session: AsyncSession, request: RegistrationRequest) -> User:
    normalized = normalize_email(request.email)
    existing = await session.execute(select(User).where(User.normalized_email == normalized))
    if existing.scalars().first() is not None:
        raise EmailAlreadyRegistered(normalized)

    user = User(email=request.email, password_hash=hash_password(request.password))
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user
```

```python
# backend/app/api/routes/accounts.py
"""Registration."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_database_session
from app.modules.accounts.schemas import AccountRead, RegistrationRequest
from app.modules.accounts.service import EmailAlreadyRegistered, register

router = APIRouter(prefix="/api/v1/accounts", tags=["accounts"])


@router.post("", response_model=AccountRead, status_code=status.HTTP_201_CREATED)
async def create_account(
    request: RegistrationRequest,
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> AccountRead:
    try:
        user = await register(session, request)
    except EmailAlreadyRegistered:
        # Deliberately the same wording whatever went wrong, and no echo of the
        # address, so this cannot be used to enumerate who has an account.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="that account cannot be created"
        ) from None
    return AccountRead.model_validate(user)
```

In `backend/app/api/router.py`:

```python
from app.api.routes import accounts, health, jobs

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(jobs.router)
api_router.include_router(accounts.router)
```

- [ ] **Step 4: Run tests**

```bash
cd backend && .venv/bin/pytest tests/api/test_accounts.py -v
.venv/bin/ruff check app tests && .venv/bin/ruff format --check app tests && .venv/bin/mypy
```
Expected: PASS, clean.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/accounts backend/app/api/routes/accounts.py backend/app/api/router.py backend/pyproject.toml backend/tests
git commit -m "feat: let a visitor create an account"
```

---

### Task 6: Login, and the cookie it sets

**Files:**
- Modify: `backend/app/modules/accounts/service.py`
- Modify: `backend/app/modules/accounts/schemas.py`
- Modify: `backend/app/api/routes/accounts.py`
- Test: `backend/tests/api/test_login.py`

**Interfaces:**
- Consumes: `verify_password`, `issue_token`, `SessionClaims`, `Settings`
- Produces: `authenticate(session, email, password) -> User | None`. The cookie name lives in `app.api.dependencies` as `SESSION_COOKIE` and is imported, not redeclared — two copies of a cookie name is a bug waiting for one of them to change.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/api/test_login.py
import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

CREDENTIALS = {"email": "ada@example.com", "password": "correct horse battery staple"}


def register(client: TestClient) -> None:
    assert client.post("/api/v1/accounts", json=CREDENTIALS).status_code == 201


def test_login_sets_an_httponly_cookie(migrated_client: TestClient) -> None:
    register(migrated_client)
    response = migrated_client.post("/api/v1/sessions", json=CREDENTIALS)
    assert response.status_code == 204
    cookie = response.headers["set-cookie"]
    assert "session=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie


def test_the_token_never_appears_in_the_body(migrated_client: TestClient) -> None:
    register(migrated_client)
    response = migrated_client.post("/api/v1/sessions", json=CREDENTIALS)
    assert response.content == b""


def test_a_wrong_password_is_refused(migrated_client: TestClient) -> None:
    register(migrated_client)
    response = migrated_client.post(
        "/api/v1/sessions", json={"email": "ada@example.com", "password": "not the password"}
    )
    assert response.status_code == 401


def test_an_unknown_address_fails_exactly_like_a_wrong_password(
    migrated_client: TestClient,
) -> None:
    register(migrated_client)
    unknown = migrated_client.post(
        "/api/v1/sessions", json={"email": "nobody@example.com", "password": "whatever it is"}
    )
    wrong = migrated_client.post(
        "/api/v1/sessions", json={"email": "ada@example.com", "password": "not the password"}
    )
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/api/test_login.py -v`
Expected: FAIL — 404 on `/api/v1/sessions`.

- [ ] **Step 3: Implement**

Append to `backend/app/modules/accounts/schemas.py`:

```python
class LoginRequest(BaseModel):
    """Credentials offered at login. Deliberately not length-validated: the
    rules that apply when choosing a password must not leak into checking one,
    or a rejected length becomes a hint about the stored value."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str
```

Append to `backend/app/modules/accounts/service.py`:

```python
from app.modules.accounts.passwords import hash_password, verify_password

# A hash to check against when no account matches, so a missing address costs
# the same time as a wrong password and cannot be told apart by timing.
_ABSENT_ACCOUNT_HASH = hash_password("no account with this address exists")


async def authenticate(session: AsyncSession, email: str, password: str) -> User | None:
    """The account these credentials belong to, or None."""
    normalized = normalize_email(email)
    found = await session.execute(select(User).where(User.normalized_email == normalized))
    user = found.scalars().first()
    if user is None:
        verify_password(password, _ABSENT_ACCOUNT_HASH)
        return None
    if not verify_password(password, user.password_hash):
        return None
    if not user.is_active:
        return None
    return user
```

Append to `backend/app/api/routes/accounts.py`:

```python
from datetime import UTC, datetime

from fastapi import Response

from app.api.dependencies import SESSION_COOKIE, get_application_settings
from app.core.config import Settings
from app.modules.accounts.schemas import LoginRequest
from app.modules.accounts.service import authenticate
from app.modules.accounts.tokens import SessionClaims, issue_token

sessions_router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


@sessions_router.post("", status_code=status.HTTP_204_NO_CONTENT)
async def log_in(
    request: LoginRequest,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_database_session)],
    settings: Annotated[Settings, Depends(get_application_settings)],
) -> None:
    user = await authenticate(session, request.email, request.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="those credentials were not accepted"
        )
    token = issue_token(
        SessionClaims(user_id=user.id, token_version=user.token_version),
        secret=settings.session_secret,
        lifetime_minutes=settings.session_lifetime_minutes,
        now=datetime.now(UTC),
    )
    # The token goes only into the cookie. Putting it in the body as well would
    # hand it to any script on the page, which is what HttpOnly is preventing.
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        max_age=settings.session_lifetime_minutes * 60,
        path="/",
    )
```

Add to `backend/app/api/dependencies.py`:

```python
from app.core.config import Settings

# Declared here because both the route that sets it and the dependency that
# reads it need the same name, and two copies is one rename away from a bug.
SESSION_COOKIE = "session"


def get_application_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)
```

Confirm `create_app` stores settings on `app.state.settings`; if it does not, add that in `backend/app/main.py` alongside the database.

Register the router in `backend/app/api/router.py`:

```python
api_router.include_router(accounts.sessions_router)
```

- [ ] **Step 4: Run tests**

```bash
cd backend && .venv/bin/pytest tests/api -v
.venv/bin/ruff check app tests && .venv/bin/mypy
```
Expected: PASS, clean.

- [ ] **Step 5: Commit**

```bash
git add backend/app backend/tests
git commit -m "feat: sign a candidate in and carry it in a cookie"
```

---

### Task 7: The current-user dependency

**Files:**
- Modify: `backend/app/api/dependencies.py`
- Create: `backend/app/api/routes/me.py`
- Modify: `backend/app/api/router.py`
- Test: `backend/tests/api/test_current_user.py`

**Interfaces:**
- Produces: `current_user(...) -> User` (401 when absent or stale), `CurrentUser = Annotated[User, Depends(current_user)]`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/api/test_current_user.py
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.integration

CREDENTIALS = {"email": "ada@example.com", "password": "correct horse battery staple"}


def sign_in(client: TestClient) -> None:
    assert client.post("/api/v1/accounts", json=CREDENTIALS).status_code == 201
    assert client.post("/api/v1/sessions", json=CREDENTIALS).status_code == 204


def test_a_signed_in_candidate_is_recognised(migrated_client: TestClient) -> None:
    sign_in(migrated_client)
    response = migrated_client.get("/api/v1/me")
    assert response.status_code == 200
    assert response.json()["email"] == "ada@example.com"


def test_no_cookie_is_unauthorised(migrated_client: TestClient) -> None:
    assert migrated_client.get("/api/v1/me").status_code == 401


def test_a_forged_cookie_is_unauthorised(migrated_client: TestClient) -> None:
    migrated_client.cookies.set("session", "not.a.real.token")
    assert migrated_client.get("/api/v1/me").status_code == 401


def test_bumping_the_version_ends_the_session(
    migrated_client: TestClient, database_url: object
) -> None:
    sign_in(migrated_client)
    assert migrated_client.get("/api/v1/me").status_code == 200
    engine = create_engine(str(database_url))
    with engine.begin() as connection:
        connection.execute(text("UPDATE users SET token_version = token_version + 1"))
    engine.dispose()
    assert migrated_client.get("/api/v1/me").status_code == 401


def test_a_disabled_account_is_refused(
    migrated_client: TestClient, database_url: object
) -> None:
    sign_in(migrated_client)
    engine = create_engine(str(database_url))
    with engine.begin() as connection:
        connection.execute(text("UPDATE users SET is_active = false"))
    engine.dispose()
    assert migrated_client.get("/api/v1/me").status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/api/test_current_user.py -v`
Expected: FAIL — 404 on `/api/v1/me`.

- [ ] **Step 3: Implement**

Append to `backend/app/api/dependencies.py`:

```python
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select

from app.modules.accounts.models import User
from app.modules.accounts.tokens import read_token

_UNAUTHORISED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="not signed in"
)


async def current_user(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_database_session)],
    settings: Annotated[Settings, Depends(get_application_settings)],
) -> User:
    """The signed-in account, or a 401.

    Every rejection is the same response. A caller learning why a token failed
    learns whether an account exists and whether it is disabled, which is not
    information an unauthenticated request should be able to buy.
    """
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise _UNAUTHORISED
    claims = read_token(token, secret=settings.session_secret, now=datetime.now(UTC))
    if claims is None:
        raise _UNAUTHORISED
    found = await session.execute(select(User).where(User.id == claims.user_id))
    user = found.scalars().first()
    if user is None or not user.is_active:
        raise _UNAUTHORISED
    # The generation check. A token issued before a password change carries the
    # old number and stops here.
    if user.token_version != claims.token_version:
        raise _UNAUTHORISED
    return user


CurrentUser = Annotated[User, Depends(current_user)]
```

```python
# backend/app/api/routes/me.py
"""The signed-in account. Also the smallest possible proof the session works."""

from fastapi import APIRouter

from app.api.dependencies import CurrentUser
from app.modules.accounts.schemas import AccountRead

router = APIRouter(prefix="/api/v1/me", tags=["accounts"])


@router.get("", response_model=AccountRead)
async def read_me(user: CurrentUser) -> AccountRead:
    return AccountRead.model_validate(user)
```

In `backend/app/api/router.py`, import `me` and `api_router.include_router(me.router)`.

- [ ] **Step 4: Run tests**

```bash
cd backend && .venv/bin/pytest tests/api -v
.venv/bin/ruff check app tests && .venv/bin/mypy
```
Expected: PASS, clean.

- [ ] **Step 5: Commit**

```bash
git add backend/app backend/tests
git commit -m "feat: recognise the signed-in candidate on later requests"
```

---

### Task 8: Logging out, here and everywhere

**Files:**
- Modify: `backend/app/api/routes/accounts.py`
- Modify: `backend/app/modules/accounts/service.py`
- Test: `backend/tests/api/test_logout.py`

**Interfaces:**
- Produces: `DELETE /api/v1/sessions` (this device), `DELETE /api/v1/sessions/all` (every device), `end_all_sessions(session, user) -> None`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/api/test_logout.py
import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

CREDENTIALS = {"email": "ada@example.com", "password": "correct horse battery staple"}


def sign_in(client: TestClient) -> None:
    assert client.post("/api/v1/accounts", json=CREDENTIALS).status_code == 201
    assert client.post("/api/v1/sessions", json=CREDENTIALS).status_code == 204


def test_logging_out_clears_the_cookie(migrated_client: TestClient) -> None:
    sign_in(migrated_client)
    response = migrated_client.delete("/api/v1/sessions")
    assert response.status_code == 204
    assert migrated_client.get("/api/v1/me").status_code == 401


def test_logging_out_here_leaves_another_device_signed_in(
    migrated_client: TestClient,
) -> None:
    """A second client stands in for a second device: same account, own cookie."""
    sign_in(migrated_client)
    other = TestClient(migrated_client.app)
    assert other.post("/api/v1/sessions", json=CREDENTIALS).status_code == 204
    assert migrated_client.delete("/api/v1/sessions").status_code == 204
    assert other.get("/api/v1/me").status_code == 200


def test_logging_out_everywhere_ends_the_other_device_too(
    migrated_client: TestClient,
) -> None:
    sign_in(migrated_client)
    other = TestClient(migrated_client.app)
    assert other.post("/api/v1/sessions", json=CREDENTIALS).status_code == 204
    assert migrated_client.delete("/api/v1/sessions/all").status_code == 204
    assert other.get("/api/v1/me").status_code == 401


def test_logging_out_everywhere_needs_a_session(migrated_client: TestClient) -> None:
    assert migrated_client.delete("/api/v1/sessions/all").status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/api/test_logout.py -v`
Expected: FAIL — 405 or 404 on `DELETE /api/v1/sessions`.

- [ ] **Step 3: Implement**

Append to `backend/app/modules/accounts/service.py`:

```python
async def end_all_sessions(session: AsyncSession, user: User) -> None:
    """Invalidate every token already issued for this account.

    Strong enough that it is reserved for the cases that want it: a password
    change, a disabled account, and an explicit request to sign out everywhere.
    Ordinary logout clears one cookie and leaves other devices alone.
    """
    user.token_version += 1
    session.add(user)
    await session.commit()
```

Append to `backend/app/api/routes/accounts.py`:

```python
from app.api.dependencies import CurrentUser
from app.modules.accounts.service import end_all_sessions


@sessions_router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def log_out(response: Response, settings: Annotated[Settings, Depends(get_application_settings)]) -> None:
    """This device only. A token stolen before now survives until it expires,
    which is why the lifetime is short rather than why this is stronger."""
    response.delete_cookie(
        SESSION_COOKIE, path="/", httponly=True,
        secure=settings.session_cookie_secure, samesite="lax",
    )


@sessions_router.delete("/all", status_code=status.HTTP_204_NO_CONTENT)
async def log_out_everywhere(
    user: CurrentUser,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_database_session)],
    settings: Annotated[Settings, Depends(get_application_settings)],
) -> None:
    await end_all_sessions(session, user)
    response.delete_cookie(
        SESSION_COOKIE, path="/", httponly=True,
        secure=settings.session_cookie_secure, samesite="lax",
    )
```

- [ ] **Step 4: Run the whole suite with coverage**

```bash
cd backend && .venv/bin/pytest -v
.venv/bin/ruff check app tests scripts && .venv/bin/ruff format --check app tests scripts && .venv/bin/mypy
```
Expected: all PASS, coverage gate met, lint and types clean.

- [ ] **Step 5: Commit**

```bash
git add backend/app backend/tests
git commit -m "feat: end a session here, or everywhere"
```

---

## Verification before opening the PR

- [ ] `cd backend && .venv/bin/pytest` — full suite green, coverage gate met
- [ ] `.venv/bin/alembic upgrade head && .venv/bin/alembic downgrade -1 && .venv/bin/alembic upgrade head`
- [ ] `.venv/bin/ruff check app tests scripts && .venv/bin/ruff format --check app tests scripts && .venv/bin/mypy`
- [ ] `git grep -nE "password|token|secret" backend/app | grep -iE "log|print"` returns nothing — no credential material reaches a log
- [ ] No `.env` file is created and no secret is committed
- [ ] All CI checks, SonarCloud included, are green **before** merging

## What this plan does not do

- No profile. `#99` and `#100` are their own plan and depend only on Task 1.
- No CV handling. `#41`–`#45` are their own plan and depend on Task 7.
- No refresh tokens. The spec puts them out of the first version deliberately.
- No roles or permissions. `#40` scopes them out and nothing yet needs them.
