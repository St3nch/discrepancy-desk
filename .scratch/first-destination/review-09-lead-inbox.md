# Review — Ticket 09 (lead inbox)

**Date:** 2026-08-05
**Reviewers:** Claude (seam checks + steward) and GPT (spec), independently
**Verdict:** Accepted after F-33 through F-36 were fixed and two acceptance criteria were
narrowed. Both axes accepted.

Three review rounds. The first found two blockers; the second verified the fixes; the third
resolved a disagreement about the auth-wall criterion that neither reviewer could settle
alone. Code is `ed1f134`, local, unpushed at the time of writing.

---

## Standing checks (post-fix)

| Check | Result |
|---|---|
| Vocabulary reconciliation | **Clean.** `leads.material_status` and `leads.inbox_status` both carry CHECKs and were added as tuples to the existing `tests/test_check_enums.py` table — no third per-table pattern invented |
| Fail-open inventory | **F-33** — the significant one |
| Destructive-write inventory | **Clean.** `attach_lead` writes one column on `captures` and three on `leads`, all in the input model's intent |
| Dead-capability inventory | **F-36.** `get_lead` had no call site; removed |
| Write-once inventory | N/A — no append-only chains added |
| Projection completeness | **Clean.** Every governed lead decision reads back through `LeadRecord`, which the client views render |

---

## What held

**`retain_capture_from_bytes` is a genuine shared path, not a copy.** This was the thing the
ticket 08 handoff warned about most loudly and it landed correctly — store, hash,
`document_versions`, `elements`, full-span `regions`, projection banner, one function. Both
doors produce identical capture records; ownership columns differ and nothing else does.

**`read_capture`'s `CAPTURE_NOT_ON_CASE` branch was not asked for.** Nothing required
thinking about an executor pointing `read_capture` at unattached inbox material. It refuses,
with a distinct code, and the case-attached branch reuses `read_case_context`'s token
authority pattern rather than inventing a second one.

**`propose_claim` scopes lead captures on `case_id`, not `run_id`** — the right axis, so an
attached lead capture becomes citable by construction and an unattached one is refused with
a message naming what the operator must do.

**`CAPTURE_AUTH_WALLED` is a distinct code that stays a hard refusal on the run path** while
being a product state on the lead path. Separating the enforcement refusal from the product
state was the easy thing to get wrong here and it was got right.

**The `has_run ^ has_token` gate (round two) is better than what was asked for.** The fix
requested two paths; what landed is one function refusing the half-populated middle
explicitly. An empty token with a real `run_id` fails closed with `LEAD_CLAIM_INCOMPLETE`
rather than being coerced into the operator path. That is F-06's lesson — one field, two
meanings, one path coercing where another refuses — applied unprompted.

---

## Findings

### F-33 — `add_lead` on MCP required no run authority and consumed no budget

**Severity:** Blocking. **Closed.**

`add_lead_tool(url, note)` — no `run_id`, no `claim_token`, no lease check, no budget check.
The only MCP tool requiring no claim at all. An executor with an exhausted budget, or one
that never claimed a run, could call it in a loop and write unbounded captures to the Vault.

`capture_url` gates on claimed status, unexpired lease, matching token, and budget before a
single byte is stored. This door had none of it. VISION states the rationale directly — *the
executor cannot overspend because it is not the one spending* — and this handed the spending
back.

The F-12 class one level down: F-12 was the executor walking around the *transport* boundary
by fetching what it could not call; this was walking around the *budget* boundary by
capturing through a door that does not count. SSRF still held, so it was an unmetered Vault
write channel rather than an exfiltration hole.

Also worth recording: D18's justification for putting `add_lead` on MCP is the executor
**mid-run** encountering out-of-scope material. "Mid-run" is load-bearing in that argument
and was enforced nowhere.

**Resolution:** the MCP tool takes `run_id: int` and `claim_token: str` as required
parameters with no defaults, so the tool schema refuses omission — the gate is at the
transport, not only in the service, which matters because optional parameters would have let
a caller drop through to the operator path. The API variant still takes neither. Lead drops
are **not** charged against `capture_budget`; D18's whole point is that out-of-scope material
must not burn the run's allowance. A per-run drop cap is the right eventual shape and is left
as a `TODO` naming this finding, because the number is the operator's to set.

### F-34 — `close_run` crashed on attached lead captures, and excluded them by design

**Severity:** Blocking. **Closed.**

`_mark_reported_examined` tested `int(row.run_id) != run_id`. `captures.run_id` became
nullable in `0011`, so an attached lead capture — `run_id` NULL, `case_id` set — raised
`TypeError`, which is not a `DeskRefusal` and leaked through the transport as a raw error.

Fixing the crash was not enough. `propose_claim` scopes on `case_id` and `read_capture` was
taught about case-owned captures explicitly; `close_run` still asked `run_id`. So an attached
lead capture was **citable but not examinable** — a run could bind a claim to it, but if the
run read it and found nothing worth claiming, it could not say so. The capture then sat
`unexamined` permanently, indistinguishable from material nobody looked at.

That is F-32's distinction failing in the opposite direction. *"6 of 74 eligible"* means
nothing if 68 were marked examined by a `WHERE` clause, and it means nothing either if
genuinely-examined material cannot be marked.

