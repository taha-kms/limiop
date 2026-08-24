import pytest

from app.modules.cvs.policy import (
    MAX_CLIENT_FILENAME_LENGTH,
    PDF_MAGIC,
    CVFormat,
    CVUploadPolicy,
    CVUploadRejected,
    UploadRejectionReason,
)


def valid_upload(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "client_filename": "candidate.cv.pdf",
        "declared_media_type": "application/pdf",
        "size_bytes": 1024,
        "initial_bytes": PDF_MAGIC + b"1.7",
    }
    values.update(overrides)
    return values


def reject(**overrides: object) -> CVUploadRejected:
    with pytest.raises(CVUploadRejected) as raised:
        CVUploadPolicy().validate(**valid_upload(**overrides))  # type: ignore[arg-type]
    return raised.value


def test_a_pdf_is_identified_from_its_content_signature() -> None:
    accepted = CVUploadPolicy().validate(**valid_upload())  # type: ignore[arg-type]

    assert accepted.client_filename == "candidate.cv.pdf"
    assert accepted.format is CVFormat.PDF
    assert accepted.media_type == "application/pdf"
    assert accepted.size_bytes == 1024


def test_the_exact_configured_size_limit_is_accepted() -> None:
    accepted = CVUploadPolicy(max_bytes=1024).validate(
        **valid_upload(size_bytes=1024)  # type: ignore[arg-type]
    )
    assert accepted.size_bytes == 1024


@pytest.mark.parametrize("size_bytes", [0, -1])
def test_an_empty_or_impossible_size_is_rejected(size_bytes: int) -> None:
    assert reject(size_bytes=size_bytes).reason is UploadRejectionReason.EMPTY_FILE


def test_one_byte_over_the_limit_is_rejected_without_echoing_the_name() -> None:
    filename = "private-candidate-name.pdf"
    with pytest.raises(CVUploadRejected) as raised:
        CVUploadPolicy(max_bytes=1024).validate(
            **valid_upload(client_filename=filename, size_bytes=1025)  # type: ignore[arg-type]
        )

    assert raised.value.reason is UploadRejectionReason.FILE_TOO_LARGE
    assert filename not in str(raised.value)


@pytest.mark.parametrize(
    "client_filename",
    [
        None,
        "",
        ".pdf",
        "resume",
        "resume.txt",
        "resume.pdf.exe",
        " resume.pdf",
        "resume.pdf ",
        "../resume.pdf",
        "..\\resume.pdf",
        "resume\x00.pdf",
        "resume\u202e.pdf",
        f"{'r' * MAX_CLIENT_FILENAME_LENGTH}.pdf",
    ],
)
def test_unsafe_or_misleading_filenames_are_rejected(client_filename: str | None) -> None:
    assert reject(client_filename=client_filename).reason is UploadRejectionReason.INVALID_FILENAME


def test_the_pdf_extension_is_case_insensitive() -> None:
    accepted = CVUploadPolicy().validate(
        **valid_upload(client_filename="resume.PDF")  # type: ignore[arg-type]
    )
    assert accepted.client_filename == "resume.PDF"


def test_the_exact_filename_length_limit_is_accepted() -> None:
    filename = f"{'r' * (MAX_CLIENT_FILENAME_LENGTH - len('.pdf'))}.pdf"
    accepted = CVUploadPolicy().validate(
        **valid_upload(client_filename=filename)  # type: ignore[arg-type]
    )
    assert accepted.client_filename == filename


@pytest.mark.parametrize("declared_media_type", [None, "", "text/plain", "application/pdfx"])
def test_a_false_declared_media_type_is_rejected(declared_media_type: str | None) -> None:
    assert (
        reject(declared_media_type=declared_media_type).reason
        is UploadRejectionReason.UNSUPPORTED_MEDIA_TYPE
    )


@pytest.mark.parametrize("initial_bytes", [b"", b"PDF-1.7", b"prefix%PDF-1.7", b"%PDF"])
def test_an_extension_and_media_type_cannot_bypass_the_signature_check(
    initial_bytes: bytes,
) -> None:
    assert reject(initial_bytes=initial_bytes).reason is UploadRejectionReason.UNSUPPORTED_CONTENT


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"max_bytes": 0}, "positive"),
        ({"allowed_formats": frozenset()}, "at least one"),
    ],
)
def test_an_unusable_policy_configuration_is_refused(
    overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        CVUploadPolicy(**overrides)  # type: ignore[arg-type]
