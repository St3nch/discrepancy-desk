# Review — Ticket 08 (run close, agenda, open questions)

**Date:** 2026-08-05
**Reviewers:** Claude (seam checks) and GPT (spec), independently
**Verdict:** Accepted after F-30 through F-32 were fixed. Both axes accepted.

*Backfilled from the review conversation.*

---

## Standing checks

| Check | Result |
|---|---|
| Vocabulary reconciliation | **F-30** — two new enums unreconciled |
| Fail-open inventory | **F-32** — `examined` inferred rather than reported |
| Destructive-write inventory | **Clean.** |
| Dead-capability inventory | **F-31** — operator could not originate an open question |
| Write-once inventory | **Clean.** Open questions are durable rows |
| Projection completeness | **Clean.** `get_case` now fills `open_questions`, retiring the ticket 02 stub |

---

## What held

The close screen order follows D13, and the fold carries an explicit "not for
confirmation here" label — better than hiding claims silently, because it says *why*
they are folded, which is the part that stops the habit forming.

The whole close is atomic. Open questions, low-confidence rows, and examined marks all
land before the status update, but a stale-claim refusal rolls the transaction back, so
the refusal message stays accurate.

`UNIQUE(introduced_by_run_id, ordinal)` and the equivalent on low-confidence make
ordering an invariant rather than a convention. The `disposition IS NULL OR disposition
IN (...)` form is correct — pending and rejected items legitimately have no
disposition, and a plain `IN` would have forced a sentinel value.

---

## Findings

### F-30 — The two new enums had CHECK constraints but no reconciliation test

**Severity:** Medium. **Closed.**

`0010_run_close` defined `_DISPOSITIONS` and `_DECISIONS`; `models.py` defined
`OPEN_QUESTION_DISPOSITIONS` and `AGENDA_DECISIONS`. Nothing asserted they agreed — the
same gap F-10 closed for `runs.status` and F-21 for the evidence dimensions.

**Resolution:** `tests/test_check_enums.py` — one parameterised suite covering **every**
CHECK-constrained enum column: ten columns across four tables, bidirectional against
the Python frozensets, handling both the plain `IN` and nullable `IS NULL OR ... IN`
forms. Absorbs new enums by adding a tuple rather than a file.

### F-31 — The operator could only react to the executor's agenda, never originate

**Severity:** Blocking. **Closed.**

The only HTTP surface was `POST /open-questions/{id}/decide`, so every operator action
required an existing `open_question_id`. "Replace with mine" lived inside a proposed
item.

D5 requires the operator to approve, reject, edit scope, **or write his own**. That
fourth option was unreachable. If `close_run` proposed zero questions, the screen
rendered "No open questions proposed for this run" and offered no action — the research
agenda was bounded by whatever the executor happened to think of.

**That inverts the authority model. The executor proposes the agenda; it does not
define the space of possible agendas.**

**Resolution:** `create_operator_open_question`, HTTP-only, writing an `approved` row
directly with settled text and scope, disposition, decision timestamp, and full lineage.
Routing it through `pending` would have been theatre — an operator-authored question is
already decided by the act of writing it. Carries an `Operator-authored (not proposed
by the executor.)` rationale marker so provenance stays readable in a mixed list. Works
with an empty proposed agenda.

### F-32 — `examined` was inferred from absence of bindings

**Severity:** Blocking. **Closed.**

`_mark_unexamined_as_examined` selected `WHERE run_id = ? AND status = 'unexamined'` and
marked them all. That is inference from absence of a claim binding. The docstring above
it said *"an explicit editorial write at close — not inferred later from absence of
bindings"* — the word doing the work was "later." The inference had been moved to close
time, not removed.

D11's distinction is narrower: `examined` means the run looked and found nothing worth
claiming; `unexamined` means nobody looked. A capture whose locator map was truncated
at 50 elements with no `read_capture` call was fetched, not examined. Marking it
`examined` recorded a judgement the executor never made.

**This matters beyond tidiness.** The cited/examined/unexamined split is what makes an
honest corpus denominator possible later. "6 of 74 eligible" means nothing if 68 were
marked examined by a `WHERE` clause.

**Resolution:** `examined_capture_ids` on `close_run` — a report, not an inference. Only
reported captures become `examined`. Validation stronger than the finding asked for:
wrong-run captures refused, cited captures refused with
`EXAMINED_CAPTURE_ALREADY_CITED`, any status outside `unexamined` refused rather than
silently coerced, already-examined continuing rather than raising so replay is
idempotent without double-counting. Existing tests had encoded the automatic behaviour
and were rewritten rather than extended.

---

## Note recorded

`cancel_run` leaves capture status alone while `close_run` changes it. Deliberate, and
now stated in `cancel_run`'s docstring rather than left accidental: only an explicit
close report marks captures examined.
