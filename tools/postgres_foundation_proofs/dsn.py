"""The credential boundary.

Reconciliation section 7:

* the raw DSN is read only from ``VEDAOPS_POSTGRES_URL`` and never appears in argv;
* the runner never serializes the raw DSN, password, driver connection-info
  repr, environment contents, or an unfiltered driver exception;
* reports contain only credential-free host/port/user/database observations.

The accepted DSN syntax is deliberately narrow -- exactly the shape the fixed
VedaOps host operation supplies. Keyword DSNs, service files, passfiles,
query-string passwords, and environment-driven connection fields are not
supported and must not be added.

``SafeDsn`` holds the raw string in a private attribute and renders redacted in
both ``str`` and ``repr``, so an accidental interpolation into a log line or an
f-string cannot leak the password. The raw value is reachable only through the
explicitly named :meth:`SafeDsn.raw_for_connect`.
"""

from __future__ import annotations

import os
from urllib.parse import quote, unquote, urlsplit

from .errors import ErrorCategory, ProofRunError

#: The one and only accepted source of the connection string.
DSN_ENVIRONMENT_VARIABLE = "VEDAOPS_POSTGRES_URL"

_ACCEPTED_SCHEMES = frozenset({"postgresql", "postgres"})

#: The fixed VedaOps PostgreSQL host operation supplies exactly one shape:
#:
#:     postgresql://vedaops:<random-password>@127.0.0.1:<random-port>/vedaops
#:
#: explicit scheme, user, password, loopback host, port and database, with no
#: query string and no fragment. The runner therefore needs no broader DSN
#: capability, and accepting one would only widen the surface: a query string
#: can carry connection, credential, or configuration behaviour that this
#: parser, the secret-candidate extraction, and the report contract do not
#: model. Anything outside that shape is refused rather than normalized.
_ACCEPTED_SHAPE = "postgresql://user:password@host:port/database"


class SafeDsn:
    """A parsed connection string that renders redacted by default."""

    __slots__ = ("_raw", "scheme", "username", "host", "port", "dbname", "_password")

    def __init__(
        self,
        *,
        raw: str,
        scheme: str,
        username: str,
        host: str,
        port: int,
        dbname: str,
        password: str | None,
    ) -> None:
        self._raw = raw
        self._password = password
        self.scheme = scheme
        self.username = username
        self.host = host
        self.port = port
        self.dbname = dbname

    def raw_for_connect(self) -> str:
        """Return the raw DSN. The only legitimate caller is the connect path."""
        return self._raw

    def redacted(self) -> str:
        """A credential-free rendering safe for reports and messages."""
        return f"{self.scheme}://{self.username}@{self.host}:{self.port}/{self.dbname}"

    def observation(self) -> dict[str, object]:
        """Credential-free DSN observations for the report."""
        return {
            "scheme": self.scheme,
            "username": self.username,
            "host": self.host,
            "port": self.port,
            "database": self.dbname,
            "redacted": self.redacted(),
            "password_present": self._password is not None,
        }

    def secret_candidates(self) -> frozenset[str]:
        """Strings the final report must not contain.

        Reconciliation section 7 requires the defence-in-depth check to cover
        "the known raw password and encoded forms", so this returns the literal
        substring from the DSN plus its decoded and re-encoded variants.
        """
        if not self._password:
            return frozenset()
        raw = self._password
        decoded = unquote(raw)
        candidates = {raw, decoded, quote(decoded, safe=""), quote(decoded)}
        return frozenset(c for c in candidates if c)

    def __str__(self) -> str:
        return self.redacted()

    def __repr__(self) -> str:
        return f"SafeDsn({self.redacted()!r})"


