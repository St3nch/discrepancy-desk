"""The credential boundary and the fail-closed DSN contract.

Reconciliation section 7. These tests use obviously synthetic credentials only;
no real credential is present in this repository.
"""

from __future__ import annotations

import pytest

from tools.postgres_foundation_proofs.dsn import (
    DSN_ENVIRONMENT_VARIABLE,
    dsn_from_environment,
    parse_dsn,
)
from tools.postgres_foundation_proofs.errors import ErrorCategory, ProofRunError

SYNTHETIC = "postgresql://proofuser:NOT_A_REAL_PASSWORD@127.0.0.1:54321/postgres"

#: The exact shape the fixed VedaOps host operation supplies. The password is
#: synthetic; no real credential appears in this repository.
VEDAOPS_SHAPE = "postgresql://vedaops:NOT_A_REAL_PASSWORD@127.0.0.1:49183/vedaops"


def test_parses_a_well_formed_dsn():
    dsn = parse_dsn(SYNTHETIC)
    assert dsn.username == "proofuser"
    assert dsn.host == "127.0.0.1"
    assert dsn.port == 54321
    assert dsn.dbname == "postgres"


def test_str_and_repr_are_redacted():
    dsn = parse_dsn(SYNTHETIC)
    assert "NOT_A_REAL_PASSWORD" not in str(dsn)
    assert "NOT_A_REAL_PASSWORD" not in repr(dsn)
    assert "NOT_A_REAL_PASSWORD" not in f"{dsn}"
    assert "NOT_A_REAL_PASSWORD" not in "{}".format(dsn)  # noqa: UP032 - exercising format()
    assert str(dsn) == "postgresql://proofuser@127.0.0.1:54321/postgres"


def test_observation_carries_no_credential():
    observation = parse_dsn(SYNTHETIC).observation()
    assert "NOT_A_REAL_PASSWORD" not in repr(observation)
    assert observation["password_present"] is True


def test_raw_is_reachable_only_through_the_named_accessor():
    dsn = parse_dsn(SYNTHETIC)
    assert dsn.raw_for_connect() == SYNTHETIC


def test_secret_candidates_cover_encoded_forms():
    dsn = parse_dsn("postgresql://u:a%40b%21c@127.0.0.1:5432/postgres")
    candidates = dsn.secret_candidates()
    assert "a%40b%21c" in candidates
    assert "a@b!c" in candidates


def test_an_encoded_authority_password_is_represented_in_both_forms():
    # A VedaOps-random password containing reserved characters must be
    # scrubbable whether the report ever renders it encoded or decoded.
    dsn = parse_dsn("postgresql://vedaops:p%40ss%2Fw%3Ard%21@127.0.0.1:49183/vedaops")
    candidates = dsn.secret_candidates()
    assert "p%40ss%2Fw%3Ard%21" in candidates
    assert "p@ss/w:rd!" in candidates
    assert all(candidate for candidate in candidates)
    assert dsn.raw_for_connect().endswith("/vedaops")
    assert "p%40ss" not in str(dsn)


def test_the_exact_vedaops_shape_parses():
    # postgresql://vedaops:<random>@127.0.0.1:<random-port>/vedaops
    dsn = parse_dsn(VEDAOPS_SHAPE)
    assert (dsn.scheme, dsn.username, dsn.host, dsn.port, dsn.dbname) == (
        "postgresql",
        "vedaops",
        "127.0.0.1",
        49183,
        "vedaops",
    )
    assert dsn.observation()["password_present"] is True


@pytest.mark.parametrize(
    "raw",
    [
        # No password at all: libpq would consult a passfile, a service file,
        # or environment variables, none of which the runner models or scrubs.
        "postgresql://vedaops@127.0.0.1:49183/vedaops",
        # Empty password.
        "postgresql://vedaops:@127.0.0.1:49183/vedaops",
    ],
)
def test_a_dsn_without_an_explicit_password_is_refused(raw):
    with pytest.raises(ProofRunError) as excinfo:
        parse_dsn(raw)
    assert excinfo.value.category is ErrorCategory.DSN_REJECTED
    assert "explicit password" in excinfo.value.message


