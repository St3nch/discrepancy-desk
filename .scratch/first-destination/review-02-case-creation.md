# Review — Ticket 02 (case creation)

**Date:** 2026-08-05
**Reviewer:** Claude, out-of-loop, via filesystem access
**Scope:** `src/desk/service/cases.py`, `models.py`, `schema.py`, `wiring.py`,
`alembic/versions/0002_cases.py`, `tests/test_service_cases.py`, API routes
**Verdict:** Accept. F-07 and F-06 are closed by the D17 decision rather than fixed — see
below. F-08 needs a decision; F-09 needs confirmation of intent.

---

## Standing checks, results stated explicitly

| Check | Result |
|---|---|
| Vocabulary reconciliation | F-06 — superseded by D17 |
| Fail-open inventory | F-07 — the significant one; superseded by D17 |
| Destructive-write inventory | **Clean.** No updates exist; inserts and selects only |
| Dead-capability inventory | F-08 — open, needs a decision |
| Write-once inventory | N/A — no append-only chains yet |
| Projection completeness | F-09 — low, needs confirmation of intent |

---

## What holds

**`test_case_schema_has_no_complete_or_closed_status`** asserts the absence of a whole class
of column names, not just the ones currently avoided. A case never completes (D6), and this
is that rule enforced structurally rather than remembered.

**Ticket 01's conventions carried without drift.** Pydantic in and out, typed refusals, a
single `_StrictModel` base with `extra="forbid"`, service functions taking a `Connection`,
API-only wiring with matching route names. No shortcuts taken under the second ticket's
pressure, which is where house style usually starts eroding.

**Refusal codes are specific.** `CASE_TITLE_EMPTY` and `CASE_NOT_FOUND` are distinguishable
actions, which is the point of the `code` field.

---

## Findings

### F-06 — `"default"` was a magic string in three places, with two meanings for empty

**Status: closed by D17 (multi-brand cancelled). Removed rather than fixed.**

`CreateCaseInput.account_id`, `ListCasesInput.account_id`, and `list_cases`' own
`.strip() or "default"` each carried the literal independently.

More seriously, the same value meant two different things: `create_case` **refused** an empty
`account_id` with `CASE_ACCOUNT_EMPTY`, while `list_cases` **silently coerced** it to
`"default"`. One fail-closed, one fail-open, same field. A caller sending `""` got an error
from one operation and results from another.

### F-07 — `get_case` was not account-scoped

**Status: closed by D17. Removed rather than fixed.**

`list_cases` filtered `WHERE account_id = ?`. `get_case` filtered only on `id`, and
`GetCaseInput` had no `account_id` field, so it could not scope even in principle.

Nothing leaked — one account existed. But the stated reason for carrying `account_id` from
ticket 02 rather than adding it later was that scoping should be correct from the start. Half
the surface enforced the boundary and half did not, on the second ticket, and the half that
did not was the one returning full case detail.

**This finding is the direct cause of D17.** The correct response was not to add the missing
filter but to observe how quickly the boundary decayed and conclude that an in-instance
account boundary is the wrong mechanism. It has to hold in every query, projection, and join,
forever, and its failure is silent.

### F-08 — The probe surface is now dead capability

**Severity:** Low, but requires a decision rather than drift

`ensure_probe_parent`, `record_probe_note`, and `list_probe_notes` remain wired to both
transports, and `probe_parents` / `probe_notes` still exist, but the client's primary surface
is now cases. Ticket 01 named these temporary; nothing schedules their removal.

Temporary scaffolding that nothing removes is permanent.

**Decide one:** a migration dropping the probe tables and their wiring, or an explicit note
that they remain until ticket 03 puts real tools on the MCP surface and are dropped in the
same change. Either is fine. Silence is not.

### F-09 — The case projection omits open questions

**Severity:** Low; needs confirmation of intent

`GetCaseResult` carries `captures`, `claims`, `angles`, `renditions`. `CONTEXT.md` says a case
owns sources, claims, entities, conflicts, timeline, open questions, and angles. Open
questions are a first-class worked object under D5 and D6 and are absent from the shape.

Not wrong if the projection is intended to grow ticket by ticket. Worth confirming that is the
intent, rather than the current shape being read later as complete.

---

## Notes, no action required

**`_row_to_case` carries four `# type: ignore[attr-defined]`.** Acceptable here — SQLAlchemy
Core rows are awkward to type. But every future table gets a `_row_to_X`, and this pattern
compounds. Worth solving once with a typed row helper before there are twelve of them.

**`CASE_NOT_FOUND`'s `what_was_not_changed` reads "No case was read as missing,"** which is
garbled. The five-field refusal contract was designed for writes and reads sit awkwardly in
it. Establish the convention now: for read operations, state plainly that nothing was written.
