"""Bounded PDF-to-plain-text extraction for hostile CV documents."""

import hashlib
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from io import BytesIO
from multiprocessing import get_context
from multiprocessing.connection import Connection
from typing import Protocol

from anyio import to_thread
from pypdf import PdfReader

from app.modules.cvs.storage import CVObjectTooLarge, CVStorage, CVStorageError


class PDFParsingFailureReason(StrEnum):
    FILE_TOO_LARGE = "file_too_large"
    ENCRYPTED = "encrypted"
    MALFORMED = "malformed"
    PAGE_LIMIT_EXCEEDED = "page_limit_exceeded"
    TEXT_LIMIT_EXCEEDED = "text_limit_exceeded"
    TIMEOUT = "timeout"
    NO_TEXT = "no_text"
    CHECKSUM_MISMATCH = "checksum_mismatch"
    SOURCE_UNAVAILABLE = "source_unavailable"
    PARSER_FAILURE = "parser_failure"


FAILURE_MESSAGES: dict[PDFParsingFailureReason, str] = {
    PDFParsingFailureReason.FILE_TOO_LARGE: "the PDF exceeds the parser size limit",
    PDFParsingFailureReason.ENCRYPTED: "encrypted PDFs are not supported",
    PDFParsingFailureReason.MALFORMED: "the PDF is malformed",
    PDFParsingFailureReason.PAGE_LIMIT_EXCEEDED: "the PDF exceeds the page limit",
    PDFParsingFailureReason.TEXT_LIMIT_EXCEEDED: "the PDF exceeds the text limit",
    PDFParsingFailureReason.TIMEOUT: "PDF parsing exceeded its time limit",
    PDFParsingFailureReason.NO_TEXT: "the PDF contains no extractable text",
    PDFParsingFailureReason.CHECKSUM_MISMATCH: "the stored PDF failed its integrity check",
    PDFParsingFailureReason.SOURCE_UNAVAILABLE: "the stored PDF is unavailable",
    PDFParsingFailureReason.PARSER_FAILURE: "the PDF parser failed",
}


class PDFParsingFailure(Exception):
    """A structured, content-free outcome for an expected parsing failure."""

    def __init__(self, reason: PDFParsingFailureReason) -> None:
        super().__init__(FAILURE_MESSAGES[reason])
        self.reason = reason


@dataclass(frozen=True, slots=True)
class PDFParserLimits:
    max_file_bytes: int
    max_pages: int
    max_text_characters: int
    timeout_seconds: float

    def __post_init__(self) -> None:
        if min(self.max_file_bytes, self.max_pages, self.max_text_characters) < 1:
            raise ValueError("PDF parser size, page, and text limits must be positive")
        if self.timeout_seconds <= 0:
            raise ValueError("PDF parser timeout must be positive")


@dataclass(frozen=True, slots=True)
class ExtractedPDFText:
    text: str
    page_count: int


class PDFTextExtractor(Protocol):
    async def extract(self, document: bytes) -> ExtractedPDFText: ...


@dataclass(frozen=True, slots=True)
class _WorkerSuccess:
    result: ExtractedPDFText


@dataclass(frozen=True, slots=True)
class _WorkerFailure:
    reason: PDFParsingFailureReason


type ParserWorker = Callable[[Connection, bytes, PDFParserLimits], None]


class PypdfTextExtractor:
    def __init__(
        self,
        limits: PDFParserLimits,
        *,
        worker: ParserWorker | None = None,
    ) -> None:
        self._limits = limits
        self._worker = _parse_pdf_worker if worker is None else worker

    async def extract(self, document: bytes) -> ExtractedPDFText:
        if len(document) > self._limits.max_file_bytes:
            raise PDFParsingFailure(PDFParsingFailureReason.FILE_TOO_LARGE)
        return await to_thread.run_sync(
            _run_parser_process,
            document,
            self._limits,
            self._worker,
        )


