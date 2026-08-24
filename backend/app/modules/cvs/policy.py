"""Security policy for accepting a CV before storage or parsing.

The client-supplied name and media type are corroborating metadata only. The
file signature decides the format, and later PDF parsing must still treat the
whole document as hostile input.
"""

import unicodedata
from dataclasses import dataclass
from enum import StrEnum

DEFAULT_CV_MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_CLIENT_FILENAME_LENGTH = 255
PDF_MAGIC = b"%PDF-"
PDF_MEDIA_TYPE = "application/pdf"


class CVFormat(StrEnum):
    PDF = "pdf"


class UploadRejectionReason(StrEnum):
    INVALID_FILENAME = "invalid_filename"
    EMPTY_FILE = "empty_file"
    FILE_TOO_LARGE = "file_too_large"
    UNSUPPORTED_MEDIA_TYPE = "unsupported_media_type"
    UNSUPPORTED_CONTENT = "unsupported_content"


class CVUploadRejected(ValueError):
    """An expected boundary rejection with no untrusted value in its message."""

    def __init__(self, reason: UploadRejectionReason, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class AcceptedCVUpload:
    """Validated metadata safe to pass to the storage stage.

    `client_filename` remains display metadata. It must never become a storage
    path or parser option.
    """

    client_filename: str
    format: CVFormat
    media_type: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class CVUploadPolicy:
    max_bytes: int = DEFAULT_CV_MAX_UPLOAD_BYTES
    allowed_formats: frozenset[CVFormat] = frozenset({CVFormat.PDF})

    def __post_init__(self) -> None:
        if self.max_bytes < 1:
            raise ValueError("CV upload size limit must be positive")
        if not self.allowed_formats:
            raise ValueError("at least one CV format must be allowed")

    def validate(
        self,
        *,
        client_filename: str | None,
        declared_media_type: str | None,
        size_bytes: int,
        initial_bytes: bytes,
    ) -> AcceptedCVUpload:
        """Validate boundary metadata and a bounded content-signature sample."""
        filename = _validate_filename(client_filename)
        _validate_size(size_bytes, max_bytes=self.max_bytes)

        if declared_media_type != PDF_MEDIA_TYPE:
            raise CVUploadRejected(
                UploadRejectionReason.UNSUPPORTED_MEDIA_TYPE,
                "the upload must declare the application/pdf media type",
            )
        if not initial_bytes.startswith(PDF_MAGIC):
            raise CVUploadRejected(
                UploadRejectionReason.UNSUPPORTED_CONTENT,
                "the upload content is not a supported PDF",
            )
        return AcceptedCVUpload(
            client_filename=filename,
            format=CVFormat.PDF,
            media_type=PDF_MEDIA_TYPE,
            size_bytes=size_bytes,
        )


def _validate_filename(client_filename: str | None) -> str:
    if client_filename is None:
        _reject_filename()

    assert client_filename is not None
    has_forbidden_character = any(
        character in "/\\" or unicodedata.category(character).startswith("C")
        for character in client_filename
    )
    if (
        not client_filename
        or client_filename != client_filename.strip()
        or len(client_filename) > MAX_CLIENT_FILENAME_LENGTH
        or has_forbidden_character
    ):
        _reject_filename()

    stem, separator, extension = client_filename.rpartition(".")
    if not separator or not stem or extension.casefold() != CVFormat.PDF.value:
        _reject_filename()
    return client_filename


def _reject_filename() -> None:
    raise CVUploadRejected(
        UploadRejectionReason.INVALID_FILENAME,
        "the upload filename must be a safe PDF filename",
    )


def _validate_size(size_bytes: int, *, max_bytes: int) -> None:
    if size_bytes < 1:
        raise CVUploadRejected(UploadRejectionReason.EMPTY_FILE, "the upload is empty")
    if size_bytes > max_bytes:
        raise CVUploadRejected(
            UploadRejectionReason.FILE_TOO_LARGE,
            "the upload exceeds the configured size limit",
        )
