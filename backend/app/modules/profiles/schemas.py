"""Validated candidate-profile API contracts."""

from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.jobs.domain import EmploymentType, WorkplaceType

ShortText = Annotated[str, Field(min_length=1, max_length=255)]


class CandidateProfileUpdate(BaseModel):
    """Any canonical profile fields supplied by either onboarding route."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    display_name: ShortText | None = None
    location: ShortText | None = None
    workplace_types: Annotated[list[WorkplaceType], Field(min_length=1)] | None = None
    employment_types: Annotated[list[EmploymentType], Field(min_length=1)] | None = None
    headline: ShortText | None = None
    summary: str | None = None
    years_experience: Annotated[int, Field(ge=0)] | None = None

    @field_validator("workplace_types", "employment_types")
    @classmethod
    def reject_duplicate_preferences[PreferenceT](
        cls, values: list[PreferenceT] | None
    ) -> list[PreferenceT] | None:
        if values is not None and len(values) != len(set(values)):
            raise ValueError("preference values must be unique")
        return values

    @field_validator("headline")
    @classmethod
    def keep_headline_on_one_line(cls, headline: str | None) -> str | None:
        if headline is not None and ("\n" in headline or "\r" in headline):
            raise ValueError("headline must be one line")
        return headline

    @model_validator(mode="after")
    def require_a_change(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("at least one profile field is required")
        required_fields = {
            "display_name",
            "location",
            "workplace_types",
            "employment_types",
        }
        if any(
            field in self.model_fields_set and getattr(self, field) is None
            for field in required_fields
        ):
            raise ValueError("required profile fields cannot be cleared")
        return self


class CandidateProfileRead(BaseModel):
    """The route-neutral candidate description returned to its owner."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    display_name: str | None
    location: str | None
    workplace_types: list[WorkplaceType] | None
    employment_types: list[EmploymentType] | None
    headline: str | None
    summary: str | None
    years_experience: int | None
    profile_complete: bool
    created_at: datetime
    updated_at: datetime
