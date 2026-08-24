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
