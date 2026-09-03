---
name: to-tickets
description: Break a plan, spec, or the current conversation into a proposed set of tracer-bullet tickets, each declaring its blocking edges, for Project Steward reconciliation.
disable-model-invocation: true
---

# To Tickets

Break a plan, spec, or conversation into a set of **tickets**: tracer-bullet vertical slices, each declaring the tickets that **block** it.

## Discrepancy Desk mode

Desk mode supersedes upstream issue-tracker publication behavior.

- Use the shared canonical project skill under `.agents/skills/`; every supported coding client consumes the same adapted method.
- Work from an accepted spec, accepted design boundary, or explicit Steward request. Generated ticket text is a proposal until the Project Steward reconciles and accepts it.
- Prefer tracer-bullet vertical slices with observable behavior and explicit blocking edges.
- Keep each implementation ticket small enough for one fresh Writer context and one reviewable implementation commit.
- Do not turn architecture cleanup, speculative future capability, or adjacent discoveries into hidden scope.
- **Do not publish tickets to GitHub/GitLab or apply triage labels by default.** Desk tickets are governed repository artifacts unless the Product Owner and Steward later change that policy explicitly.
- The Steward controls durable ticket identifiers, location, acceptance, and exact implementation start commit.
- A generated ticket never authorizes implementation, network/provider/spend actions, credentials, production mutation, or push.

Desk flow:

```text
accepted spec/design → tracer-bullet proposal → Steward reconciliation → accepted repo ticket → adversarial pre-implementation review
```

In Desk mode, ignore the upstream requirement for issue-tracker or triage configuration. The remaining upstream publication instructions are reference behavior for projects that use such a tracker.

## Process

### 1. Gather context

Work from whatever is already in the conversation context. If the user passes a reference (a spec path, an issue number or URL) as an argument, fetch it and read its full body and comments.

### 2. Explore the codebase (optional)

If you have not already explored the codebase, do so to understand the current state of the code. Ticket titles and descriptions should use the project's domain glossary vocabulary, and respect ADRs in the area you're touching.

Look for opportunities to prefactor the code to make the implementation easier. "Make the change easy, then make the easy change."

### 3. Draft vertical slices

Break the work into **tracer bullet** tickets.

<vertical-slice-rules>

- Each slice cuts a narrow but COMPLETE path through every layer (schema, API, UI, tests): vertical, NOT a horizontal slice of one layer
- A completed slice is demoable or verifiable on its own
- Each slice is sized to fit in a single fresh context window
- Any prefactoring should be done first

</vertical-slice-rules>

Give each ticket its **blocking edges**: the other tickets that must complete before it can start. A ticket with no blockers can start immediately.

**Wide refactors are the exception to vertical slicing.** A **wide refactor** is one mechanical change (rename a column, retype a shared symbol) whose **blast radius** fans across the whole codebase, so a single edit breaks thousands of call sites at once and no vertical slice can land green. Don't force it into a tracer bullet; sequence it as **expand–contract**. First expand: add the new form beside the old so nothing breaks. Then migrate the call sites over in batches sized by blast radius (per package, per directory), each batch its own ticket blocked by the expand, keeping CI green batch to batch because the old form still exists. Finally contract: delete the old form once no caller remains, in a ticket blocked by every migrate batch. When even the batches can't stay green alone, keep the sequence but let them share an integration branch that all block a final integrate-and-verify ticket; green is promised only there.

### 4. Quiz the user

Present the proposed breakdown as a numbered list. For each ticket, show:

- **Title**: short descriptive name
- **Blocked by**: which other tickets (if any) must complete first
- **What it delivers**: the end-to-end behaviour this ticket makes work

Ask the user:

- Does the granularity feel right? (too coarse / too fine)
- Are the blocking edges correct: does each ticket only depend on tickets that genuinely gate it?
- Should any tickets be merged or split further?

Iterate until the user approves the breakdown.

### 5. Return the ticket proposal to the Project Steward

In Desk mode, stop after the user approves the breakdown and return the proposed ticket set to the Project Steward for reconciliation. Do not publish to GitHub/GitLab, apply triage labels, create `.scratch/` issue state, or assign an accepted status unless current Desk authority explicitly instructs that exact action.

The Steward owns durable ticket identifiers, repository location, accepted status, blocking edges, and the exact implementation start commit. Until that reconciliation happens, every generated ticket remains a proposal.

Work the **frontier** conceptually: any proposed ticket whose blockers are all accepted and completed could start next. This does not authorize implementation.

<local-ticket-template>

# <NN>: <Ticket title>

**What to build:** the end-to-end behaviour this ticket makes work, from the user's perspective, not a layer-by-layer implementation list.

**Blocked by:** the numbers/titles of the tickets that gate this one, or "None (can start immediately)".

**Status:** proposed

- [ ] Acceptance criterion 1
- [ ] Acceptance criterion 2

</local-ticket-template>

Avoid specific file paths or code snippets: they go stale fast. Exception: if a prototype produced a snippet that encodes a decision more precisely than prose can (state machine, reducer, schema, type shape), inline it and note briefly that it came from a prototype. Trim to the decision-rich parts, not a working demo, just the important bits.
