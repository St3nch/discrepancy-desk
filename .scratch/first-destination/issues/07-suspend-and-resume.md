# 07 — Suspend and resume

**What to build:** An executor working a claimed run can call `suspend_run` with a stated
question, what it's uncertain between, and its default action, moving the run to
`suspended-awaiting-human`. The operator sees the suspended run, answers, and the run
resumes.

**Blocked by:** 03 — Run dispatch and claim

**Status:** implemented (pending review; F-26–F-29 addressed)

- [x] `suspend_run(run_id, question, ...)` moves a claimed run to `suspended`
      and records the stated question, uncertainty, and default action.
- [x] The browser client surfaces suspended runs distinctly, requiring an operator answer
      before resuming.
- [x] The operator's answer is recorded and the run returns to `claimed` (same claim_token,
      new lease) for the executor to continue.
- [x] The governed operations are tested at the agreed seam.
- [x] F-26: human-only `cancel_run` escapes suspended/open runs without wedging the case.
- [x] F-27: `read_case_context` delivers held-run state and suspension answers to the executor.
- [x] F-28: durable `run_suspensions` rows; second suspend retains the first instance.
- [x] F-29: instance-vs-class notice on suspended run UI and API projection.
