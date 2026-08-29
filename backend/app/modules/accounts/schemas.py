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


class LoginRequest(BaseModel):
    """Credentials offered at login. Deliberately not length-validated: the
    rules that apply when choosing a password must not leak into checking one,
    or a rejected length becomes a hint about the stored value."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str


class AccountDeletionRequest(BaseModel):
    """The password, re-stated to authorise deleting the account.

    A cookie is enough to read and to write; it is not enough to destroy. Asked
    for here rather than by the route so the rule travels with the shape.
    """

    model_config = ConfigDict(extra="forbid")

    password: str