**This is the project's recurring failure shape.** Three paths needed to understand
case-owned captures. Two were taught. Same as `get_case` unscoped while `list_cases` was
scoped; same as one-directional vocabulary reconciliation.

**Resolution:** `_mark_reported_examined` takes `case_id`, computes `owned_by_run` and
`owned_by_case` with explicit null guards on both, and refuses only when neither holds. The
`UPDATE` dropped its `run_id` filter and gained `WHERE status = 'unexamined'` with a
`rowcount != 1` check — the removed guard was replaced by a stronger one rather than deleted.
`CAPTURE_WRONG_RUN` now names both the run and case the capture actually belongs to.

### F-35 — An unsupported content type loses the lead entirely

**Severity:** Medium. **Open — deferred to its own ticket.**

`assert_content_type_supported` runs inside `retain_capture_from_bytes`, outside `add_lead`'s
fetch try block, so dropping a PDF or an audio URL refuses with no lead row at all and the
URL is gone.

VISION's own examples of what the inbox is for: *a podcast encountered by chance, a video
surfaced by a recommendation engine.* D10's justification for capturing on drop is that the
material most worth having is the material most likely to disappear. Today the inbox refuses
precisely that material and parks a login wall instead.

The asymmetry is the tell: two distinct "cannot capture this" outcomes, and only one
preserves the URL.

**Not folded into ticket 09 after the fact.** The implementer sized it at review as small —
catch the refusal, insert a lead with `capture_id` NULL, the pattern identity-only already
proves; `retain_capture_from_bytes` needs no URL-only mode because unsupported types raise
before any Vault write. It is new code and belongs in its own ticket or an explicitly
approved rider. Recorded in D19's consequences and in `CONTEXT.md` as open, not intended.

### F-36 — Three small ones

**Severity:** Low. **Closed.**

- `get_lead` / `GET /api/leads/{id}` had no client call site; `list_leads` returns the same
  projection. Removed across service, route, wiring, and models — the better of the two
  options, and F-03's lesson about registries that look authoritative and are not.
- `list_leads` used `"all"` as a sentinel outside the `inbox_status` enum, and an
  unrecognised filter returned empty rather than refusing — F-06's shape. Now a named
  constant, with `LEAD_INBOX_STATUS_INVALID` for unknown values.
- `del attached` in `promote_lead` — dead code silencing a linter, F-05 again. Removed.

Also recorded, no defect: `promote_lead` composes `create_case` and `attach_lead` on the
shared connection, so it is atomic in one transaction. `codingstandards.md` says multi-step
atomicity should be one service function owning the unit of work, not composed calls sharing
a connection; this works only because those functions take a `Connection` rather than opening
their own scope. Now stated in the docstring so the pattern is not copied somewhere it
breaks.

---

## Spec axis (GPT) — S-01 through S-05

**S-03 (`close_run` ownership) and S-04 (MCP `add_lead` authority)** closed against F-34 and
F-33. Both reviewers reached these independently on different rounds.

**S-05** — unsupported types — converged with F-35. Non-blocking on both axes, deferred.

**S-01 — auth walls. Resolved by narrowing the criterion, not by code.** GPT held through
three rounds that documenting the soft-wall gap in a comment and `CONTEXT.md` could not
narrow an already-binding acceptance criterion. **He was right, and this reviewer was wrong
to accept while owing document edits** — an acceptance conditional on work that has not
happened is not an acceptance. The substantive disagreement (whether to build wall detection)
resolved against detection once the implementer confirmed what the fetch path retains and
discards. See D19 for the full reasoning and both rejected alternatives.

**S-02 — summary generation. Resolved by narrowing.** `summarise_lead` stores
operator-supplied text; the criterion said a summary "may be generated." Both reviewers
agreed generation would make the backend an LLM client, which VISION §17 parks deliberately,
and that a ticket should not force that choice. Criterion narrowed to an optional
operator-authored field, generation deferred. The narrowing was made by the steward, not the
implementer — acceptance criteria should not be edited by the party being reviewed against
them.

---

## What turned the S-01 argument

The implementer was asked what soft walls actually look like coming through the capture path
— an observation question, deliberately not a recommendation question, since he was the party
being reviewed against the criterion.

**He opened by saying he had not fetched a real wall.** Ticket 09's tests inject fake HTML or
raise `CAPTURE_AUTH_WALLED` by hand. Everything after that was framed as what the code keeps
and discards rather than as a field report.

That is worth recording as behaviour, not just as an input. The easy answer was a confident
description of how paywalls generally work, which would have read as observation and been
unfalsifiable from outside.

The substance decided the question: `safe_http_get` returns body bytes and Content-Type only
— status, headers, hop count, intermediate `Location`s, and the final URL are all discarded,
so a detector could not be built on what the Vault retains. And `material_status` does not
reach `propose_claim`, `close_run`, or `attach_lead`, so an operator mark would be
decorative unless enforcement were spread across four sites — the D17 shape.

---

## Process note

The routing held this time. Grok reported to both reviewers, each responded independently,
and findings were merged into one prompt afterwards — the sequence that collapsed during
tickets 06 and 07. Neither reviewer found the other's blocking findings, which is the
argument for the split stated as evidence rather than as principle.

The third round introduced a question to the implementer that was neither review nor
instruction: what did you observe. Worth repeating where a decision turns on facts about the
code that only the person who wrote it has.
