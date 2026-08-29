# The Discrepancy Desk — Foundation Model v2

**Status:** NON-AUTHORITATIVE DESIGN DRAFT

**Purpose:** Reduce the foundation dossier and independent reviews into a small, testable grammar before `VISION.md`, `CONTEXT.md`, ADRs, PostgreSQL schema, or `0001_initial`.

> **The Record preserves. Models notice. The human decides.**

> **Strict on write. Powerful on read.**

This file is workshop material. It does not become authority merely by being committed.

---

# 1. Core planes

## Evidence

```text
Capture → Artifact → Surface → Locator → Excerpt → Observation
```

- **Capture** — governed acquisition act/receipt.
- **Artifact** — immutable acquired bytes/material preserved by the Vault.
- **Surface** — frozen versioned representation used for inspection/citation.
- **Locator** — durable address into one exact Artifact/Surface version.
- **Excerpt** — exact bounded evidence selected through a Locator.
- **Observation** — source-local structured statement of what the preserved evidence presents.

A better extractor creates a new Surface. It never mutates the citation target under an existing Locator.

An Excerpt proves what material is present. It does not prove the proposition is true.

An Observation answers **“what does this source present?”**, not **“what does the Desk believe?”**

## Shared Record

```text
Entity
Event
Claim
Open Question
Notice   # working name; previously Analyst Finding
```

Not every destination object belongs in the first implementation slice.

## Human authority

```text
Decision
```

Viewing, model confidence, repetition, salience, or elapsed time never substitutes for a Decision.

## Investigation / editorial

```text
Case
Angle
Rendition
Rendition Unit
Publication
```

## Operational

```text
Run
```

A Run is bounded work with explicit provenance, not a persistent autonomous agent identity.

## Derived / rebuildable

FTS indexes, trigram indexes, embeddings, ANN indexes, graph layouts/neighborhood caches, public read models, cached summaries, and salience rankings are rebuildable.

> **Nothing durable may point only into rebuildable state.**

---

# 2. Claim and Decision

## Claim

A **Claim** is a durable Desk-level proposition.

Current strong direction:

```text
Source says X
    ↓
Observation

X is the proposition
    ↓
Claim

What the Desk decides about X
    ↓
Decision
```

Do not reintroduce `source_asserted` as Claim authority merely because an Observation supports it.

> **A Case is a scope of investigative attention, not a scope of truth.**

Claims live in the shared Record. Cases associate Claims for relevance, inquiry, hypothesis, and editorial work.

## Decision

A **Decision** is an explicit human-authority event acting on an exact durable target/version.

Potential uses: Claim posture, Entity resolution, Notice disposition, source-independence judgment, rendition approval, publication authorization, and correction/public-safety decisions.

Conceptually it carries actor, decided time, target/version, action, rationale where required, and lineage/supersession.

The conceptual primitive does **not** require one weak polymorphic table.

## Mutation rule

> **Governed semantic state is append-only or versioned through append-only lineage.**

Operational/rebuildable state may mutate. Governed corrections must not erase prior understanding or prior Decisions.

---

# 3. Identity

An **Entity** is a durable identity anchor.

Names, aliases, identifiers, addresses, and roles enter through Observations; storage near an Entity does not silently make them canonical truth.

Deterministic anchors may support candidate identity resolution. They do not autonomously merge.

Required property:

> **Identity resolution must be reversible without rewriting historical evidence provenance.**

Therefore merge is a governed resolution Decision, not bulk FK rewriting; split/unmerge is first-class; prior resolution states remain reconstructable.

---

# 4. Provenance / Basis

**Basis** is the conceptual relation that explains what supports, contradicts, quotes, derives, or depends on something else.

The system must answer:

- What supports this Claim?
- What contradicts it?
- What evidence was quoted?
- What Notice caused this inquiry?
- Which Decisions affected this object?
- Which Publication units depended on this Claim?
- Which Publications are affected by a later correction?

Required walkback:

```text
Publication
  → Rendition version
  → Rendition Unit
  → Claim
  → Basis / EvidenceBinding
  → Observation / Excerpt
  → Locator
  → Surface
  → Artifact
  → Capture provenance
```

Reverse traversal must also work.

> **Every loaf decomposes back into crumbs.**

Physical design remains open: typed provenance tables + unified traversal versus a narrow shared Record-object identity spine.

---

# 5. Time

Keep separate:

- **effective/world time**
- **source-declared time**
- **acquired time**
- **recorded time**
- **decided time**

UUIDv7 time is not a substitute for any of them.

Historical precision must preserve exact day/instant, month-only, year-only, approximate, before, after, ranges, unknown, and conflicting observations.

Do not turn `1979` into `1979-01-01` while losing year-only precision.

PostgreSQL ranges may be query/index helpers, not the whole temporal meaning.