@pytest.mark.parametrize(
    "query",
    [
        "password=NOT_A_REAL_PASSWORD",
        "user=someone_else",
        "sslmode=require",
        "options=-csearch_path%3Dpublic",
        "host=elsewhere",
        "hostaddr=10.0.0.1",
        "port=5433",
        "dbname=other",
        "service=svc",
        "passfile=/tmp/pass",
        "connect_timeout=1",
        "totally_unknown_key=whatever",
        "",  # a bare trailing "?" that urlsplit reports as an empty query
    ],
)
def test_any_query_string_is_refused(query):
    with pytest.raises(ProofRunError) as excinfo:
        parse_dsn(f"{VEDAOPS_SHAPE}?{query}")
    assert excinfo.value.category is ErrorCategory.DSN_REJECTED
    assert "no query string" in excinfo.value.message


@pytest.mark.parametrize("fragment", ["frag", "", "sslmode=require"])
def test_any_fragment_is_refused(fragment):
    with pytest.raises(ProofRunError) as excinfo:
        parse_dsn(f"{VEDAOPS_SHAPE}#{fragment}")
    assert excinfo.value.category is ErrorCategory.DSN_REJECTED
    assert "no fragment" in excinfo.value.message


def test_a_query_string_password_is_never_treated_as_the_credential():
    # Refused outright, so it can never become a secret candidate the scrubber
    # would then have to model.
    with pytest.raises(ProofRunError):
        parse_dsn("postgresql://vedaops@127.0.0.1:49183/vedaops?password=NOT_A_REAL_PASSWORD")


def test_keyword_dsn_syntax_is_not_supported():
    with pytest.raises(ProofRunError):
        parse_dsn("host=127.0.0.1 port=49183 dbname=vedaops user=vedaops password=x")


@pytest.mark.parametrize(
    ("raw", "category"),
    [
        ("", ErrorCategory.DSN_UNPARSEABLE),
        ("   ", ErrorCategory.DSN_UNPARSEABLE),
        ("postgresql://u:p@127.0.0.1:notaport/db", ErrorCategory.DSN_UNPARSEABLE),
        ("mysql://u:p@127.0.0.1:3306/db", ErrorCategory.DSN_REJECTED),
        ("http://u:p@127.0.0.1:5432/db", ErrorCategory.DSN_REJECTED),
    ],
)
def test_malformed_dsn_is_refused(raw, category):
    with pytest.raises(ProofRunError) as excinfo:
        parse_dsn(raw)
    assert excinfo.value.category is category


@pytest.mark.parametrize(
    "raw",
    [
        # No host: libpq would fall back to a local Unix socket, which is the
        # host-cluster path the ticket forbids.
        "postgresql:///postgres",
        # No port: libpq would fall back to 5432 or PGPORT.
        "postgresql://u:p@127.0.0.1/postgres",
        # No user: libpq would fall back to the operating-system user.
        "postgresql://127.0.0.1:5432/postgres",
        # No database name.
        "postgresql://u:p@127.0.0.1:5432/",
        "postgresql://u:p@127.0.0.1:5432",
    ],
)
def test_implicit_fallback_shapes_are_refused(raw):
    with pytest.raises(ProofRunError) as excinfo:
        parse_dsn(raw)
    assert excinfo.value.category is ErrorCategory.DSN_REJECTED


def test_missing_environment_variable_never_falls_back():
    with pytest.raises(ProofRunError) as excinfo:
        dsn_from_environment({})
    assert excinfo.value.category is ErrorCategory.DSN_MISSING
    assert "never selects a default DSN" in excinfo.value.message


def test_environment_variable_is_the_only_source():
    dsn = dsn_from_environment({DSN_ENVIRONMENT_VARIABLE: SYNTHETIC})
    assert dsn.port == 54321


def test_error_messages_never_echo_the_dsn():
    with pytest.raises(ProofRunError) as excinfo:
        parse_dsn("postgresql://u:NOT_A_REAL_PASSWORD@127.0.0.1:5432/")
    assert "NOT_A_REAL_PASSWORD" not in str(excinfo.value)
