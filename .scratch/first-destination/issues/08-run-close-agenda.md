# 08 — Run close: agenda and open questions

**What to build:** Closing a run presents, in order: the proposed agenda of new open
questions (with rationale and proposed scope) for the operator to approve, reject, edit, or
replace; counts of captures made and claims proposed; the executor's self-reported
low-confidence areas; and full claim/capture detail behind a fold. Approved open questions
get a disposition and lineage back to the run and question that produced them.

**Blocked by:** 03 — Run dispatch and claim, 04 — Capture (Vault), 05 — Claim proposal

**Status:** implemented (pending review; F-30–F-32 addressed)

- [x] `close_run(run_id, questions, ...)` accepts the executor's proposed new open questions
      and self-reported low-confidence areas, and moves the run to `complete`.
- [x] The run-close view in the browser client leads with the proposed agenda, not with
      claims — claim/capture detail sits behind a fold, not one click from the top.
- [x] Operator can approve, reject, edit the scope of, or replace each proposed open
      question.
- [x] Operator can author an open question with no prior proposal (F-31 / D5).
- [x] Approved open questions are recorded with a disposition:
      unresolved-likely-permanent, unresolved-awaiting-external-development, or
      not-yet-worked.
- [x] Each open question and each claim records which run introduced it and which question
      prompted that run.
- [x] Only executor-reported `examined_capture_ids` become `examined` (F-32); omitted uncited stay unexamined.
- [x] CHECK enum reconciliation is parameterised across all constrained columns (F-30).
- [x] The governed operations are tested at the agreed seam.
