import asyncio
import hashlib
import time
from io import BytesIO
from typing import IO
from uuid import UUID

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.modules.cvs import parsing
from app.modules.cvs.parsing import (
    ExtractedPDFText,
    PDFParserLimits,
    PDFParsingFailure,
    PDFParsingFailureReason,
    PypdfTextExtractor,
    extract_stored_pdf_text,
    normalize_pdf_text,
)
from app.modules.cvs.storage import (
    CVObjectNotFound,
    CVObjectTooLarge,
    StoredCVObject,
)


def synthetic_pdf(*page_texts: str) -> bytes:
    writer = PdfWriter()
    for text in page_texts:
        page = writer.add_blank_page(width=612, height=792)
        if not text:
            continue
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        font_reference = writer._add_object(font)
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_reference})}
        )
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def encrypted_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.encrypt("synthetic-password")
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def limits(**overrides: int | float) -> PDFParserLimits:
    values: dict[str, int | float] = {
        "max_file_bytes": 20_000,
        "max_pages": 3,
        "max_text_characters": 100,
        "timeout_seconds": 3.0,
    }
    values.update(overrides)
    return PDFParserLimits(**values)  # type: ignore[arg-type]


def extract(document: bytes, **limit_overrides: int | float) -> ExtractedPDFText:
    extractor = PypdfTextExtractor(limits(**limit_overrides))
    return asyncio.run(extractor.extract(document))


def failure(document: bytes, **limit_overrides: int | float) -> PDFParsingFailure:
    with pytest.raises(PDFParsingFailure) as raised:
        extract(document, **limit_overrides)
    return raised.value


def slow_worker(_connection: object, _document: bytes, _limits: PDFParserLimits) -> None:
    time.sleep(2)


def test_valid_text_pages_produce_normalized_plain_text() -> None:
    result = extract(synthetic_pdf("Platform   Engineer", "Python\tSQL"))

    assert result == ExtractedPDFText(
        text="Platform Engineer\nPython SQL",
        page_count=2,
    )


def test_encrypted_pdfs_have_an_explicit_outcome() -> None:
    assert failure(encrypted_pdf()).reason is PDFParsingFailureReason.ENCRYPTED


@pytest.mark.parametrize("document", [b"", b"%PDF-private marker but not a document"])
def test_malformed_pdfs_have_a_content_free_outcome(document: bytes) -> None:
    error = failure(document)

    assert error.reason is PDFParsingFailureReason.MALFORMED
    assert "private marker" not in str(error)


def test_the_file_limit_is_checked_before_parsing() -> None:
    document = synthetic_pdf("bounded")
    error = failure(document, max_file_bytes=len(document) - 1)

    assert error.reason is PDFParsingFailureReason.FILE_TOO_LARGE


def test_an_image_only_or_blank_pdf_has_an_explicit_no_text_outcome() -> None:
    assert failure(synthetic_pdf("")).reason is PDFParsingFailureReason.NO_TEXT


def test_the_page_limit_is_checked_before_page_text_extraction() -> None:
    document = synthetic_pdf("one", "two")
    error = failure(document, max_pages=1)

    assert error.reason is PDFParsingFailureReason.PAGE_LIMIT_EXCEEDED


def test_normalized_output_is_bounded() -> None:
    error = failure(synthetic_pdf("abcdefghij"), max_text_characters=9)

    assert error.reason is PDFParsingFailureReason.TEXT_LIMIT_EXCEEDED


def test_the_parser_process_is_terminated_at_its_deadline() -> None:
    extractor = PypdfTextExtractor(
        limits(timeout_seconds=0.05),
        worker=slow_worker,
    )
    started = time.monotonic()

    with pytest.raises(PDFParsingFailure) as raised:
        asyncio.run(extractor.extract(synthetic_pdf("bounded")))

    assert raised.value.reason is PDFParsingFailureReason.TIMEOUT
    assert time.monotonic() - started < 1.5


def test_text_normalization_removes_control_and_repeated_whitespace() -> None:
    assert normalize_pdf_text("  Python\u00a0  SQL\x00\r\n\r\n  API  ") == "Python SQL\nAPI"


def test_the_parser_core_normalizes_pages_before_returning() -> None:
    result = parsing._parse_pdf(
        synthetic_pdf("first   page", "", "third\tpage"),
        limits(max_pages=3),
    )

    assert result == ExtractedPDFText("first page\nthird page", 3)


