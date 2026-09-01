"""Account operations, kept out of the route so they can be tested directly."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.accounts.models import User, normalize_email
from app.modules.accounts.passwords import (
    hash_password,
    hash_password_in_thread,
    verify_password_in_thread,
)
from app.modules.accounts.schemas import RegistrationRequest
from app.modules.cvs.models import CV
from app.modules.cvs.storage import CVStorage


class EmailAlreadyRegistered(Exception):
    """Raised rather than returned, so a caller cannot forget to check."""


class PasswordNotConfirmed(Exception):
    """The password offered to authorise something destructive did not match."""


async def register(session: AsyncSession, request: RegistrationRequest) -> User:
    normalized = normalize_email(request.email)
    existing = await session.execute(select(User).where(User.normalized_email == normalized))
    if existing.scalars().first() is not None:
        raise EmailAlreadyRegistered(normalized)

    user = User(email=request.email, password_hash=await hash_password_in_thread(request.password))
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
        await verify_password_in_thread(password, _ABSENT_ACCOUNT_HASH)
        return None
    if not await verify_password_in_thread(password, user.password_hash):
        return None
    if not user.is_active:
        return None
    return user


async def end_all_sessions(session: AsyncSession, user: User) -> None:
    """Invalidate every token already issued for this account.

    Strong enough that it is reserved for the cases that want it: a password
    change, a disabled account, and an explicit request to sign out everywhere.
    Ordinary logout clears one cookie and leaves other devices alone.
    """
    user.token_version += 1
    session.add(user)
    await session.commit()


async def change_password(
    session: AsyncSession,
    *,
    user: User,
    current_password: str,
    new_password: str,
) -> int:
    """Replace an account's password and end every session it had.

    The current password is re-stated because a cookie is enough to read and to
    write, and not enough to replace the credential that issues cookies.

    Returns the token version the caller's own device must be re-issued under.
    Read before the commit rather than after it, so the number handed back is
    the one that was stored and never a re-read that could have moved on.
    """
    if not await verify_password_in_thread(current_password, user.password_hash):
        raise PasswordNotConfirmed

    user.password_hash = await hash_password_in_thread(new_password)
    user.token_version += 1
    version = user.token_version
    session.add(user)
    await session.commit()
    return version


async def delete_account(
    session: AsyncSession,
    storage: CVStorage,
    *,
    user: User,
    password: str,
) -> None:
    """Delete an account and everything it owns.

    The password is re-stated because this is irreversible: a cookie is enough
    to read and to write, and not enough to destroy.

    The profile, its skills and the CV rows go with the user row, which the
    schema already says by cascading them. The stored files do not: a database
    cannot reach a filesystem, so they are removed here, and before the row —
    an account that still exists can be deleted again, while files nothing
    points at are what the upload policy promises not to keep.

    The account is taken before anything hanging off it is read. Without that,
    an upload committing while the files are being deleted is never covered: its
    key was not in the list, and the cascade reaps its row, leaving a file
    nothing names and nothing can ever name again. Holding the row makes that
    insert wait — every CV row takes a lock on its owner to exist — and then
    fail against an account that is gone, which the upload path already cleans
    up after.
    """
    if not await verify_password_in_thread(password, user.password_hash):
        raise PasswordNotConfirmed

    held = await session.scalar(select(User).where(User.id == user.id).with_for_update())
    if held is None:
        return

    keys = (await session.scalars(select(CV.storage_key).where(CV.owner_id == user.id))).all()
    for key in keys:
        await storage.delete(key)

    await session.delete(held)
    await session.commit()
