# 07 — Suspend and resume

**What to build:** An executor working a claimed run can call `suspend_run` with a stated
question, what it's uncertain between, and its default action, moving the run to
`suspended-awaiting-human`. The operator sees the suspended run, answers, and the run
resumes.

**Blocked by:** 03 — Run dispatch and claim

**Status:** ready-for-agent

- [ ] `suspend_run(run_id, question, ...)` moves a claimed run to `suspended-awaiting-human`
      and records the stated question, uncertainty, and default action.
- [ ] The browser client surfaces suspended runs distinctly, requiring an operator answer
      before resuming.
- [ ] The operator's answer is recorded and the run returns to `claimed` (or an equivalent
      resumable state) for the executor to continue.
- [ ] The governed operations are tested at the agreed seam.