async def extract_stored_pdf_text(
    storage: CVStorage,
    extractor: PDFTextExtractor,
    *,
    storage_key: str,
    expected_checksum_sha256: str,
    max_file_bytes: int,
) -> ExtractedPDFText:
    try:
        document = await storage.read(storage_key, max_bytes=max_file_bytes)
    except CVObjectTooLarge:
        raise PDFParsingFailure(PDFParsingFailureReason.FILE_TOO_LARGE) from None
    except CVStorageError:
        raise PDFParsingFailure(PDFParsingFailureReason.SOURCE_UNAVAILABLE) from None
    checksum = hashlib.sha256(document).hexdigest()
    if checksum != expected_checksum_sha256:
        raise PDFParsingFailure(PDFParsingFailureReason.CHECKSUM_MISMATCH)
    return await extractor.extract(document)


def normalize_pdf_text(value: str) -> str:
    """Normalize Unicode and whitespace while preserving plain-text line boundaries."""
    normalized = unicodedata.normalize("NFKC", value).replace("\x00", " ")
    lines = (" ".join(line.split()) for line in normalized.splitlines())
    return "\n".join(line for line in lines if line)


def _parse_pdf(document: bytes, limits: PDFParserLimits) -> ExtractedPDFText:
    reader = PdfReader(BytesIO(document), strict=True)
    if reader.is_encrypted:
        raise PDFParsingFailure(PDFParsingFailureReason.ENCRYPTED)
    page_count = len(reader.pages)
    if page_count > limits.max_pages:
        raise PDFParsingFailure(PDFParsingFailureReason.PAGE_LIMIT_EXCEEDED)

    parts: list[str] = []
    text_characters = 0
    for page in reader.pages:
        page_text = normalize_pdf_text(page.extract_text() or "")
        if not page_text:
            continue
        text_characters += len(page_text) + (1 if parts else 0)
        if text_characters > limits.max_text_characters:
            raise PDFParsingFailure(PDFParsingFailureReason.TEXT_LIMIT_EXCEEDED)
        parts.append(page_text)
    if not parts:
        raise PDFParsingFailure(PDFParsingFailureReason.NO_TEXT)
    return ExtractedPDFText(text="\n".join(parts), page_count=page_count)


def _parse_pdf_worker(
    connection: Connection,
    document: bytes,
    limits: PDFParserLimits,
) -> None:
    try:
        try:
            message: _WorkerSuccess | _WorkerFailure = _WorkerSuccess(_parse_pdf(document, limits))
        except PDFParsingFailure as error:
            message = _WorkerFailure(error.reason)
        except Exception:
            message = _WorkerFailure(PDFParsingFailureReason.MALFORMED)
        connection.send(message)
    finally:
        connection.close()


def _run_parser_process(
    document: bytes,
    limits: PDFParserLimits,
    worker: ParserWorker,
) -> ExtractedPDFText:
    context = get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=worker, args=(sender, document, limits), daemon=True)
    started = False
    try:
        try:
            process.start()
            started = True
        except (OSError, RuntimeError):
            raise PDFParsingFailure(PDFParsingFailureReason.PARSER_FAILURE) from None
        finally:
            sender.close()

        if not receiver.poll(limits.timeout_seconds):
            reason = (
                PDFParsingFailureReason.TIMEOUT
                if process.is_alive()
                else PDFParsingFailureReason.PARSER_FAILURE
            )
            raise PDFParsingFailure(reason)
        try:
            message = receiver.recv()
        except EOFError:
            raise PDFParsingFailure(PDFParsingFailureReason.PARSER_FAILURE) from None
        if isinstance(message, _WorkerSuccess):
            return message.result
        if isinstance(message, _WorkerFailure):
            raise PDFParsingFailure(message.reason)
        raise PDFParsingFailure(PDFParsingFailureReason.PARSER_FAILURE)
    finally:
        receiver.close()
        if started:
            process.join(timeout=0.1)
            if process.is_alive():
                process.terminate()
                process.join(timeout=1)
