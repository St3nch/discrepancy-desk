# Review — Ticket 10a (registration guard and interaction tests)

**Date:** 2026-08-06
**Reviewer:** Claude (seam checks + steward)
**Verdict:** Accept. No findings.

No product behaviour changed. Two pieces of enforcement that had been assumed to exist.
Suite verified by the reviewer: 156 passed, exit 0.

---

## F-03 — closed after nine tickets

Open since ticket 01, when `api_operation_names()` was written with no call site and the
review said "add a test or delete it, either is fine, silence is not." Silence won for nine
tickets while `API_ONLY` grew to sixteen entries of registry that constrained nothing.

`tests/test_transport_registration.py` now enforces both directions and names the offending
operations rather than reporting that counts differ.

**The check that mattered on review: it fails closed rather than vacuously.** A subset
assertion over an empty set passes silently, so if route discovery ever broke and returned
nothing, a naive version would go green. Here the second assertion — registered names with no
route — fires with the full registry. Route naming also falls back to the endpoint function
name in FastAPI, so a route added without an explicit name lands outside the registry and
fails rather than escaping the check.

The partition test carries the safety-critical assertion directly:
`API_ONLY.isdisjoint(mcp_tool_names())`. Human-authority operations cannot appear on MCP.

**Test-only enforcement accepted, and the reasoning recorded** because the asymmetry with MCP
will look like an oversight later. MCP fails closed at application startup via
`build_mcp_server`; the API registry fails in CI. That is right: the direction that must never
drift — a human operation reachable from MCP — already raises at startup, and API route drift
is a developer error that cannot reach production without passing CI. Adding an import-time
route scan to the app factory would introduce a runtime failure mode to catch what CI already
catches. The implementer raised the asymmetry himself and left it undone pending a decision;
this is the decision.

---

## Interaction tests — eight pairs

`tests/test_operation_interactions.py`, with a docstring saying why the file exists and that
adding a governed operation means adding a pair.

Every defect that has broken this project has been *operation A changes what operation B
reports* — F-07, F-25b, F-26, F-32, F-34, F-38 — and not one was caught by a test. Each
layer's tests were green every time, which is the sentence in `codingstandards.md` describing
how the previous build failed.

Read `test_attest_then_attach_lead_then_gauge_stale` as representative: it asserts the gauge
reads complete, performs the interfering operation, asserts the **second** operation's report
changed, and then asserts the gate itself refuses. Three assertions across the seam rather
than two calls and a happy ending.

### The implementer's pair selection was better than the reviewer's list

He was asked which pairs he thought more likely to break than the ones specified, and which
would be filler. Both halves of the answer were taken.

**Dropped as filler, correctly:** `create_run → list_runs`; `create_case → get_case` (the F-07
shape is historical — both paths are now unscoped, so the pair tests nothing);
`dispose_lead → list_leads` (inbox filter only).

**Added, not on the reviewer's list:** a second `claim_next_run` while a run is held (F-25b,
pure concurrency authority); cite-then-examine across write paths (F-32); and cancel-leftover
then attest with reported examined ids — the wedge ticket 10 fixed, which will re-break if
either `cancel_run` or `attest_coverage` drifts.

**Skipped with a stated trigger:** `promote_lead → get_case`, on the grounds that promote is
currently `create_case` plus `attach_lead` with one extra status write, and attach is already
covered — to be added if promote ever diverges from attach on capture ownership. That is the
right shape for a deferral: a condition, not a maybe.

---

## Note carried forward

The interaction tests run multiple service calls inside one `connection_scope`, so they share
a transaction where production would use one per call. Consistent with the seam-test
convention established in ticket 01 and not a defect, but it means these tests do not exercise
the real transactional boundary between operations. Worth knowing before anyone reads a green
run as proof that a two-call sequence is atomic in production. It is not — by design.
