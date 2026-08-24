"""Accounts domain module."""

from app.modules.accounts.models import User, normalize_email

__all__ = [
    "User",
    "normalize_email",
]
