"""Reading third-party source credentials from the environment.

One environment variable per credential, never a JSON blob. `SKILLSYNC_SOURCE_CONFIG`
was rejected for this precisely because it is read and logged whole in
diagnostics; the structured logger redacts by field, and a field is what one
environment variable is. A source that needs an app id and a key registers two
`Credential` values rather than one config object, so each can be named,
required, and redacted on its own.

`resolve` returns `Unconfigured` rather than raising when a variable is missing
or blank. A deployment enables sources one at a time, so an unset credential is
an expected, ordinary state -- not a reason for import, or a scheduler's DAG
parse, to fail. Callers that need the run recorded rather than merely reported
use `require`, in `runs.py`.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from os import environ as os_environ

from job_ingestion.contracts import IngestionSummary
from job_ingestion.database import Database
from job_ingestion.logging_support import install_secret_filter, register_secrets
from job_ingestion.runs import record_unconfigured_run


@dataclass(frozen=True, slots=True)
class Credential:
    """One environment variable a source needs to run."""

    env: str
    # False for an identifier that is not confidential, such as an app id
    # published alongside a key. Still required; only the redaction differs.
    secret: bool = True


@dataclass(frozen=True, slots=True)
class Unconfigured:
    """A source's credentials are not all present.

    Names the missing variables, never their values -- there is nothing to
    redact here because nothing sensitive is carried.
    """

    missing: tuple[str, ...]

    @property
    def reason(self) -> str:
        return "source unconfigured: " + ", ".join(self.missing)


def resolve(
    required: Sequence[Credential], environ: Mapping[str, str] | None = None
) -> Mapping[str, str] | Unconfigured:
    """Read every required credential, or report what is missing.

    A variable that is absent or blank (whitespace only) counts as missing.
    Present values are stripped. `environ` defaults to `os.environ`; a caller
    that wants a fixed environment for a test passes its own mapping.
    """
    source = environ if environ is not None else os_environ
    values: dict[str, str] = {}
    missing: list[str] = []
    for credential in required:
        raw = source.get(credential.env)
        value = raw.strip() if raw is not None else ""
        if value:
            values[credential.env] = value
        else:
            missing.append(credential.env)
    if missing:
        return Unconfigured(missing=tuple(missing))
    return values


async def require(
    database: Database,
    source_key: str,
    required: Sequence[Credential],
    *,
    started_at: datetime,
) -> Mapping[str, str] | IngestionSummary:
    """Resolve `required`, recording a run if the source is not configured.

    A keyed `ingest_*` entry point opens with:

        resolved = await require(database, SOURCE_KEY, REQUIRED, started_at=started_at)
        if isinstance(resolved, IngestionSummary):
            return resolved

    so the unconfigured path returns the same type the entry point already
    returns on every other path, and the caller never branches on `Unconfigured`
    itself.

    This is the first place a source's secret values exist in the process, so
    it installs the log redaction filter itself -- idempotent, so calling it
    here costs nothing on the second and every later keyed source -- rather
    than depending on some other startup step to have run first (see
    `logging_support`'s module docstring for why that ordering matters). A
    resolved `secret=True` value is then registered for redaction before this
    returns, so it is protected everywhere before the client that carries it
    can even be constructed. A `secret=False` value -- an app id published
    alongside a key -- is never registered: there is nothing in it to redact.
    """
    resolved = resolve(required)
    if isinstance(resolved, Unconfigured):
        return await record_unconfigured_run(database, source_key, resolved, started_at=started_at)
    install_secret_filter()
    register_secrets(resolved[credential.env] for credential in required if credential.secret)
    return resolved
