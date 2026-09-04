---
name: future-capability-reconciliation
description: Resolve a material future Product idea from CHAZ, an LLM, review, research, implementation, or operator use without losing it to chat or silently turning it into backlog, architecture, or implementation authority.
---

# Future capability reconciliation — Discrepancy Desk mode

Use this working method when a material idea has reached the point where “later,” “maybe,”
or “remember this” would be an unsafe ending.

Ideas may originate from CHAZ, the Steward, Writers, reviewers, LLM suggestions, external
research, incidents, operator friction, or real File work. Origin is provenance, not
authority.

## 1. Read before classifying

Read the smallest relevant authority in normal Desk order:

1. `VISION.md`
2. `CONTEXT.md`
3. `decisions/decisions.md`
4. `decisions/deferred.md`
5. relevant accepted ticket/ADR/spec when the idea touches current work

Do not use chat memory, reviewer confidence, or a research report as a substitute for live
authority.

## 2. Teach, evaluate, recommend

For the candidate idea:

1. explain what the capability/question actually means;
2. evaluate Product fit, redundancy, authority impact, evidence, cost, risk, and whether
   existing capability already solves the real job;
3. distinguish Product direction from proposed implementation/provider shape;
4. recommend one lifecycle disposition;
5. obtain CHAZ resolution when the choice is consequential.

Do not mutate Product authority merely because a model recommends something.

## 3. Choose exactly one disposition

- **Exploring** — active understanding is incomplete; normally keep transient until a
  material durable question exists.
- **Rejected** — does not belong; record in `decisions/decisions.md` only when forgetting
  the rejection would cause repeated drift or re-litigation.
- **Research Required** — important unresolved question; bounded research may be separately
  authorized, but no direction is assumed.
- **Accepted Direction** — belongs in the Product if/when stated conditions are met; not
  backlog, priority, architecture, provider selection, or implementation authority.
- **Promoted** — a trigger/revisit was reviewed and CHAZ made a fresh decision that the item
  may enter the normal authority/spec/ticket chain.
- **Superseded** — later evidence/direction replaces the prior disposition.

## 4. Place durable future items

For **Accepted Direction** or durable **Research Required**, update the existing canonical
`decisions/deferred.md` entry or add the smallest new entry. Do not create a second register.

Record:

- Disposition
- primary Product Pillar
- Clock: `CURRENT`, `NEXT`, `TRIGGERED`, or `HORIZON`
- Direction or exact unresolved Question
- Why it matters
- Why not now
- observable Review trigger
- deliberate Revisit point
- Evidence basis and useful origin
- Cost of forgetting
- explicit **Not authorized** boundary

The review trigger says when a fresh review is earned. It never auto-promotes work; only a
fresh CHAZ Product decision may promote an item into the normal project chain.

## 5. Preserve implementation uncertainty

Strip premature implementation choices from the durable direction unless CHAZ separately
settled them. Model/provider/library/database/UI names may be preserved as research examples
or optional experiments, not silently promoted into architecture.

Examples:

- preserve “model-assisted exact evidence noticing against frozen Surfaces” rather than
  “build Anthropic Citations integration”;
- preserve the question of provider-restricted evidence retention rather than inventing a
  tombstone schema before a real source requires it.

## 6. LLM/reviewer report reconciliation

A large research/review report may contain dozens of suggestions. Do not bulk-create
deferred entries or tickets.

For each material candidate only:

1. reconcile against live authority and implementation evidence;
2. remove duplicates and already-settled ideas;
3. separate external evidence from model inference;
4. recommend a disposition;
5. obtain CHAZ resolution where consequential;
6. record only the resulting durable Product judgment/question.

Token count, model cost, reviewer count, or confidence does not increase authority.

## 7. End state

Finish with one of these outcomes:

- no durable record because exploration remains genuinely transient;
- settled rejection recorded where consequential;
- Research Required entry recorded;
- Accepted Direction entry recorded;
- promoted item handed into the normal project chain;
- prior item superseded in the canonical authority.

Never finish a material resolved idea with only “we will remember this later.”

This skill is working method, not Product authority. `AGENTS.md`, the decision registers,
accepted specs/ADRs/tickets, Steward reconciliation, and CHAZ authority continue to govern.