def parse_dsn(raw: str) -> SafeDsn:
    """Parse and validate a PostgreSQL DSN, failing closed.

    Every rejection below exists to prevent an implicit fallback to a server the
    Steward did not supply -- in particular the host-installed cluster.
    """
    if raw is None or not raw.strip():
        raise ProofRunError(
            ErrorCategory.DSN_UNPARSEABLE,
            f"{DSN_ENVIRONMENT_VARIABLE} is empty",
        )

    raw_stripped = raw.strip()
    try:
        parts = urlsplit(raw_stripped)
        port = parts.port
    except ValueError:
        # Includes a non-numeric or out-of-range port. The driver's message is
        # not reused because it can echo the DSN.
        raise ProofRunError(
            ErrorCategory.DSN_UNPARSEABLE,
            f"{DSN_ENVIRONMENT_VARIABLE} is not a parseable URL",
        ) from None

    if parts.scheme not in _ACCEPTED_SCHEMES:
        raise ProofRunError(
            ErrorCategory.DSN_REJECTED,
            "DSN scheme must be postgresql:// or postgres://",
        )

    # An absent host would let libpq fall back to a local Unix socket, which is
    # exactly the host-cluster path the ticket forbids.
    if not parts.hostname:
        raise ProofRunError(
            ErrorCategory.DSN_REJECTED,
            "DSN must name an explicit host; libpq local-socket defaulting is refused",
        )

    # An absent port would let libpq fall back to 5432 or PGPORT.
    if port is None:
        raise ProofRunError(
            ErrorCategory.DSN_REJECTED,
            "DSN must name an explicit port; libpq port defaulting is refused",
        )

    # An absent user would let libpq fall back to the operating-system user.
    if not parts.username:
        raise ProofRunError(
            ErrorCategory.DSN_REJECTED,
            "DSN must name an explicit user; libpq operating-system-user defaulting is refused",
        )

    # An absent password would let libpq consult alternate credential
    # mechanisms -- a passfile, a service file, or environment variables --
    # none of which this runner models and none of which its secret scrubber
    # could scrub.
    if not parts.password:
        raise ProofRunError(
            ErrorCategory.DSN_REJECTED,
            "DSN must carry an explicit password in the URI authority; libpq "
            "alternate credential mechanisms are refused",
        )

    dbname = parts.path.lstrip("/")
    if not dbname:
        raise ProofRunError(
            ErrorCategory.DSN_REJECTED,
            "DSN must name an explicit maintenance database",
        )
    if "/" in dbname:
        raise ProofRunError(
            ErrorCategory.DSN_REJECTED,
            "DSN path must contain exactly one database name",
        )

    # Every query parameter is refused, not merely a denylist of redirecting
    # keys. The supplied shape carries none, and an allowed-looking parameter
    # would still be connection behaviour this runner does not model. The raw
    # delimiter check also catches a bare trailing "?" that urlsplit reports as
    # an empty query.
    if parts.query or "?" in raw_stripped:
        raise ProofRunError(
            ErrorCategory.DSN_REJECTED,
            f"DSN must carry no query string; the accepted shape is {_ACCEPTED_SHAPE}",
        )

    if parts.fragment or "#" in raw_stripped:
        raise ProofRunError(
            ErrorCategory.DSN_REJECTED,
            f"DSN must carry no fragment; the accepted shape is {_ACCEPTED_SHAPE}",
        )

    return SafeDsn(
        raw=raw_stripped,
        scheme=parts.scheme,
        username=parts.username,
        host=parts.hostname,
        port=port,
        dbname=dbname,
        password=parts.password,
    )


def dsn_from_environment(environ: dict[str, str] | None = None) -> SafeDsn:
    """Read and validate the DSN from the environment. Never falls back."""
    env = os.environ if environ is None else environ
    if DSN_ENVIRONMENT_VARIABLE not in env:
        raise ProofRunError(
            ErrorCategory.DSN_MISSING,
            f"{DSN_ENVIRONMENT_VARIABLE} is not set; the runner never selects a "
            "default DSN, localhost, Docker metadata, or the host PostgreSQL cluster",
        )
    return parse_dsn(env[DSN_ENVIRONMENT_VARIABLE])