> **Do not use temporal constraints to erase legitimate disagreement between observations.**

`WITHOUT OVERLAPS`, `PERIOD`, and exclusion constraints are selective future tools for genuine Desk-internal invariants only.

The as-of UI may wait. The ability to reconstruct prior Record state may not be designed out.

---

# 6. Case, Event, Relationship, hypothesis

A **Case** is a durable scope of investigative attention. It does not own private truth and does not permanently close merely because a Run or Publication ends.

An **Event** is a likely future first-class anchor for a world occurrence, but is not automatically required in `0001`.

Current Relationship direction:

```text
Observation(relation_as_stated)
        ↓
Notice(relationship_candidate)
        ↓
Claim(shape=relationship)
        ↓
Decision
        ↓
relationship traversal / graph projection
```

A governed Relationship is a structured Claim shape/projection, not a second truth system.

Hypothesis overlays are Case-scoped and non-authoritative. They cannot flow directly into Rendition as fact.

---

# 7. Candidate intelligence — working name `Notice`

The final name is open. The semantic contract is not.

A **Notice** is a durable, non-authoritative candidate insight surfaced for human attention.

> **Look here; something may matter.**

It does not mean:

> **This proposition is true.**

Notices distinguish deterministic from interpretive triggers. Interpretive Notices preserve Basis, ordinary explanations/counterevidence, what they do not establish, and Run/model/rubric provenance.

Viewing a Notice changes nothing. A human Decision may dismiss, defer, promote to Open Question, initiate Claim/identity work, or request more research.

Dismissed Notices remain institutional memory.

Raw Notices never become a second publication truth path.

---

# 8. Intelligence priority

Build **source genealogy before broad No Coincidences**.

Core question:

> **Are these actually independent evidentiary paths?**

Prioritize exact Artifact identity, reprint/near-clone detection, quote fingerprinting, explicit citation dependency, shared filing/press-release/witness origins, and human-governed independence judgments.

Do not infer independence from URL/domain/article count.

Later, track proposition mutation through retelling: qualifier loss, wording shifts, added actors/motives, and increasing precision without new evidence.

Negative-space analysis requires an explicit expectation, corpus scope, and ordinary explanations.

> **If the expectation cannot be named, the Desk has a vibe, not a discrepancy.**

---

# 9. Story, Quinton, and publication

Story Intelligence is real, but no `StoryPackage` is admitted unless Angle proves insufficient in execution.

An **Angle** is durable editorial state. It does not alter Claim posture.

Quinton is a public/editorial voice profile, not Record authority.

> **Quinton-mode has no legal write path into evidence, Observation, Entity resolution, Notice disposition, or authoritative Claim state.**

Research/Record Intelligence stays neutral. Story Intelligence is neutral editorial work. Quinton is applied during Rendition drafting.

A **Rendition** is an exact target-native expression of an Angle.

A **Rendition Unit** is the smallest public/editorial unit needing independent Claim/evidence binding.

> **If the Desk promises “prove line six,” unit-level binding exists from the first real Publication.**

A **Publication** is the historical event that an exact approved Rendition version shipped. Later Record changes do not rewrite it.

Consequential stories receive a risk-tiered skeptical Run before publication; this is a rubric, not an autonomous agent.

---

# 10. LLM-native Record

```text
LLM
 ↓
governed reads / commands
 ↓
validation + provenance + authorization
 ↓
PostgreSQL / Vault services
```

Direct arbitrary model SQL remains rejected.

Reads should use few resource families, typed links/expansions, bounded default payloads, hard page sizes, no `include=all`, bounded graph neighborhoods, temporal warnings, discoverable legal traversals, and stable opaque IDs.

Machine writes express domain intent (`propose_*`, bind, request) rather than row mutation and preserve Run/model/rubric provenance.

Human-only effects remain human-only.

> **One Run has one declared operational mode and cannot gain new Record-write authority by changing prompt/persona mid-run.**

---

# 11. Public and commercial boundaries

The future public site is a governed projection, not the internal workbench.

Internal preservation rights do not automatically create public redistribution rights.

Researcher-facing factual surfaces default to neutral language and mechanically checkable receipts.

Audience/revenue metrics may influence topic and format. They must not change Claim posture, identity resolution, source independence, evidence quality, candidate salience, or publication-safety requirements.

> **Research volume itself can bias recurrence signals.**

Future recurrence systems need denominator/base-rate context.

---

# 12. Slice admission

## Likely first vertical slice

- Case
- Run
- Capture
- Artifact
- Surface
- Locator
- Excerpt
- Observation
- Claim
- Decision
- minimal Entity identity only if a real slice requires it

Required: evidence integrity/walkback, acquired/recorded/decided clocks, non-destructive governed lineage, neutral Run mode, paired Vault/Record restore proof, explicit refusals.

