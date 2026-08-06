# Review — Ticket 05 (claim proposal)

**Date:** 2026-08-05
**Reviewer:** Claude, out-of-loop, via filesystem access
**Verdict:** Accepted after F-21 and F-22 were fixed.

*Backfilled from the review conversation.*

This is the ticket the architecture rests on. `propose_claim` is the enforcement seam
that makes an untrusted executor safe; everything built before it exists to make this
step meaningful.

---

## Standing checks

| Check | Result |
|---|---|
| Vocabulary reconciliation | **F-21 — the significant one** |
| Fail-open inventory | F-21 |
| Destructive-write inventory | **Clean.** The `captures.status` update writes one column |
| Dead-capability inventory | F-23 — `examined` unreachable |
| Write-once inventory | N/A |
| Projection completeness | Clean, though see F-24 |

---

## What held

The five steps run in ADR 9's order, fail closed on first failure, and carry distinct
codes. `_verify_quote_binding` runs per binding rather than in aggregate, so a claim
with three bindings fails on the first bad one and reports which.

The inference path is well designed: it requires citations, *refuses* capture bindings
on that path, and validates that cited claims exist and belong to the same case.
`CAPTURE_WRONG_CASE` is a boundary that was not asked for and should have been.

---

## Findings

### F-21 — The five evidence dimensions had no CHECK constraints

**Severity:** Medium-high. **Closed.**

`0005_claims` declared `source_basis`, `corroboration`, `certainty`, `posture`, and
`publication_risk` as bare `TEXT NOT NULL`. Validation lived only in
`_validate_dimensions`.

`runs.status` already carried a CHECK plus a bidirectional reconciliation test — the
standard set two tickets earlier — and the dimensions are the more important
vocabulary, because they *are* the evidence model.

The only thing preventing `certainty='definitely_true'` in the database was one Python
function. Any future write path, migration, or fix-up script bypassed it silently.

**Resolution:** CHECK constraints on all five, plus a test parsing each column's CHECK
from `sqlite_master` and asserting set equality with the Python frozensets. Later
folded into `tests/test_check_enums.py` by F-30.

### F-22 — Quote verification required the quote to equal the entire element

**Severity:** High. **Closed by implementing region locators.**

`if binding.quoted_text != element_text` meant a claim could only ever quote a complete
block — a whole `<p>`, a whole `<li>` — never a sentence within one.

That is maximally strong verification, and preferable to a substring check, which a
single word would pass. But it collides with what the product needs: §11 makes
quotations first-class with exact text, speaker, and attribution frame, and ticket 11's
quotation shelf wants the sentence someone actually said.

F-16 had scheduled `e/{n}/r/{start}-{end}` for "the same change that first uses region
addressing." This was that change.

**Resolution:** region locators implemented rather than deferred a second time.
`_resolve_quotation_surface` resolves the locator to a surface string first, then
applies the same exact-equality check to whatever comes back — so precision was added
without weakening verification. Malformed locator forms are refused with
`LOCATOR_UNRESOLVED` rather than falling through to a default.

The range guard `0 <= start < end <= len(element_text)` rejects empty regions. A
zero-length quote would otherwise have matched trivially and passed verification — a
hole closed without being asked about.

| Locator | Quotation surface |
|---|---|
| `e/N` | Full `elements.text` |
| `e/N/r/START-END` | `elements.text[START:END]`, end exclusive |

### F-23 — The `examined` capture status was unreachable

**Severity:** Low. **Closed by ticket 08.**

D11 defines cited, examined, unexamined. `propose_claim` set `cited`; nothing set
`examined`. Confirmed as belonging to run close and documented in `CONTEXT.md` as such,
then implemented in ticket 08 — where F-32 established that it must be *reported*
rather than inferred.

### F-24 — Inference claims do not inherit publication risk from cited claims

**Severity:** Deferred to ticket 11. **OPEN.**

§10 says Angle Room items inherit publication risk from their claims. An inference
reasoning over a `living_private` claim can currently be recorded `not_applicable`,
laundering the risk one level up.

Out of scope for ticket 05. Noted in the `claims.py` module docstring. **Must close
before ticket 11's confirmation and use paths.**

---

## Notes carried forward

`stored_qualification` strips for required postures and stores raw otherwise — strip in
both cases.

`list_claims_for_case` runs two extra queries per claim, so a case with 150 claims
costs roughly 300 queries. D4 explicitly anticipates that volume; worth a single
grouped fetch before the case view gets real use.
