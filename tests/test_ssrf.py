"""SSRF guards for capture_url — resolved-address and redirect re-validation."""

from __future__ import annotations

import ipaddress
from pathlib import Path

import httpx
import pytest
from sqlalchemy import Engine

from desk.db.session import connection_scope
from desk.refusals import DeskRefusal
from desk.service import (
    approve_run,
    capture_url,
    claim_next_run,
    create_case,
    create_run,
)
from desk.service.models import (
    ApproveRunInput,
    CaptureUrlInput,
    ClaimNextRunInput,
    CreateCaseInput,
    CreateRunInput,
)
from desk.vault.ssrf import (
    MAX_BODY_BYTES,
    assert_url_safe_to_fetch,
    safe_http_get,
)
from desk.vault.store import VaultStore


def _loopback_resolve(hostname: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    return [ipaddress.ip_address("127.0.0.1")]


def _public_resolve(hostname: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    return [ipaddress.ip_address("93.184.216.34")]


def _meta_resolve(hostname: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    return [ipaddress.ip_address("169.254.169.254")]


def _mapped_loopback_resolve(
    hostname: str,
) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    return [ipaddress.ip_address("::ffff:127.0.0.1")]


def test_literal_loopback_refused() -> None:
    with pytest.raises(DeskRefusal) as exc_info:
        assert_url_safe_to_fetch("http://127.0.0.1:8000/api/cases")
    assert exc_info.value.code == "CAPTURE_URL_BLOCKED"


def test_literal_ipv6_loopback_refused() -> None:
    with pytest.raises(DeskRefusal) as exc_info:
        assert_url_safe_to_fetch("http://[::1]/")
    assert exc_info.value.code == "CAPTURE_URL_BLOCKED"


def test_ipv4_mapped_loopback_refused() -> None:
    """::ffff:127.0.0.1 must be blocked independent of Python patch level (F-18)."""
    with pytest.raises(DeskRefusal) as exc_info:
        assert_url_safe_to_fetch(
            "http://mapped.example/",
            resolve=_mapped_loopback_resolve,
        )
    assert exc_info.value.code == "CAPTURE_URL_BLOCKED"


def test_private_rfc1918_refused() -> None:
    with pytest.raises(DeskRefusal) as exc_info:
        assert_url_safe_to_fetch("http://10.0.0.5/secret")
    assert exc_info.value.code == "CAPTURE_URL_BLOCKED"


def test_link_local_metadata_refused() -> None:
    with pytest.raises(DeskRefusal) as exc_info:
        assert_url_safe_to_fetch("http://169.254.169.254/latest/meta-data/")
    assert exc_info.value.code == "CAPTURE_URL_BLOCKED"


def test_dns_name_resolving_to_loopback_refused() -> None:
    with pytest.raises(DeskRefusal) as exc_info:
        assert_url_safe_to_fetch(
            "http://evil.example/internal",
            resolve=_loopback_resolve,
        )
    assert exc_info.value.code == "CAPTURE_URL_BLOCKED"
    assert "127.0.0.1" in exc_info.value.what_happened


def test_dns_name_resolving_to_metadata_refused() -> None:
    with pytest.raises(DeskRefusal) as exc_info:
        assert_url_safe_to_fetch(
            "http://metadata.internal/latest/meta-data/",
            resolve=_meta_resolve,
        )
    assert exc_info.value.code == "CAPTURE_URL_BLOCKED"


def test_public_host_allowed() -> None:
    cleaned = assert_url_safe_to_fetch(
        "https://example.com/page",
        resolve=_public_resolve,
    )
    assert cleaned.startswith("https://example.com")


def test_file_scheme_refused() -> None:
    with pytest.raises(DeskRefusal) as exc_info:
        assert_url_safe_to_fetch("file:///etc/passwd")
    assert exc_info.value.code == "CAPTURE_URL_INVALID"


def test_scheme_must_remain_http_after_redirect() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "public.example":
            return httpx.Response(302, headers={"Location": "file:///etc/passwd"})
        return httpx.Response(200, content=b"ok")

    with pytest.raises(DeskRefusal) as exc_info:
        safe_http_get(
            "https://public.example/start",
            resolve=_public_resolve,
            transport=httpx.MockTransport(handler),
        )
    assert exc_info.value.code == "CAPTURE_URL_INVALID"


def test_redirect_from_public_to_loopback_refused() -> None:
    def resolve(hostname: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
        if hostname in {"127.0.0.1", "localhost"}:
            return [ipaddress.ip_address("127.0.0.1")]
        return [ipaddress.ip_address("93.184.216.34")]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "public.example":
            return httpx.Response(
                302,
                headers={"Location": "http://127.0.0.1:8000/api/cases"},
            )
        return httpx.Response(200, content=b"LEAKED")

    with pytest.raises(DeskRefusal) as exc_info:
        safe_http_get(
            "https://public.example/redirect",
            resolve=resolve,
            transport=httpx.MockTransport(handler),
        )
    assert exc_info.value.code == "CAPTURE_URL_BLOCKED"
    assert "127.0.0.1" in exc_info.value.what_happened


def test_redirect_to_private_lan_refused() -> None:
    def resolve(hostname: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
        if hostname.startswith("10."):
            return [ipaddress.ip_address(hostname)]
        return [ipaddress.ip_address("93.184.216.34")]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "public.example":
            return httpx.Response(302, headers={"Location": "http://10.0.0.8/admin"})
        return httpx.Response(200, content=b"nope")

    with pytest.raises(DeskRefusal) as exc_info:
        safe_http_get(
            "https://public.example/r",
            resolve=resolve,
            transport=httpx.MockTransport(handler),
        )
    assert exc_info.value.code == "CAPTURE_URL_BLOCKED"


def test_streamed_body_over_limit_refused() -> None:
    """Size cap aborts during stream, not after full materialization (F-20)."""
    oversized = b"x" * (MAX_BODY_BYTES + 1)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=oversized, headers={"content-type": "text/plain"})

    with pytest.raises(DeskRefusal) as exc_info:
        safe_http_get(
            "https://public.example/big",
            resolve=_public_resolve,
            transport=httpx.MockTransport(handler),
        )
    assert exc_info.value.code == "CAPTURE_TOO_LARGE"


def test_capture_url_preserves_ssrf_refusal_code_from_fetch(engine: Engine, tmp_path: Path) -> None:
    """F-17: DeskRefusal from fetch must not be remapped to CAPTURE_FETCH_FAILED."""
    vault = VaultStore(tmp_path / "vault")

    def blocked_fetch(url: str) -> tuple[bytes, str]:
        raise DeskRefusal(
            code="CAPTURE_URL_BLOCKED",
            what_happened=f"blocked {url}",
            what_was_preserved="n/a",
            what_was_not_changed="n/a",
            what_you_can_do="stop",
        )

    with connection_scope(engine) as conn:
        case = create_case(conn, CreateCaseInput(title="SSRF"))
        run = create_run(
            conn,
            CreateRunInput(case_id=case.case_id, question="Q?", scope="s"),
        )
        approve_run(conn, ApproveRunInput(run_id=run.run_id))
        packet = claim_next_run(conn, ClaimNextRunInput())
        assert packet.run is not None
        # Pass _validate_url (public host) then refuse inside fetch — simulates redirect SSRF.
        with pytest.raises(DeskRefusal) as exc_info:
            capture_url(
                conn,
                CaptureUrlInput(
                    run_id=run.run_id,
                    url="https://example.com/page",
                    claim_token=packet.run.claim_token,
                ),
                vault=vault,
                fetch=blocked_fetch,
            )
    assert exc_info.value.code == "CAPTURE_URL_BLOCKED"


def test_capture_url_service_refuses_loopback(engine: Engine, tmp_path: Path) -> None:
    vault = VaultStore(tmp_path / "vault")
    with connection_scope(engine) as conn:
        case = create_case(conn, CreateCaseInput(title="SSRF"))
        run = create_run(
            conn,
            CreateRunInput(case_id=case.case_id, question="Q?", scope="s"),
        )
        approve_run(conn, ApproveRunInput(run_id=run.run_id))
        packet = claim_next_run(conn, ClaimNextRunInput())
        assert packet.run is not None
        with pytest.raises(DeskRefusal) as exc_info:
            capture_url(
                conn,
                CaptureUrlInput(
                    run_id=run.run_id,
                    url="http://127.0.0.1:8000/api/cases",
                    claim_token=packet.run.claim_token,
                ),
                vault=vault,
                fetch=lambda u: (_ for _ in ()).throw(AssertionError(f"fetched {u}")),
            )
    assert exc_info.value.code == "CAPTURE_URL_BLOCKED"
