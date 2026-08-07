"""F-51 — client `/api/…` paths must resolve on the API router.

F-03 closed wiring.py ↔ router bidirectionally. That still left client/src/api.ts
unverified: a path the browser calls that the router does not serve fails as
Vite proxy fallthrough to index.html (JSON.parse: unexpected character at line 1)
with the full suite green.

This test extracts literal fetch paths from the client and asserts each template
matches a registered FastAPI route (method + path segments).
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.routing import APIRoute

from desk.transports.api import router as api_router

_CLIENT_API = Path(__file__).resolve().parents[1] / "client" / "src" / "api.ts"

# fetch("/api/…") or fetch(`/api/…${id}…`, { method: "POST", ... })
_FETCH_RE = re.compile(
    r"fetch\(\s*(`[^`]+`|\"[^\"]+\")\s*(?:,\s*\{([^}]*)\})?",
    re.MULTILINE,
)


def _client_fetch_calls() -> list[tuple[str, str]]:
    """Return (method, path_template) pairs from client/src/api.ts."""
    text = _CLIENT_API.read_text(encoding="utf-8")
    calls: list[tuple[str, str]] = []
    for match in _FETCH_RE.finditer(text):
        raw = match.group(1)[1:-1]  # strip quotes/backticks
        opts = match.group(2) or ""
        method = "GET"
        mm = re.search(r'method:\s*"(\w+)"', opts)
        if mm:
            method = mm.group(1).upper()
        # Drop query string (listLeads uses optional ?inbox_status=).
        template = raw.split("?", 1)[0]
        # Replace ${expr} with {param} for segment matching.
        template = re.sub(r"\$\{[^}]+\}", "{param}", template)
        # Query-only interpolation: `/api/leads${q}` → `/api/leads{param}` with
        # no slash before the placeholder — that is not a path segment.
        if template.endswith("{param}") and not template[: -len("{param}")].endswith("/"):
            template = template[: -len("{param}")]
        calls.append((method, template))
    return calls


def _segment_pattern(path: str) -> list[str]:
    """Normalise path to segments; `{anything}` → `{p}`."""
    path = path.strip()
    if path.startswith("/api/"):
        path = path[len("/api") :]
    elif path == "/api":
        path = "/"
    segs = [s for s in path.strip("/").split("/") if s]
    out: list[str] = []
    for s in segs:
        if (s.startswith("{") and s.endswith("}")) or s == "{param}":
            out.append("{p}")
        else:
            out.append(s)
    return out


def _router_patterns() -> list[tuple[str, list[str]]]:
    patterns: list[tuple[str, list[str]]] = []
    for route in api_router.routes:
        if not isinstance(route, APIRoute):
            continue
        segs = _segment_pattern(route.path)
        for method in route.methods or []:
            if method in {"HEAD", "OPTIONS"}:
                continue
            patterns.append((method.upper(), segs))
    return patterns


def test_client_api_paths_resolve_on_router() -> None:
    """Every fetch path in client/src/api.ts matches a router method+path."""
    calls = _client_fetch_calls()
    assert calls, "expected at least one fetch() in client/src/api.ts"
    router = _router_patterns()
    assert router, "API router has no routes — discovery failed open"

    missing: list[str] = []
    for method, template in calls:
        want = _segment_pattern(template)
        matched = any(m == method and segs == want for m, segs in router)
        if not matched:
            missing.append(f"{method} {template}")

    assert not missing, (
        "client/src/api.ts paths with no matching API route (F-51 — Vite will "
        f"serve index.html and JSON.parse will fail): {missing}"
    )


def test_client_api_path_extraction_covers_known_operations() -> None:
    """Smoke: extraction sees core operations so an empty scrape cannot pass."""
    calls = _client_fetch_calls()
    methods_paths = {(m, p) for m, p in calls}
    # Static paths that must appear (no params).
    assert ("GET", "/api/cases") in methods_paths
    assert ("POST", "/api/cases") in methods_paths
    assert ("POST", "/api/angles") in methods_paths
    assert ("POST", "/api/quotation-shelf") in methods_paths
