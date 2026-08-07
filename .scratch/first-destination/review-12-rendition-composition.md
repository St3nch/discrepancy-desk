# Review — Ticket 12 (rendition composition)

**Date:** 2026-08-07
**Reviewers:** Claude (seam checks + steward) and GPT (spec), independently
**Verdict:** Accepted on both axes.

The first ticket that produces something a human reads, and the first ticket where a live
model drove the system end to end. The second of those turned out to matter more than the
first.

Suite verified by the reviewer at each round rather than taken from the report: 184, then
192 passing.

---

## Standing checks

| Check | Result |
|---|---|
| Vocabulary reconciliation | **Clean**, with one note — see F-59 below |
| Fail-open inventory | **Clean.** `propose_rendition` requires `run_id` and `claim_token` with no defaults, validated before any read |
| Destructive-write inventory | **Clean.** Renditions insert; nothing mutates |
| Dead-capability inventory | **Clean** after F-53 |
| Write-once inventory | **Clean.** Drafts persist; approval is ticket 13 |
| Projection completeness | **Clean** after F-53 — the run list now shows budget used against total |

---

## What held

**Run authority on `propose_rendition` was right on the first pass.** `run_id` and
`claim_token` required with no defaults, `validate_and_refresh_claim` before anything else.
F-33 was the obvious repeat and it did not happen.

**`ANGLE_WRONG_CASE` was not asked for.** Nothing in the ticket said to check that the angle
belongs to the run's case. A token for a run on case A composing against an angle on case B
is refused with both case ids named. Third consecutive ticket where a boundary check nobody
specified appeared anyway.

**`CLAIM_UNCONFIRMED` and `CLAIM_NOT_ON_ANGLE` are distinct refusals.** Different operator
actions, and one code for both would have made the executor guess.

**`ANGLE_NOT_CHOSEN`** closes the gap where a draft angle could be composed against, which
would have made choosing decorative.

---

## Findings

### F-51 — Client paths unverified against the router

**Severity:** Medium. **Closed.**

Nothing asserted that the paths `client/src/api.ts` calls resolve on the router. Ticket 10a
closed `wiring.py` ↔ router bidirectionally; this was the next leg.

The root cause of the operator's `JSON.parse: unexpected character at line 1` turned out not
to be a missing path at all — `bootstrap-mcp` held port 8000, Vite proxied into a plain-text
404, and the client choked on HTML. The implementer diagnosed it honestly rather than
inventing a bug, added the guard anyway so real drift cannot hide, and made the client error
name that failure mode. Correct on all three counts.

### F-52 — The readable threads were hand-composed

**Severity:** Acceptance question, not a code defect. **Recorded, not closed.**

The ticket said *done means a thread the operator reads*. Two threads exist and are readable
in the browser, and their prose was written by the implementer by hand through the service
seam. Reading them shows the composition path works. It shows nothing about whether an
executor composing under a rubric produces anything worth publishing.

The implementer reported this against himself before either reviewer raised it — *"say that
plainly rather than claim the loop is closed."*

**Partly answered by the live run** described below: a real model drove the research loop end
to end. Composition itself remains un-model-driven. Both axes agree ticket 16 owns real
composition quality, since that is where voice rules become generation constraints tuned
against output.

### F-53 — The operator could not set the capture budget

**Severity:** Medium. **Closed.**

The dispatch form posted `case_id`, `question`, `scope`, and `coverage_dimension`. The
backend defaulted to 20 and the operator never saw it. D8 puts budget enforcement in the
backend precisely so the executor cannot overspend — but the person doing the spending could
not set the amount.

F-44's shape exactly: the service supported it, the form did not expose it, and raw API was
the only path. Closed with the field on the form, default prefilled, minimum 1, and
`budget used/total` in the run list — the projection half nobody asked for.

### F-54 — `close_run` leaked a bare string instead of a refusal

**Severity:** Blocking. **Closed.** **Found by a live executor, not by either reviewer.**

The MCP adapter raised a bare `'proposed_scope'` — a `KeyError` fragment with none of the
five-field refusal envelope — because the tool description said `scope` and the
implementation wanted `proposed_scope`. The executor guessed the right key and recovered. A
weaker one stalls at the last call of every run, after all the work is done.

Two artifacts describing one contract with nothing checking they agreed. **Third instance of
that pattern in this project**, after F-51 and F-59 below.