## Before first real Publication

Add Angle, Rendition, Rendition Unit, unit-level evidence binding, exact-content approval Decision, Publication snapshot, Quinton boundary, correction lineage, and appropriate skeptical/publication-risk gate.

## Once repetition exists

1. source genealogy
2. claim/narrative mutation
3. confirmed-Entity cross-Case recurrence
4. dismissed-work retrieval
5. base-rate-aware recurrence

Broad interpretive No Coincidences comes later.

---

# 13. Explicitly starved architecture

Do not reward proposals for:

- autonomous multi-agent newsroom;
- universal trust/suspicion/coincidence score;
- automatic identity merge;
- autonomous publication;
- chat-with-the-Record as primary architecture;
- public raw candidate feed;
- graph database as Record authority;
- embeddings as identity/corroboration;
- Quinton in extraction/Record Intelligence;
- invented Quinton biography as system truth;
- engagement metrics that modify Record authority.

> **If a capability cannot ultimately walk back toward addressable evidence, it is not Superman-level. It is costume.**

---

# 14. Worked investigation torture test

The grammar must represent this without destructive rewrite or a second truth path:

1. Create Case `C1`; start neutral Run `R1`.
2. `CAP1 → Artifact A1 → Surface S1 → Locator L1 → Excerpt X1`.
3. Observation `O1`: source says Person P began Role R in 2005.
4. Claim `CL1`: Person P began Role R in 2005.
5. Second source yields Observation `O2`: 2006.
6. Preserve both; deterministic chronology-conflict Notice `N1`.
7. Identity candidate `N2` maps a mention to Entity `E1`.
8. Human Decision `D1` rejects it; history remains.
9. Later evidence supports `E2`; Notice `N3`.
10. Human Decision `D2` accepts resolution without rewriting Observations.
11. Relationship candidate Notice `N4` is surfaced with temporal context and ordinary explanation.
12. Human Decision `D3` rejects it; no authoritative Relationship Claim exists.
13. Further evidence lets human Decision `D4` disposition `CL1` or a precise successor.
14. Neutral Story Run creates Angle `AN1`.
15. Skeptical Run attempts to break the Angle; human dispositions concerns.
16. Quinton Rendition Run drafts exact version `RV1`.
17. Factual Rendition Unit `U6` binds to Claim/evidence: “prove line six.”
18. Human Decision `D5` approves exact `RV1`; Publication `P1` records release.
19. Later Capture yields Observation `O3` changing understanding.
20. Human Decision `D6` supersedes current Claim posture without erasing `D4`.
21. As-of query reconstructs what the Desk knew before `P1`.
22. Reverse provenance identifies `U6` and `P1` as affected.

### Result

The proof does not require Event in slice 1, a second authoritative Relationship system, graph-as-truth, `StoryPackage`, suspiciousness scores, autonomous agents, destructive merges, or temporal constraints that erase disagreement.

---

# 15. Open before `0001`

1. Vault vs PostgreSQL ownership for Capture/Artifact/Surface/Locator/Excerpt metadata.
2. Capture/archive fidelity per media type.
3. Excerpt durability/granularity and Locator envelope.
4. Physical append/version/supersession model.
5. Physical Decision representation.
6. Physical Basis/provenance representation and reverse traversal.
7. Claim identity/deduplication, posture, and versioning.
8. Entity mention/membership and merge/split/unmerge representation.
9. Historical temporal-value representation and exact as-of convention.
10. Minimal LLM read envelope and first-slice command/refusal/idempotency contract.
11. Run mode/voice ACL.
12. Internal UUIDv7 versus public/tool-facing identifiers.
13. Whether Entity and Open Question belong in slice 1.
14. Paired Vault + Record backup/restore integrity contract.
15. Explicit destination nouns excluded from `0001`.

---

# 16. Promotion rule

This file remains workshop material until reviewed.

After reconciliation:

- doctrine → `VISION.md`
- canonical nouns → `CONTEXT.md`
- model/write rules → `AGENTS.md` + ADRs
- database/authority decisions → ADRs
- operational details → architecture/reference docs
- speculative taxonomies → discard or retain only as design history

The authoritative repository should become **smaller and sharper** than this file.

---

# 17. North-star test

A mature Desk should feel like:

- **Memory:** we have seen this before.
- **Honesty:** we cannot say that yet.
- **Speed:** governed work is reusable.
- **Resistance:** the system challenges attractive frames before consequential publication.
- **Replay:** we can reconstruct what we knew, decided, and later changed.

> **The Discrepancy Desk is not an AI that notices everything. It is an institution that can remember, show its work, change its mind out loud, and still be entertaining.**

If the architecture cannot support that sentence, it is not ready for `0001_initial`.
