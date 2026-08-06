# Review — Ticket 07 (suspend and resume)

**Date:** 2026-08-05
**Reviewers:** Claude (seam checks) and GPT (spec), independently
**Verdict:** Accepted after F-26 through F-29 were fixed. Both axes accepted.

*Backfilled from the review conversation.*

---

## Standing checks

| Check | Result |
|---|---|
| Vocabulary reconciliation | **Clean.** `suspended` is the canonical status; no second stored state invented |
| Fail-open inventory | **F-26** — a suspended run wedged its case permanently |
| Destructive-write inventory | **F-28** — the v1 defect pattern, recurring |
| Dead-capability inventory | **F-26** — `cancelled` still unreachable |
| Write-once inventory | **F-28** |
| Projection completeness | **F-27** — the executor had no read of its own run |

---

## Findings

### F-26 — A suspended run permanently wedged its case

**Severity:** Blocking. **Closed.**

A suspended run has no lease, so `reclaim_expired_leases` never touched it — that
function only considers `claimed` runs with a non-null lease. `suspended` is in
`ACTIVE_CLAIM_STATUSES`, so the case refused to approve any other run. The only exit
was `answer_suspended_run`.

If the operator never answered — unanswerable question, incoherent executor, garbage
run — that case was blocked forever, with no remedy short of editing the database.

`cancelled` had been in the run-status vocabulary since ticket 03 and was still
unreachable. This is where it came due.

**Resolution:** human-only `cancel_run` on `/api`, from `draft`, `approved`, `claimed`,
or `suspended`, clearing lease and token and preserving captures, claims, and
suspension history. Not reachable from MCP — an executor abandoning its own work is not
something this system permits. Calls `reclaim_expired_leases` first so a page-stale
claimed run does not refuse oddly.

### F-27 — The executor had no governed read of its own run

**Severity:** Blocking. **Closed.**

The narrow symptom: a resumed executor could not retrieve the operator's answer.
`answer_suspended_run` recorded it, the run returned to `claimed`, and no MCP operation
delivered it. **A claim token proves authority to continue, not knowledge of what was
decided.**

The real gap was wider. Once a run was claimed, the executor had no way to read its own
run state at all — `claim_next_run` returns only `approved` runs, and there is no
`get_run` on MCP. After a refusal, after a resume, after anything, the executor was
blind to the run it held.

**Resolution:** `read_case_context(case_id, claim_token)`, already in the fixed
eight-tool surface, rather than a ninth tool. The token must match a `claimed` or
`suspended` run on that case; wrong or missing gives `RUN_CLAIM_STALE`. Payload carries
the held run's status, question, scope, rubric, budget and usage, claims made, full
suspension history, and the current suspension. Lease refreshed when claimed, not
when suspended — a suspended run has no lease, and pretending otherwise would have
reintroduced F-25a.

**Solving the general case means tickets 08 onward inherit a working executor read
rather than accumulating special cases.**

### F-28 — A second suspension destroyed the first — the v1 defect pattern

**Severity:** Blocking. **Closed.**

`suspend_run` wrote eight columns in one update, including `human_answer=None` and
`answered_at=None`, overwriting any prior suspension.

This is precisely the failure that motivated the no-partial-update rule in ticket 01: a
review-status write in the previous build nulled a populated note field because the
service wrote all four columns unconditionally. Same mechanism, same silence.

Doctrine says the database remembers, and D9 says an answer resolves *this instance* —
which presupposes instances. A run that suspended twice had no record the first
question was ever asked or answered.

**Resolution:** durable `run_suspensions` rows with `UNIQUE(run_id, ordinal)`, question,
uncertainty, default action, timestamps, and answer. The projection columns on `runs`
remain for list rendering and may be overwritten freely.

**Pattern established, now stated twice in the codebase: history is never the
projection.**

### F-29 — The interface did not distinguish instance from class

**Severity:** Medium. **Closed.**

D9: *"Answering a suspended question resolves this instance; amending a rubric resolves
the class. The interface must distinguish them."* Ticket 07 is where that interface
first existed, so the obligation came due.

**Resolution:** `INSTANCE_VS_CLASS_NOTICE` on `RunRecord` when status is `suspended`,
rendered in the suspension panel, asserted in API and client tests. No rubric editor —
the requirement was to distinguish the remedies, not to expand scope.

---

## What held

`suspend_run` MCP-only and `answer_suspended_run` HTTP-only is the correct transport
split. Clearing the lease so a human wait is not treated as abandonment is correct.
Keeping the token so the same claim instance continues is correct.

After this ticket, `MCP_AND_API` is **empty** — every operation is deliberately on one
surface or the other, with nothing sitting in both by default. The transport rule fully
realised rather than merely stated.

---

## Scope note

`cancel_run` was adjacent scope, added from F-26 rather than the ticket's original
acceptance criteria. Compatible with the canonical run lifecycle, human-only, preserves
prior work. Recorded in the commit message so the ticket's history is honest about what
it grew.
