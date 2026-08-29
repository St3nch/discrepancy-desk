---
name: grill-with-docs
description: A relentless interview to sharpen a plan or design, which also creates docs (ADR's and glossary) as we go.
disable-model-invocation: true
---

# Grill with Docs — Discrepancy Desk mode

Use the project-local `grilling` and `domain-modeling` skills together to stress-test a design before it becomes authority.

## Preflight

1. Use the canonical project-local skill copy under `.agents/skills/`; Grok Build and Claude Code are consumers of the same project method.
2. Read the current Desk authority relevant to the subject. During Foundation Model v2, `docs/design/` is explicitly workshop material, not authority.
3. Once `VISION.md`, `CONTEXT.md`, `AGENTS.md`, accepted ADRs/specs, and tickets exist, respect that hierarchy and surface conflicts rather than silently overriding it.
4. Invoke the project-local `grilling` and `domain-modeling` skills only.

## Process

1. Grill the current design using concrete scenarios and edge cases. Question Product facts; do not invent them.
2. Use `domain-modeling` to challenge nouns, boundaries, relationships, and ADR candidacy.
3. Distinguish clearly among:
   - current accepted authority;
   - current non-authoritative design material;
   - new proposals from this session.
4. End with a bounded proposal package containing, as relevant:
   - proposed canonical terms and avoided synonyms;
   - proposed decisions and rejected alternatives;
   - proposed deferrals with trigger/cost of forgetting;
   - ADR candidates only when hard to reverse, surprising without context, and based on a real trade-off;
   - unresolved Product questions for CHAZ.
5. Stop for Project Steward reconciliation.

## Boundary

Skill output is working input, not authority. Do not autonomously promote proposals into `VISION.md`, `CONTEXT.md`, ADRs, specs, tickets, schema, or implementation.

During Foundation Model v2, the first calibration target is reversible identity: improve the model without creating noun sprawl or a second truth path.