@pytest.mark.parametrize(
    ("document", "limit_overrides", "expected_reason"),
    [
        (encrypted_pdf(), {}, PDFParsingFailureReason.ENCRYPTED),
        (
            synthetic_pdf("one", "two"),
            {"max_pages": 1},
            PDFParsingFailureReason.PAGE_LIMIT_EXCEEDED,
        ),
        (
            synthetic_pdf("abcdefghij"),
            {"max_text_characters": 9},
            PDFParsingFailureReason.TEXT_LIMIT_EXCEEDED,
        ),
        (synthetic_pdf(""), {}, PDFParsingFailureReason.NO_TEXT),
    ],
)
def test_the_parser_core_returns_each_expected_document_outcome(
    document: bytes,
    limit_overrides: dict[str, int | float],
    expected_reason: PDFParsingFailureReason,
) -> None:
    with pytest.raises(PDFParsingFailure) as raised:
        parsing._parse_pdf(document, limits(**limit_overrides))

    assert raised.value.reason is expected_reason


class RecordingConnection:
    def __init__(self) -> None:
        self.message: object | None = None
        self.closed = False

    def send(self, message: object) -> None:
        self.message = message

    def close(self) -> None:
        self.closed = True


@pytest.mark.parametrize(
    ("document", "message_type", "expected_reason"),
    [
        (synthetic_pdf("plain"), parsing._WorkerSuccess, None),
        (
            synthetic_pdf(""),
            parsing._WorkerFailure,
            PDFParsingFailureReason.NO_TEXT,
        ),
        (
            b"%PDF-malformed",
            parsing._WorkerFailure,
            PDFParsingFailureReason.MALFORMED,
        ),
    ],
)
def test_the_worker_returns_only_structured_messages(
    document: bytes,
    message_type: type[object],
    expected_reason: PDFParsingFailureReason | None,
) -> None:
    connection = RecordingConnection()

    parsing._parse_pdf_worker(
        connection,  # type: ignore[arg-type]
        document,
        limits(),
    )

    assert isinstance(connection.message, message_type)
    assert connection.closed is True
    if expected_reason is not None:
        assert isinstance(connection.message, parsing._WorkerFailure)
        assert connection.message.reason is expected_reason


@pytest.mark.parametrize(
    "overrides",
    [
        {"max_file_bytes": 0},
        {"max_pages": 0},
        {"max_text_characters": 0},
        {"timeout_seconds": 0.0},
    ],
)
def test_parser_limits_must_be_positive(overrides: dict[str, int | float]) -> None:
    with pytest.raises(ValueError, match="positive"):
        limits(**overrides)


class FakeStorage:
    def __init__(self, document: bytes | Exception) -> None:
        self.document = document

    async def write(self, owner_id: UUID, content: IO[bytes], *, max_bytes: int) -> StoredCVObject:
        del owner_id, content, max_bytes
        raise AssertionError("write is not part of parsing")

    async def read(self, key: str, *, max_bytes: int) -> bytes:
        del key, max_bytes
        if isinstance(self.document, Exception):
            raise self.document
        return self.document

    async def delete(self, key: str) -> None:
        del key
        raise AssertionError("delete is not part of parsing")


class FakeExtractor:
    def __init__(self) -> None:
        self.documents: list[bytes] = []

    async def extract(self, document: bytes) -> ExtractedPDFText:
        self.documents.append(document)
        return ExtractedPDFText(text="plain text", page_count=1)


def test_stored_extraction_checks_integrity_before_parsing() -> None:
    document = b"synthetic PDF bytes"
    extractor = FakeExtractor()

    result = asyncio.run(
        extract_stored_pdf_text(
            FakeStorage(document),
            extractor,
            storage_key="opaque",
            expected_checksum_sha256=hashlib.sha256(document).hexdigest(),
            max_file_bytes=1024,
        )
    )

    assert result.text == "plain text"
    assert extractor.documents == [document]


def test_a_stored_checksum_mismatch_never_reaches_the_parser() -> None:
    extractor = FakeExtractor()
    with pytest.raises(PDFParsingFailure) as raised:
        asyncio.run(
            extract_stored_pdf_text(
                FakeStorage(b"changed"),
                extractor,
                storage_key="opaque",
                expected_checksum_sha256="a" * 64,
                max_file_bytes=1024,
            )
        )

    assert raised.value.reason is PDFParsingFailureReason.CHECKSUM_MISMATCH
    assert extractor.documents == []


@pytest.mark.parametrize(
    ("storage_error", "expected_reason"),
    [
        (
            CVObjectTooLarge("private detail"),
            PDFParsingFailureReason.FILE_TOO_LARGE,
        ),
        (
            CVObjectNotFound("private host path"),
            PDFParsingFailureReason.SOURCE_UNAVAILABLE,
        ),
    ],
)
def test_stored_object_failures_are_structured_and_sanitized(
    storage_error: Exception,
    expected_reason: PDFParsingFailureReason,
) -> None:
    with pytest.raises(PDFParsingFailure) as raised:
        asyncio.run(
            extract_stored_pdf_text(
                FakeStorage(storage_error),
                FakeExtractor(),
                storage_key="private-key",
                expected_checksum_sha256="a" * 64,
                max_file_bytes=1024,
            )
        )

    assert raised.value.reason is expected_reason
    assert "private" not in str(raised.value)
