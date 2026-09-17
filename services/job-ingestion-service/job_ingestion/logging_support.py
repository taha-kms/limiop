"""Keeping credential values out of every log line.

`transport.py` and every provider client are already told never to log a full
URL or its headers, because a credential rides in one of those rather than in
a structured field the logger could redact on its own. This module is the
line behind that rule: whatever secret values a source's credentials resolved
to are stripped from every record the process emits, regardless of which
client logged it or forgot the rule.

A `logging.Filter` attached to a `Logger` object -- even the root one -- only
runs for records that logger originates itself. Propagation calls an
ancestor's *handlers*, never its *filters* (`Logger.callHandlers` in the
standard library walks `handlers`, not `filters`, as it climbs); every module
in this service calls `logging.getLogger(__name__)`, so a `SecretFilter`
attached only to the root logger would silently protect nothing it did not
log directly. The guarantee here instead comes from
`logging.setLogRecordFactory`: every logger in the process, at any depth,
builds each record through that one shared factory, so wrapping it once
redacts every record regardless of origin. `install_secret_filter` also
attaches a `SecretFilter` to the root logger, both because a caller may rely
on `logging.Filter` composing with filters of its own and to keep the literal
shape this module was specified with; that attachment is belt-and-braces; the
factory wrap is what actually carries the guarantee, and redacting an
already-redacted string a second time is a no-op.

The wrap chains whatever factory was installed before it and must run last: if
some other library calls `logging.setLogRecordFactory` again after this
module's `install_secret_filter` has already run, that later call replaces the
chain outright and every record built after it bypasses redaction silently.
Nothing here can detect that; the ordering has to hold by construction, which
is why `credentials.require` -- the first place a source's secret values
exist in the process -- installs the filter itself rather than trusting some
other setup step to have run first.

A traceback is the one piece of a record the factory cannot see. `exc_info`
is a live exception triple when the record is built; the text a reader sees
-- the frames and the final `ExceptionClass: message` line, where a
provider's error text lands -- is produced by `logging.Formatter`'s
`formatException` only when the first handler formats the record, and
`Formatter.format` then caches that text on `record.exc_text` for every
later handler to reuse verbatim. Every handler formats through a
`Formatter`, so `install_secret_filter` also wraps the class's
`formatException` once, redacting the text at the moment it is produced.
That covers the first formatting; a record that already carries `exc_text`
-- rebuilt from another process's dict, or handed to a `SecretFilter`
attached directly to a later handler -- never calls `formatException` again,
so `_redact_record` redacts the cached text too. `stack_info` is a plain
string from the start and is redacted where the message is.

A value shorter than eight characters (`MINIMUM_SECRET_LENGTH` below) is never
registered: redacting a one- or two-character "secret" would blank out routine
words and digits in every unrelated log line.
"""

import functools
import logging
from collections.abc import Iterable
from types import TracebackType

MINIMUM_SECRET_LENGTH = 8

_ExcInfo = tuple[type[BaseException], BaseException, TracebackType | None] | tuple[None, None, None]

_registered_secrets: set[str] = set()


def register_secrets(values: Iterable[str]) -> None:
    """Register secret values read from the environment for redaction.

    Takes the values themselves, never variable names -- there is nothing to
    protect in a name. A value shorter than `MINIMUM_SECRET_LENGTH` is never
    registered; see the module docstring for why.
    """
    for value in values:
        if len(value) >= MINIMUM_SECRET_LENGTH:
            _registered_secrets.add(value)


def _redact(value: str) -> str:
    redacted = value
    # A snapshot, not the live set: `register_secrets` can run while this is
    # formatting a record on another thread, and mutating the set mid-iteration
    # would raise instead of redacting.
    for secret in tuple(_registered_secrets):
        redacted = redacted.replace(secret, "[redacted]")
    return redacted


def _redact_arg(arg: object) -> object:
    """Redact one `%`-style argument, string or not.

    A string argument is redacted directly. A number is never inspected -- a
    secret is not a bare `int`, `float`, `complex`, or `bool`, and stringifying
    every formatted count and percentage for nothing would be needless work on
    a path every ingestion log line runs through. Anything else -- an
    exception, any object whose `str()` might carry a secret -- is redacted by
    its string form only if a secret was actually found in it; an argument
    that does not contain one is returned unchanged, so `%d` and friends still
    see the original value. An argument whose `str()` itself raises is also
    returned unchanged rather than propagating from inside this filter --
    `%s`-formatting it later fails exactly as it always would have, which
    `logging` already tolerates, instead of failing here first.
    """
    if isinstance(arg, str):
        return _redact(arg)
    if isinstance(arg, int | float | complex | bool):
        return arg
    try:
        text = str(arg)
    except Exception:
        return arg
    redacted = _redact(text)
    return redacted if redacted != text else arg


def _redact_record(record: logging.LogRecord) -> logging.LogRecord:
    """Redact a record's message, arguments, and any text it already carries.

    `getMessage()`'s two inputs are touched: the format string in `msg`, for
    a caller that interpolated a secret before ever calling the logger, and
    each entry of `args`, for the ordinary `logger.info("...%s", value)`
    shape -- including a non-string argument such as an exception, whose
    `str()` may itself carry a secret (a `SourceUnavailableError` built from a
    provider's own error text, say). `stack_info` is redacted when set. So is
    `exc_text`, but only when it is already set: a record built by the
    factory never has it yet, and the traceback text produced later by
    `formatException` is redacted by the wrap in `install_secret_filter`;
    this branch covers a record that arrives with the cached text in place
    (see the module docstring). `exc_info` itself is left alone -- it is the
    live exception, not text.
    """
    if not _registered_secrets:
        return record
    if isinstance(record.msg, str):
        record.msg = _redact(record.msg)
    if isinstance(record.args, tuple):
        record.args = tuple(_redact_arg(arg) for arg in record.args)
    elif isinstance(record.args, dict):
        record.args = {key: _redact_arg(value) for key, value in record.args.items()}
    if record.exc_text is not None:
        record.exc_text = _redact(record.exc_text)
    if record.stack_info is not None:
        record.stack_info = _redact(record.stack_info)
    return record


class SecretFilter(logging.Filter):
    """Redacts every registered secret value out of one log record.

    Provided so a caller can attach the same redaction to one handler
    directly -- a sink a hosting application wires up itself, say -- rather
    than relying only on the process-wide installation below.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        _redact_record(record)
        return True


_installed = False


def install_secret_filter() -> None:
    """Install credential redaction for the whole process, once.

    Wraps the shared log record factory so every logger's every record is
    redacted at the moment it is built, wraps `logging.Formatter`'s
    `formatException` so a traceback is redacted at the moment its text is
    produced, and also attaches a `SecretFilter` to the root logger (see the
    module docstring for why the filter alone would not be enough, and why a
    traceback needs its own hook). Calling this more than once does any of it
    only on the first call. Both wraps chain whatever was there before them,
    and a test that provokes a real installation puts both back.
    """
    global _installed
    if _installed:
        return
    _installed = True

    root = logging.getLogger()
    root.addFilter(SecretFilter())

    previous_factory = logging.getLogRecordFactory()

    def factory(*args: object, **kwargs: object) -> logging.LogRecord:
        return _redact_record(previous_factory(*args, **kwargs))

    logging.setLogRecordFactory(factory)

    previous_format_exception = logging.Formatter.formatException

    @functools.wraps(previous_format_exception)
    def format_exception(self: logging.Formatter, ei: _ExcInfo) -> str:
        return _redact(previous_format_exception(self, ei))

    logging.Formatter.formatException = format_exception  # type: ignore[method-assign]
