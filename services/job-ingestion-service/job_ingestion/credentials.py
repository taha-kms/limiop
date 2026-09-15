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
from os import environ as os_environ


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
