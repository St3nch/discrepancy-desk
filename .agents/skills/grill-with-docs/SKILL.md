---
name: grill-with-docs
description: A relentless interview to sharpen a plan or design, which also creates docs (ADR's and glossary) as we go.
disable-model-invocation: true
---

# Grill with Docs — Discrepancy Desk mode

Use the project-local `grilling` and `domain-modeling` skills together to stress-test a
design before it becomes authority.

## Preflight

1. Use the canonical project-local skill copies under `.agents/skills/`.
2. Read `VISION.md`, `CONTEXT.md`, both decision registers, and relevant accepted
   ADRs/specs/tickets.
3. Treat `docs/design/` as non-authoritative Foundation Model v2 workshop/history.
4. Surface conflicts instead of silently choosing the convenient source.
5. Invoke only the project-local `grilling` and `domain-modeling` skills.

## Process

1. Grill the current idea using concrete scenarios and edge cases. Question Product facts;
   do not invent them.
2. Use `domain-modeling` to challenge nouns, boundaries, relationships, and genuine ADR
   candidacy.
3. Distinguish clearly among:
   - current accepted authority;
   - non-authoritative research or workshop material;
   - new proposals from this session.
4. For exploratory CHAZ questions, teach first, evaluate fit and trade-offs second,
   recommend third, and leave the consequential decision to CHAZ.
5. End with a bounded proposal package containing, as relevant:
   - proposed canonical terms and avoided synonyms;
   - proposed decisions and rejected alternatives;
   - proposed deferrals with trigger and cost of forgetting;
   - ADR candidates only when hard to reverse, surprising without context, and based on a
     real trade-off;
   - unresolved Product questions for CHAZ.
6. Stop for Project Steward reconciliation.

## Boundary

Skill output is working input, not authority. Do not autonomously promote proposals into
`VISION.md`, `CONTEXT.md`, decisions, ADRs, specs, tickets, schema, or implementation.
Codex is the Project Steward; another model using this skill does not acquire that role.
