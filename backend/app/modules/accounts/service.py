"""Account operations, kept out of the route so they can be tested directly."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.accounts.models import User, normalize_email
from app.modules.accounts.passwords import hash_password, verify_password
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
    try:
        await session.commit()
    except IntegrityError:
        # The pre-check above only catches an address that was already
        # committed. A second registration for the same address that reaches
        # this commit before the first one lands still slips past it, and
        # hits the unique constraint here instead -- the window this closes.
        await session.rollback()
        raise EmailAlreadyRegistered(normalized) from None
    await session.refresh(user)
    return user


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
