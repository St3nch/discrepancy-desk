# Review — Ticket 04 (capture and the Vault)

**Date:** 2026-08-05
**Reviewer:** Claude, out-of-loop, via filesystem access
**Verdict:** Accepted after F-12 through F-20 were fixed.

*Backfilled from the review conversation.*

**F-12 is the most serious finding in the project to date** — the only one that was a
security hole rather than a correctness gap. It is recorded here in full because the
reasoning matters more than the fix.

---

## Standing checks

| Check | Result |
|---|---|
| Vocabulary reconciliation | **Clean.** Capture status uses `unexamined` per D11; parser name versioned |
| Fail-open inventory | **F-12 (critical)**, F-15 |
| Destructive-write inventory | **Clean.** Inserts only; the Vault refuses to overwrite and raises on hash collision |
| Dead-capability inventory | F-16 — `regions` unaddressable |
| Write-once inventory | **Clean.** `write_raw` writes once and verifies on collision |
| Projection completeness | **Clean.** Projection carries an explicit non-authoritative flag *and* banner |

---

## What held

Content-addressing with collision verification rather than blind overwrite. Budget
checked before fetch, with the refusal stating nothing was stored. `RUN_NOT_CLAIMED`
tying the Vault write path to the run registry. `projection_is_authoritative=False`
as a field rather than only a comment. Two captures of one URL correctly producing
two capture rows sharing one stored object — correct under D3, where two reads at
different times are two captures and any difference between them is itself evidence.

---

## Findings

### F-12 — The executor had an unrestricted server-side fetch primitive

**Severity:** Critical. **Closed.**

`_validate_url` checked scheme and non-empty netloc, and nothing else. The URL comes
from the executor, which AGENTS.md constraint 4 defines as untrusted.

An executor could call `capture_url("http://127.0.0.1:8000/api/cases")` and read the
Desk's own operator API — the human-only surface that ADR 10 and `wiring.py` exist to
keep off MCP. Or `http://169.254.169.254/latest/meta-data/` on a cloud host. Or sweep
the LAN. The bytes came back in `elements` and `projection_markdown`.

`follow_redirects=True` meant validating the input URL alone was insufficient: an
allowed external host can 302 to `127.0.0.1`.

**The transport separation was carefully built and this walked around it.** The
executor could not *call* `get_case`, but it could *fetch* it.

**Resolution** — `src/desk/vault/ssrf.py`:

- Hostname resolved via `getaddrinfo`; every resulting address checked with
  `ipaddress` properties, not string matching, so `0x7f.1`, `[::1]`, and DNS names
  pointing at loopback all fail after resolution
- `follow_redirects=False` with manual following, re-validating scheme and resolved
  addresses on every hop, capped at 5
- Credentials in the URL refused
- Tests exercising real bypasses: DNS name resolving to loopback, DNS name resolving
  to the metadata address, public host 302 to `127.0.0.1`, public host 302 to a
  private address, public host 302 to `file:///etc/passwd`

**Accepted residual risk, documented in the module docstring:** DNS rebinding. The
guard resolves the hostname, then httpx resolves again when connecting; a short-TTL
record could return public on the first lookup and loopback on the second. Closing it
properly means connecting to the validated IP with an explicit `Host` header. Accepted
for a single-operator local tool and recorded rather than left unnoticed.

### F-13 — "Byte-exact" was undefined, and ticket 05 depended on it

**Severity:** High. **Closed as a recorded decision.**

ADR 9 requires `quoted_text` to appear byte-exact at the locator. But `elements.text`
is not a byte range of the stored raw bytes — the parser strips whitespace, joins
buffers, and `convert_charrefs=True` turns `&amp;` into `&`. Element text is derived,
not extracted.

That is correct and necessary. It needed stating before ticket 05 implemented
verification against it.

**Resolution, recorded in `codingstandards.md` and the ticket 05 notes:** verification
compares `quoted_text` against `elements.text` for the addressed locator. Raw bytes
remain the archival record and integrity anchor; the parsed element is the quotation
surface.

