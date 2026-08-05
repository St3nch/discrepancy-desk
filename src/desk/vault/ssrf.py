"""SSRF guard for capture fetches.

The URL is supplied by an untrusted executor. Transport separation (ADR 10) is
void if capture_url can pull the Desk's own /api surface or cloud metadata.
Validation is on *resolved* addresses, not hostname strings, and is re-applied
after every redirect hop.

Accepted residual risk — DNS rebinding: we resolve the hostname for the policy
check, then httpx resolves again when connecting. A short-TTL record could return
a public address on the first lookup and a loopback/private address on the
second. Closing that properly means connecting to the validated IP with an
explicit Host header (awkward in httpx). For a single-operator local tool this
is accepted and documented rather than left unnoticed.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from urllib.parse import urljoin, urlparse

from desk.refusals import DeskRefusal

# Hard hop cap for manual redirect following.
MAX_REDIRECTS = 5

# Abort streaming once this many bytes have been received (before full materialize).
MAX_BODY_BYTES = 5_000_000

_ALLOWED_SCHEMES = frozenset({"http", "https"})

ResolveFn = Callable[[str], list[ipaddress.IPv4Address | ipaddress.IPv6Address]]


def _refusal(code: str, what: str, *, do: str) -> DeskRefusal:
    return DeskRefusal(
        code=code,
        what_happened=what,
        what_was_preserved="Existing captures and the run budget are unchanged.",
        what_was_not_changed=(
            "No capture was written; no request was completed to a blocked target."
        ),
        what_you_can_do=do,
    )


def _normalize_ip(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    """Unwrap IPv4-mapped IPv6 so policy checks see the embedded v4 address.

    Python < 3.12.4 does not consult ipv4_mapped when evaluating is_global on
    ::ffff:127.0.0.1. Normalize version-independently before any property check.
    """
    if ip.version == 6 and getattr(ip, "ipv4_mapped", None) is not None:
        mapped = ip.ipv4_mapped
        if mapped is not None:
            return mapped
    return ip


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True if the address is not a public internet destination.

    Uses address properties after IPv4-mapped normalization, not string matching.
    Covers loopback, private, link-local, reserved, multicast, unspecified —
    including the Desk's own listen address when it is non-global (always true
    for 127.0.0.1 / typical LAN binds).
    """
    ip = _normalize_ip(ip)
    return not ip.is_global


