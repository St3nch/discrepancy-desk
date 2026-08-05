# 03 — Run dispatch and claim

**What to build:** Operator dispatches a research run against a case with an explicit
question and bounded scope. A research executor calls `claim_next_run()` and receives the
oldest approved run, along with its question, scope, and rubric version and text (rubric
content itself can be a placeholder — the mechanism is what this ticket delivers).

**Blocked by:** 02 — Case creation

**Status:** ready-for-agent

- [ ] Operator can dispatch a run on a case with a question and scope; the run enters state
      `draft` then `approved`.
- [ ] `claim_next_run()` returns the oldest approved run and moves it to `claimed`.
- [ ] The claimed-run response includes question, scope, and rubric version/text.
- [ ] The backend never pushes to a named executor — claiming is pull-only.
- [ ] Run states `draft`/`approved`/`claimed` are visible to the operator in the browser
      client.
- [ ] The governed operations are tested at the agreed seam.