### F-14 — Non-HTML content produced garbage rather than a refusal

**Severity:** Medium. **Closed.**

`parse_bytes` routed anything non-HTML to `_parse_plain`, which decodes with
`errors="replace"`. A PDF became one enormous element of replacement characters, and a
ticket 05 claim could have bound to it and passed verification — faithfully stored
garbage is still verifiable garbage.

**Resolution:** `assert_content_type_supported` runs before any Vault or Record write.
`CAPTURE_UNSUPPORTED_TYPE` names the media type and the parser. HTML sniffing as a
fallback when the server lies about or omits the type.

**Store-or-not decision:** do not store when the parse is refused. An unparseable
capture has no quotation surface, and an orphan Vault object with no elements is a
half-capture. When a real parser for the type exists, store and parse in one step.

### F-15 — Fetch failures collapsed to one code

**Severity:** Medium-low. **Closed.**

404, timeout, DNS failure, and TLS error need different next actions, which is what
the refusal contract exists for. Resolved by distinct codes in `safe_http_get`, and
by F-17 below, which stopped those codes being swallowed.

**Budget decision:** failed fetches do not consume budget. Budget counts *retained
captures*, not HTTP attempts. Timeouts, DNS failures, HTTP errors, SSRF blocks, and
unsupported types leave the slot free so flaky URLs do not burn the operator's
allowance. Retry cost is wall-clock, not budget.

### F-16 — `regions` rows were written but unaddressable

**Severity:** Low. **Closed by F-22 in ticket 05.**

Every element got one region spanning its full text, but locators were `e/{ordinal}`
with no region component, so nothing could reference one. Scheduled for "the same
change that first uses region addressing" — which turned out to be ticket 05, where the
`e/{n}/r/{start}-{end}` grammar was implemented.

---

## Follow-up findings from the F-12 fix

### F-17 — The broad `except Exception` swallowed every SSRF refusal

**Severity:** High. **Closed.**

`capture_url` caught all exceptions and remapped them to `CAPTURE_FETCH_FAILED`.
`DeskRefusal` is an `Exception`, so `CAPTURE_URL_BLOCKED`, `CAPTURE_REDIRECT_LIMIT`,
`CAPTURE_FETCH_TIMEOUT`, and `CAPTURE_HTTP_ERROR` were all remapped.

The initial `_validate_url` call sat outside the try, so blocked *input* URLs still
surfaced correctly — which is why the tests passed. But a **redirect to `127.0.0.1`**
was caught inside `fetch()` and reported as "check the URL is reachable and retry,"
telling the executor to retry a blocked target.

**Resolution:** `except DeskRefusal: raise` before the broad handler.

### F-18 — IPv4-mapped IPv6 addresses bypassed the check on Python 3.12.3

**Severity:** Medium. **Closed.**

The `ipaddress` correctness fix for IPv4-mapped IPv6 landed in 3.12.4. On 3.12.3 — the
version on this machine — `IPv6Address("::ffff:127.0.0.1").is_global` does not consult
the mapped v4 address, and `getaddrinfo` with `AF_UNSPEC` can return mapped forms.

**Resolution:** `_normalize_ip` unwraps IPv4-mapped addresses before any property
check, guarded with `getattr` so the behaviour does not depend on interpreter version
at all.

### F-19 — The `blocked_local_ports` check was unreachable

**Severity:** Low. **Closed by removal.**

Every address satisfying the port-check condition was already non-global and had
raised in the branch above. Dead code that read as an active control. Removed, with
the docstring explaining that non-global blocking subsumes it — no fake control.

### F-20 — Response size was capped after full materialisation

**Severity:** Low. **Closed.**

`response.content` materialised the whole body before the size check ran. Resolved by
streaming with a running byte count, aborting at `MAX_BODY_BYTES`.

---

## Note carried forward

The budget check is count-then-insert with no constraint, so two concurrent captures
could both pass. Serialised runs make this unlikely.