The fix is better than what was asked for: missing fields accumulate into one refusal naming
all of them rather than failing on the first, the canonical key wins when both are present,
and the remedy text says *empty string is different from missing* — the distinction that
produced the leak.

### F-58 — Same class on `propose_rendition`

**Severity:** Medium. **Closed.** Found by the implementer while fixing F-54. Free `.get()`
and bare `int()` on executor-supplied dicts would have leaked `AttributeError` and
`ValueError` the same way, and the description omitted `body` and `claim_ids`. Finding the
class rather than the instance is the thing worth doing.

### F-59 — `DEFAULT_CAPTURE_BUDGET` is duplicated across the seam

**Severity:** Low. **Recorded, no action.**

The constant now exists in `runs.py` and `api.ts`, with a comment in each saying it matches
the other. A comment is the only reconciliation. Drift means the form prefills a number the
backend overrides rather than anything breaking, so the cost is low — but it is the same
shape as F-51 and F-54, and this is the third time it has appeared.

---

## Two questions carried from ticket 11, both closed on evidence

**Shelf scope — case-scoped is fine.** Composition already enforces angle-scoped citation, so
the shelf is a shared quote pool rather than a second eligibility gate. Decided on evidence
from a real rendition, as the ticket required, and recorded in `CONTEXT.md`.

**Whole-element locators did not hurt.** The unit body is free text; `e/{n}` is correct when
the element is the quotation. The stated trigger for reopening — composition output actually
worse for it — did not fire. Region form remains supported and not required.

Both were declined twice at review as ceremony and closed here on evidence rather than
preference. That is the deferral shape working: a condition, not a maybe.

---

## The live executor run

The first time a real model drove this system. Run #4 on the seeded case, official-foundation
dimension, two captures of a budget of twenty, three claims, two open questions.

**What the architecture got right, observed rather than hoped for:**

**It suspended judgement instead of inventing an answer.** One open question — the pre-1999
origination date — was flagged as needing a scope ruling from the operator before anyone
researches it. VISION §9's suspend-and-ask is built for exactly that and had never faced a
model.

**It declined to inflate a classification.** Two independent primary documents assert the
same rationale; it marked each claim `single_source` because each claim is about what one
document says, then said explicitly that it lacked vocabulary for cross-document
corroboration and left the judgement to the operator. Correct under D4, and it surfaced
F-57.

**It recovered from a refusal on the first retry.** `QUOTE_MISMATCH` was described as the
best refusal text in the system — what happened, what was preserved, how to fix it. The
refusal doctrine working against a real model rather than a test.

**It reported its own uncertainty**, recording in low-confidence areas that its
classifications were pattern-matched rather than rubric-driven.

**What it exposed:**

- **F-55** — the `e/{n}/r/{start}-{end}` convention exists only inside refusal text. A bare
  `e/n` means the quotation surface is the *entire element*, learnable only by failing once.
  Offsets against preformatted blocks were hand-counted; the executor noted it got lucky that
  RFC headers are 72 columns wide. **→ ticket 16 / capture UX.**
- **F-56** — the classification vocabulary is invisible to the executor. Values were inferred
  by pattern-matching the case's existing confirmed claims. On a fresh case it would have
  probed blind against fail-closed validation. **→ ticket 16 / D9.**
- **F-57** — there is no vocabulary for the human judgement that two independent documents
  corroborate each other. VISION §12 reserves that judgement to the operator and gives it
  nowhere to land. **→ design before Vela**, where nine sources on a contested topic will hit
  it constantly. Both axes agree: do not invent it under ticket 12.

It also said it never felt the absence of a human-only tool — *"everything I couldn't do was
correctly something I shouldn't do."* That is the transport boundary reported from the
outside.

---

## Process notes

**The implementer wrote both review files in one round.** The steward's instruction — "send
this report to Grok and GPT both" — was ambiguous and was reasonably read as an instruction to
produce both passes. The steward's first correction landed on the implementer rather than on
the wording, and was itself corrected. The files were relabelled as implementer notes and the
spec pass ran independently afterwards.

Worth recording because the failure was in the routing instruction, not in anyone's work, and
because the substance of those notes — particularly the defect-class analysis behind F-51,
F-54, and F-58 — was good enough to carry into this file.

**A live model found a blocker neither reviewer did.** F-54 sat in the last call of every run
and both axes read past it. Running the system is a third axis, and it is the one that has
not existed until now.
