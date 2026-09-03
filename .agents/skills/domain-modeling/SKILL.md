---
name: domain-modeling
description: Build and sharpen a project's domain model. Use when discussing codebase terminology, writing or editing a CONTEXT.md, or recording or editing an ADR.
---

# Domain Modeling

Actively build and sharpen the project's domain model as you design. This is the *active* discipline: challenging terms, inventing edge-case scenarios, and writing the glossary and decisions down the moment they crystallise. (Merely *reading* `CONTEXT.md` for vocabulary is not this skill: that's a one-line habit any skill can do. This skill is for when you're changing the model, not just consuming it.)

## Discrepancy Desk preflight

1. Use the canonical project-local skill copy under `.agents/skills/`; supported coding
   clients consume the same adapted skill.
2. Read `VISION.md`, `CONTEXT.md`, both decision registers, and the relevant accepted
   ADR/spec/ticket before proposing model changes.
3. Treat `docs/design/` as non-authoritative Foundation Model v2 workshop/history. It may
   provide scenarios or rejected alternatives but cannot override current authority.
4. Keep one concise root `CONTEXT.md` as the canonical ubiquitous-language glossary. Do
   not create `CONTEXT-MAP.md` or multiple bounded-context glossaries unless the actual
   project later proves that need.
5. Task models propose terminology or ADR candidates. Codex, as Project Steward,
   reconciles authority; CHAZ resolves consequential Product choices.

## Desk modeling rules

- Preserve `Observation → Claim → Decision`; do not collapse source-local evidence, proposition, and human authority.
- Treat File as the scope of investigative attention. Foundation Model `Case` is the same object, not a second noun or truth scope.
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

The Desk already has one accepted root `CONTEXT.md`. Propose only terms that a concrete scenario proves distinct, and update that canonical glossary through Steward reconciliation.

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

Resolved terms should be captured promptly in `CONTEXT.md`. A task model returns the proposed term, definition, avoided synonyms, affected concepts, and concrete scenarios to the Project Steward rather than self-promoting authority. Use [CONTEXT-FORMAT.md](./CONTEXT-FORMAT.md) as a formatting reference.

`CONTEXT.md` should be totally devoid of implementation details. Do not treat `CONTEXT.md` as a spec, a scratch pad, or a repository for implementation decisions. It is a glossary and nothing else.

### Offer ADRs sparingly

Only offer to create an ADR when all three are true:

1. **Hard to reverse**: the cost of changing your mind later is meaningful
2. **Surprising without context**: a future reader will wonder "why did they do it this way?"
3. **The result of a real trade-off**: there were genuine alternatives and you picked one for specific reasons

If any of the three is missing, skip the ADR. Use the format in [ADR-FORMAT.md](./ADR-FORMAT.md).
