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
"""

import logging
from collections.abc import Iterable

# Below this, a value matches too much of ordinary text to redact safely --
# redacting a one- or two-character "secret" would blank out routine words
# and digits in every unrelated log line.
MINIMUM_SECRET_LENGTH = 8

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
    for secret in _registered_secrets:
        redacted = redacted.replace(secret, "[redacted]")
    return redacted


def _redact_record(record: logging.LogRecord) -> logging.LogRecord:
    """Redact a record's message and string arguments in place.

    Only `getMessage()`'s two inputs are touched: the format string in `msg`,
    for a caller that interpolated a secret before ever calling the logger,
    and each string entry of `args`, for the ordinary `logger.info("...%s",
    value)` shape. Anything else on the record -- `exc_info`, `exc_text` -- is
    untouched; a traceback that carries a secret is a different problem than
    this module solves.
    """
    if not _registered_secrets:
        return record
    if isinstance(record.msg, str):
        record.msg = _redact(record.msg)
    if isinstance(record.args, tuple):
        record.args = tuple(_redact(arg) if isinstance(arg, str) else arg for arg in record.args)
    elif isinstance(record.args, dict):
        record.args = {
            key: (_redact(value) if isinstance(value, str) else value)
            for key, value in record.args.items()
        }
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
    redacted at the moment it is built, and also attaches a `SecretFilter` to
    the root logger (see the module docstring for why that alone would not be
    enough). Calling this more than once does either only on the first call.
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
