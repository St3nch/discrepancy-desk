# Review — Ticket 12a (refusal invariant and quotation-surface lookup)

**Date:** 2026-08-07
**Reviewers:** Claude (seam checks + steward) and GPT (spec), independently
**Verdict:** Accepted on both axes after two rounds.

A follow-on ticket in the 09a/10a pattern. No product behaviour changed — both items are
executor reliability, and both came from the first live model run rather than from review.

Suite verified by the reviewer each round: 208, then 211 passing.

---

## Origin

Ticket 12's live executor run produced a sharp contrast that neither reviewer had seen:
`QUOTE_MISMATCH` taught the quotation-surface model in one shot and the executor recovered on
the first retry, while `close_run` raised a bare `'proposed_scope'` — a `KeyError` fragment
with no envelope — which taught nothing and was fixed by guessing.

The Desk's design claim is that it teaches its executor through refusals. An unstructured
error escaping the tool layer is therefore not a rough edge; it is the promise broken. F-54
and F-58 patched two call sites. This ticket made it structural.

The second item came from the same run: the executor hand-counted character offsets in
preformatted blocks and reported that it survived because RFC page headers happen to be
exactly 72 columns wide, which gave it a checksum.

---

## Round one — the invariant did not cover the boundary it named

### F-60 / S-01 — The wrapper sat inside the framework, not at the boundary

**Severity:** Blocking. **Closed.**

Decorator order was `@server.tool` outside `@mcp_tool_boundary`, so MCP's `FuncMetadata`
argument validation ran before the wrapper was ever entered. A malformed top-level payload
returned the framework's ordinary `ToolError` rather than the five-field envelope.

The invariant test called `tool.fn` directly — bypassing exactly the layer that fails — so it
could not establish what it claimed. Most of its cases also passed correctly-typed arguments
and provoked domain or database failures rather than the malformed-payload classes the ticket
lists.

**The implementer reported this himself** before either review pass. The seam reviewer then
hedged on it — calling closure conditional on how the framework surfaced those errors — which
was wrong: the ticket says the wrapper catches anything that escapes and the test asserts the
envelope in every case. Neither is conditional. The spec axis read the criterion correctly
and upgraded it to blocking.

### The correction the fix required: three categories, not two

The spec remedy said framework failures should render as non-correctable
`TOOL_INTERNAL_ERROR`. **That would have been wrong**, and correcting it was the substantive
review contribution of this ticket.

A missing required argument or a wrong type is precisely what an executor can and should fix.
Telling it *do not retry with a different payload* would stall a run over a typo — which is
F-54's failure in a new costume: unlearnable feedback on a correctable mistake.

The boundary therefore carries three categories:

| Category | Code | Behaviour |
|---|---|---|
| Domain | original `DeskRefusal` code | Passes through unchanged |
| Framework argument validation | `TOOL_ARGUMENT_INVALID` | **Actionable** — names the parameter and expected type, says fix and retry |
| Unexpected | `TOOL_INTERNAL_ERROR` | Non-correctable, no internals, logged server-side |

The ticket and `codingstandards.md` were reconciled to the three-category contract, so the
documents and the code agree — the S-07/S-08 lesson from ticket 11 applied before acceptance
rather than after.

---

## What held

**The two-category docstring named F-17 one level up.** *Dressing every failure as an
actionable refusal hides the bug and invites a loop.* That reasoning was in the ticket;
carrying it into the module docstring means the next person cannot undo it by accident.

**`TOOL_INTERNAL_ERROR`'s remedy text is genuinely non-actionable**, which is the hard part.
Most attempts at this write something helpful-sounding and re-create the loop they were meant
to prevent.

**`raise ToolError(message) from None`** suppresses chaining so the original traceback cannot
ride along into the message. Small and deliberate.

**Discrimination is on `ToolError.__cause__`, not string matching** — a rendered envelope
re-raises clean with `Tool.run`'s prefix stripped, a pydantic `ValidationError` becomes
correctable, everything else is non-correctable.

**Schema validation still runs inside `Tool.run`.** The obvious implementation — wrapping
registration and accepting loose types — would have cost the schemas that teach parameter
names in the first place. Intercepting on the way out keeps them intact.

**`Unknown tool:` passes through unrebranded.** Not the Desk's failure to describe, and
putting it in a Desk envelope would claim authorship of a framework concern. Judgement rather
than mechanism.

**`parse_quote_binding` was unprompted** — same F-54/F-58 class, keeping missing quote-binding
keys as domain refusals rather than letting them fall through to internal errors. Fourth
consecutive ticket with a boundary check nobody specified.

**`find_quote` with `refresh_lease=False`.** A read-only lookup that silently extended the
lease would let an executor hold a run alive indefinitely by polling a read — F-25's
territory. Built right and locked with a test.

**Structured misses are success payloads, not refusals.** Not finding a quote is an answer,
not a failure the caller should correct. `codingstandards`' empty-result-versus-refusal
distinction applied to a new operation. `multiple_in_element` went slightly beyond the
ticket's wording and is correct — same non-uniqueness failure, and its own reason with a match
list is more useful than collapsing it.

---

## F-61 — Monkey-patching a private attribute

**Severity:** Low. **Recorded, no action.**

`install_tool_dispatch_envelope` reaches into `server._tool_manager` and replaces the bound
`call_tool`. A library upgrade renaming that attribute or changing the signature breaks this
silently — the failure mode is the invariant quietly not installing, not an import error.

Worth one assertion at install time that the attribute exists and is callable, so an upgrade
fails loudly at startup rather than leaving the envelope uninstalled. Same argument that made
MCP tool registration checked at startup. The tests would catch it now that they go through
`call_tool`, which is why this is low rather than medium.

---

## Open, not blocking

**The live-model wrong-type smoke test has not run.** The implementer flagged it plainly:
worth doing before treating the ticket as production-closed. Both axes agree it is not an
acceptance criterion — it needs a live executor session, which is the operator's side of the
desk.

It should happen before ticket 13 rather than drifting, because what it tests is whether a
real model reads `TOOL_ARGUMENT_INVALID` and corrects. That is the claim the ticket rests on,
and the automated suite can only show the envelope is well-formed, not that it teaches.

---

## Process note

**The implementer flagged the blocker in his own report, and the seam reviewer softened it.**
The finding was raised as medium with closure described as conditional; the spec axis read the
acceptance criteria literally and was right to. Worth recording because the failure mode is
specific: a reviewer who has already read the implementer's honest self-report is primed to
treat it as disclosed-and-therefore-acceptable rather than as found-and-therefore-blocking.
