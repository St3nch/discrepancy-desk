# Review — Ticket 03 (run dispatch and claim)

**Date:** 2026-08-05
**Reviewer:** Claude, out-of-loop, via filesystem access
**Verdict:** Accepted after F-10 and F-11 were fixed.

*Backfilled from the review conversation. Findings are recorded here because commit
messages reference finding numbers and those numbers previously pointed nowhere.*

---

## Standing checks

| Check | Result |
|---|---|
| Vocabulary reconciliation | F-10 |
| Fail-open inventory | F-11 |
| Destructive-write inventory | **Clean.** `approve_run` writes `status` and `updated_at`; both in the input model |
| Dead-capability inventory | **Clean.** All four operations have call sites; probe surface removed as F-08 scheduled |
| Write-once inventory | N/A — no append-only chains yet |
| Projection completeness | **Clean.** `list_runs` surfaces every status the operator can act on |

---

## What held

**The conditional update in `claim_next_run`** — `WHERE id = ? AND status = 'approved'`
with a `rowcount` check — was built without being asked for. A plain
select-then-update would have let two executors claim the same run and would have
passed every acceptance criterion.

**`test_run_status_check_rejects_unknown`** proves the CHECK actually rejects, which is
the necessary complement to proving it accepts.

**The probe removal landed with a real `downgrade()`** recreating the tables rather
than a one-way drop.

---

## Findings

### F-10 — Vocabulary reconciliation was one-directional

**Severity:** Low-medium. **Closed.**

`test_run_status_check_accepts_full_vocabulary` iterated `RUN_STATUSES` and inserted
each value, so a value present in Python but missing from the CHECK failed loudly.
The reverse was uncovered: a value added to the migration's frozen `_RUN_STATUSES`
copy but not to `run_status.py` would pass silently, and the schema would accept a
status no Python code knew about.

The migration keeping its own frozen copy is correct — migrations must not import
application code — and that is exactly what makes divergence possible.

**Resolution:** a test reading the CHECK clause from `sqlite_master`, extracting the
quoted values, and asserting set equality with `RUN_STATUSES`. Later generalised into
`tests/test_check_enums.py` by F-30.

### F-11 — No `busy_timeout`, so a write conflict leaked a driver error

**Severity:** Medium. **Closed.**

`apply_connection_pragmas` set `foreign_keys` and `journal_mode` but not
`busy_timeout`, which defaults to 0. Any contended write failed immediately with
`OperationalError: database is locked` rather than waiting.

WAL keeps readers from blocking writers, but `claim_next_run` is a write and an
executor polls it on a loop while the operator uses the browser client. Two writers
is the steady state, not an edge case. An unhandled `OperationalError` propagates as a
500 with driver text, breaking the rule that no transport leaks internals.

The conditional update handled the *logical* race; this was the *physical* one
underneath it.

**Resolution:** `PRAGMA busy_timeout=5000` set alongside the other pragmas, read back
and verified the same way. An exhausted timeout maps to `DeskRefusal` with code
`DATABASE_BUSY` rather than a 500 — after five seconds the condition is still
transient and retryable, and the code is specific enough for an executor to act on.

---

## Convention recorded from this ticket

**Empty result for expected absence; refusal for failure.** `claim_next_run` returns
`run=None` when no run is approved, not a `DeskRefusal`. Idle is the normal polling
steady state, and a refusal would force every quiet poll through the
error-and-self-correct path. Recorded in `codingstandards.md` because ticket 08's
close and any later polling tool face the same choice.

---

## Note carried forward

`claim_next_run` returning `run=None` when it *loses* a race is slightly wrong —
another approved run may be available and the executor is told to idle. Irrelevant
with one executor and serialised cases. Becomes real if a retry loop is added.