def resolve_host_ips(hostname: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Resolve hostname to IP addresses. Raises DeskRefusal on DNS failure."""
    try:
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise _refusal(
            "CAPTURE_DNS_FAILED",
            f"Could not resolve hostname {hostname!r}.",
            do="Check the URL hostname and retry.",
        ) from None
    ips: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    seen: set[str] = set()
    for info in infos:
        addr = str(info[4][0])
        if addr in seen:
            continue
        seen.add(addr)
        try:
            ips.append(ipaddress.ip_address(addr))
        except ValueError:
            continue
    if not ips:
        raise _refusal(
            "CAPTURE_DNS_FAILED",
            f"Hostname {hostname!r} resolved to no usable addresses.",
            do="Check the URL hostname and retry.",
        )
    return ips


def assert_url_safe_to_fetch(
    url: str,
    *,
    resolve: ResolveFn = resolve_host_ips,
) -> str:
    """Validate scheme and resolved addresses. Returns cleaned URL or raises.

    Non-global destinations (loopback, private, link-local, reserved, multicast)
    are refused. That subsumes blocking the Desk's own listening port when bound
    on such addresses — no separate port check is needed or present.
    """
    cleaned = url.strip()
    if not cleaned:
        raise _refusal(
            "CAPTURE_URL_EMPTY",
            "capture_url was called with an empty URL.",
            do="Retry with a non-empty http(s) URL.",
        )

    parsed = urlparse(cleaned)
    scheme = (parsed.scheme or "").lower()
    if scheme not in _ALLOWED_SCHEMES or not parsed.hostname:
        raise _refusal(
            "CAPTURE_URL_INVALID",
            f"URL {cleaned!r} is not an absolute http(s) URL with a host.",
            do="Retry with a full URL beginning with http:// or https://.",
        )

    if parsed.username is not None or parsed.password is not None:
        raise _refusal(
            "CAPTURE_URL_BLOCKED",
            "URLs with embedded credentials are not allowed for capture.",
            do="Retry with a URL that has no userinfo component.",
        )

    hostname = parsed.hostname
    ips = resolve(hostname)

    for ip in ips:
        if _is_blocked_ip(ip):
            display = _normalize_ip(ip)
            raise _refusal(
                "CAPTURE_URL_BLOCKED",
                (
                    f"URL host {hostname!r} resolves to non-public address "
                    f"{display} (loopback, private, link-local, or reserved)."
                ),
                do="Capture only public internet http(s) resources.",
            )

    return cleaned


def _read_body_capped(response: object, *, max_bytes: int = MAX_BODY_BYTES) -> bytes:
    """Stream response body; refuse once max_bytes would be exceeded."""
    chunks: list[bytes] = []
    total = 0
    # httpx Response.iter_bytes
    for chunk in response.iter_bytes():  # type: ignore[attr-defined]
        if not chunk:
            continue
        total += len(chunk)
        if total > max_bytes:
            raise _refusal(
                "CAPTURE_TOO_LARGE",
                (f"Response body exceeded {max_bytes} bytes while streaming; download aborted."),
                do=("Capture a smaller resource, or raise the size limit in a later ticket."),
            )
        chunks.append(chunk)
    return b"".join(chunks)


def safe_http_get(
    url: str,
    *,
    timeout: float = 30.0,
    max_redirects: int = MAX_REDIRECTS,
    max_bytes: int = MAX_BODY_BYTES,
    resolve: ResolveFn = resolve_host_ips,
    transport: object | None = None,
) -> tuple[bytes, str]:
    """GET with SSRF checks on the initial URL and every redirect hop.

    Redirects are followed manually so each Location is re-validated (scheme +
    resolved addresses). Automatic follow_redirects is not used. Body is streamed
    and aborted if it exceeds max_bytes.

    ``transport`` is for tests (e.g. httpx.MockTransport); production leaves it None.
    """
    import httpx

    current = assert_url_safe_to_fetch(url, resolve=resolve)
    hops = 0

    client_kwargs: dict[str, object] = {
        "follow_redirects": False,
        "timeout": timeout,
    }
    if transport is not None:
        client_kwargs["transport"] = transport

    with httpx.Client(**client_kwargs) as client:  # type: ignore[arg-type]
        while True:
            try:
                response = client.get(current)
            except httpx.TimeoutException:
                raise _refusal(
                    "CAPTURE_FETCH_TIMEOUT",
                    f"Timed out fetching {current!r}.",
                    do="Retry later or use a different URL.",
                ) from None
            except httpx.RequestError:
                raise _refusal(
                    "CAPTURE_FETCH_FAILED",
                    f"Failed to fetch {current!r}.",
                    do="Check the URL is reachable and retry capture_url.",
                ) from None

            if response.is_redirect:
                hops += 1
                if hops > max_redirects:
                    raise _refusal(
                        "CAPTURE_REDIRECT_LIMIT",
                        f"Exceeded {max_redirects} redirects while fetching {url!r}.",
                        do="Use a URL that does not redirect through a long chain.",
                    )
                location = response.headers.get("location")
                if not location:
                    raise _refusal(
                        "CAPTURE_FETCH_FAILED",
                        f"Redirect response from {current!r} had no Location header.",
                        do="Retry with a different URL.",
                    )
                next_url = urljoin(current, location)
                current = assert_url_safe_to_fetch(next_url, resolve=resolve)
                continue

            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                raise _refusal(
                    "CAPTURE_HTTP_ERROR",
                    f"HTTP {status} fetching {current!r}.",
                    do="Use a URL that returns a successful response.",
                ) from None

            content_type = response.headers.get("content-type", "application/octet-stream")
            body = _read_body_capped(response, max_bytes=max_bytes)
            return body, content_type
