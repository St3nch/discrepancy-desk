# 08 — Run close: agenda and open questions

**What to build:** Closing a run presents, in order: the proposed agenda of new open
questions (with rationale and proposed scope) for the operator to approve, reject, edit, or
replace; counts of captures made and claims proposed; the executor's self-reported
low-confidence areas; and full claim/capture detail behind a fold. Approved open questions
get a disposition and lineage back to the run and question that produced them.

**Blocked by:** 03 — Run dispatch and claim, 04 — Capture (Vault), 05 — Claim proposal

**Status:** ready-for-agent

- [ ] `close_run(run_id, questions, ...)` accepts the executor's proposed new open questions
      and self-reported low-confidence areas, and moves the run to `complete`.
- [ ] The run-close view in the browser client leads with the proposed agenda, not with
      claims — claim/capture detail sits behind a fold, not one click from the top.
- [ ] Operator can approve, reject, edit the scope of, or replace each proposed open
      question.
- [ ] Approved open questions are recorded with a disposition:
      unresolved-likely-permanent, unresolved-awaiting-external-development, or
      not-yet-worked.
- [ ] Each open question and each claim records which run introduced it and which question
      prompted that run.
- [ ] The governed operations are tested at the agreed seam.
