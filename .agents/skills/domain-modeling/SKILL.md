---
name: domain-modeling
description: Build and sharpen a project's domain model. Use when discussing codebase terminology, writing or editing a CONTEXT.md, or recording or editing an ADR.
---

# Domain Modeling

Actively build and sharpen the project's domain model as you design. This is the *active* discipline: challenging terms, inventing edge-case scenarios, and writing the glossary and decisions down the moment they crystallise. (Merely *reading* `CONTEXT.md` for vocabulary is not this skill: that's a one-line habit any skill can do. This skill is for when you're changing the model, not just consuming it.)

## Discrepancy Desk preflight

1. Use the canonical project-local skill copy under `.agents/skills/`; Grok Build and Claude Code consume the same adapted skill.
2. During Foundation Model v2, read `docs/design/FOUNDATION-MODEL-V2.md` and the relevant `docs/design/CONTRACT-*.md` files before proposing model changes.
3. `docs/design/` is non-authoritative workshop material. Do not silently treat a committed design draft as settled Product authority.
4. Once accepted, the Desk expects one concise root `CONTEXT.md` as the canonical ubiquitous-language glossary. Do not create `CONTEXT-MAP.md` or multiple bounded-context glossaries unless the actual project later proves that need.
5. The Project Steward reconciles accepted vocabulary and ADRs into authority. During the foundation phase this skill proposes; it does not self-promote proposals.

## Desk modeling rules

- Preserve `Observation → Claim → Decision`; do not collapse source-local evidence, proposition, and human authority.
- Treat Case as scope of investigative attention unless a worked example proves Case-local truth is necessary.
- Prefer one candidate-intelligence envelope over noun proliferation.
- Identity resolution must remain reversible and must not rewrite historical evidence provenance.
- Relationship is currently a Claim shape/projection, not a second truth system, unless evidence forces a different model.
- Preserve temporal precision and disagreement rather than normalizing them into false certainty.
- A brainstorm phrase does not become a domain noun until a concrete scenario proves the concept is distinct.

## File structure

Most repos have a single context:

```
/
├── CONTEXT.md
├── docs/
│   └── adr/
│       ├── 0001-event-sourced-orders.md
│       └── 0002-postgres-for-write-model.md
└── src/
```

If a `CONTEXT-MAP.md` exists at the root, the repo has multiple contexts. The map points to where each one lives:

```
/
├── CONTEXT-MAP.md
├── docs/
│   └── adr/                          ← system-wide decisions
├── src/
│   ├── ordering/
│   │   ├── CONTEXT.md
│   │   └── docs/adr/                 ← context-specific decisions
│   └── billing/
│       ├── CONTEXT.md
│       └── docs/adr/
```

Create files lazily: only when you have something to write. If no `CONTEXT.md` exists, create one when the first term is resolved. If no `docs/adr/` exists, create it when the first ADR is needed.

For the Desk foundation phase, do **not** create `CONTEXT.md` merely because upstream normally would. Propose reconciled entries first; the Steward will create or promote authority when Foundation Model v2 is ready.

## During the session

### Challenge against the glossary

When the user uses a term that conflicts with the existing language in `CONTEXT.md`, call it out immediately. "Your glossary defines 'cancellation' as X, but you seem to mean Y. Which is it?"

### Sharpen fuzzy language

When the user uses vague or overloaded terms, propose a precise canonical term. "You're saying 'account': do you mean the Customer or the User? Those are different things."

### Discuss concrete scenarios

When domain relationships are being discussed, stress-test them with specific scenarios. Invent scenarios that probe edge cases and force the user to be precise about the boundaries between concepts.

### Cross-reference with code

When the user states how something works, check whether the code agrees. If you find a contradiction, surface it: "Your code cancels entire Orders, but you just said partial cancellation is possible. Which is right?"

### Reconcile CONTEXT.md deliberately

In ordinary mature-project use, resolved terms should be captured promptly in `CONTEXT.md`. During Foundation Model v2, return the proposed term, definition, avoided synonyms, affected existing concepts, and concrete scenarios to the Project Steward instead of writing authority directly. Use [CONTEXT-FORMAT.md](./CONTEXT-FORMAT.md) as a formatting reference when promotion is authorized.

`CONTEXT.md` should be totally devoid of implementation details. Do not treat `CONTEXT.md` as a spec, a scratch pad, or a repository for implementation decisions. It is a glossary and nothing else.

### Offer ADRs sparingly

Only offer to create an ADR when all three are true:

1. **Hard to reverse**: the cost of changing your mind later is meaningful
2. **Surprising without context**: a future reader will wonder "why did they do it this way?"
3. **The result of a real trade-off**: there were genuine alternatives and you picked one for specific reasons

If any of the three is missing, skip the ADR. Use the format in [ADR-FORMAT.md](./ADR-FORMAT.md).
