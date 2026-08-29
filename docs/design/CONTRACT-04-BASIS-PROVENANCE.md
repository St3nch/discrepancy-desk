# Foundation Contract 04 — Basis / Provenance

**Status:** NON-AUTHORITATIVE DESIGN DRAFT

**Depends on:** `FOUNDATION-MODEL-V2.md`, `CONTRACT-01-EVIDENCE.md`, `CONTRACT-02-CLAIM-DECISION.md`, `CONTRACT-03-IDENTITY.md`

**Purpose:** Define how durable Desk objects show what supports them, what contradicts them, what they depend on, and what later work may be affected when an upstream dependency changes.

> **What supports this?** and **What depends on this?** are equally fundamental Desk questions.

---

# 1. Basis is a semantic contract before it is a table

**Basis** is the durable, typed explanation of why a governed object is supported, contradicted, derived, reviewed, or otherwise dependent on another durable object.

Basis is a foundation concept. This contract does **not** require one generic `basis` table or one universal polymorphic Record-object spine.

The physical model must preserve the semantics and PostgreSQL integrity requirements defined here. Typed provenance tables, a constrained shared identity spine, or a hybrid remain open until schema design.

> **Do not choose a convenient physical abstraction before proving that it can preserve typed meaning and referential integrity.**

---

# 2. Basis never creates authority

Basis explains why something is under consideration or why a human acted. It does not manufacture authoritative posture.

```text
Evidence / Record objects
        ↓ Basis
Claim / Notice / Decision / Rendition Unit
        ↓ when applicable
human Decision
```

Five supporting Observations do not confirm a Claim.

A deterministic identifier match does not resolve an Entity.

A model explanation does not become evidence merely because it was persisted.

Authority remains where the relevant contract places it, especially in explicit human Decisions.

---

# 3. Relation semantics must be explicit

The system must not require a later model to infer from prose whether one object supports, contradicts, derives, or otherwise depends on another.

Basis/dependency relations therefore need explicit semantic kinds.

Illustrative kinds include:

- supports;
- contradicts;
- quotes / directly_evidences;
- derived_from;
- depends_on;
- reviewed_with.

These names are provisional. The invariant is not.

> **The meaning of a durable dependency must be machine-readable.**

Do not collapse support and contradiction into an unlabeled generic edge.

---

# 4. Evidence-local support and Observation support are distinct

Claims and other governed objects may need different legitimate support paths.

Normal semantic path:

```text
Excerpt
  ↓
Observation
  ↓ supports / contradicts
Claim
```

An Observation gives structured source-local meaning.

The direct evidence path is a narrow exception. It is valid only when the Claim proposition is materially about the existence/content of the exact bounded material itself and no additional interpretation beyond that presence is being asserted. Ordinary world-fact Claims require the Observation layer.

Example narrow case: "this preserved document contains the exact string X at this location." That proposition may be supported directly by the verified Excerpt. "Person P committed act A" may not skip Observation merely because an Excerpt contains words about P and A.

When the narrow condition holds:

```text
Excerpt ──directly_evidences──> Claim
```

These paths must not be treated as interchangeable.

`Excerpt` means exact bounded evidence is present.

`Observation` means the source presents a structured source-local statement.

`Claim` means the Desk-level proposition.

The physical design must preserve those distinctions rather than forcing every dependency through one ceremonial layer.

> **Direct Excerpt support proves bounded material presence/content. It is not a deadline shortcut around source-local Observation semantics.**

---

# 5. Claims may depend on Claims

The Desk may form explicit analytical or derived Claims from other Claims.

Example:

```text
C1: Company A owned Domain X in 2020
C2: Person P controlled Company A in 2020

C1 ─┐
    ├─ derived_from → C3
C2 ─┘

C3: Person P indirectly controlled Domain X in 2020
```

This is allowed only when the dependency is explicit and traversable.

The system must preserve the distinction between:

- what evidence directly presents;
- what a source-local Observation states;
- what a Claim proposes;
- what the Desk inferred from other Claims;
- what a human Decision authoritatively concluded about posture.

Inference must never be laundered into source testimony.

---

# 6. Decisions may and often should preserve Basis

A consequential human Decision should be able to preserve the exact material reviewed when the Decision was made.

Examples include:

- Claim posture;
- Entity identity resolution;
- Notice disposition;
- source-independence judgment;
- Rendition approval;
- Publication authorization;
- correction, takedown, privacy, or safety action.

The system should be able to answer:

```text
Why did we decide this?
What supporting material existed?
What counterevidence existed?
What prior Decisions were operative?
What changed later?
```

This does not require a giant rationale document for every trivial action. It requires the model to support exact review Basis when consequence demands it.

---

# 7. Counterevidence remains first-class

A later human Decision does not erase contradictory Basis.

Example:

```text
O1 ──supports────> C1
O2 ──contradicts─> C1
D1: confirm posture of C1
```

The current Claim view may show a confirmed posture while still exposing both supporting and contradicting Basis.

> **Decision settles posture, not history.**

Counterevidence must remain queryable after confirmation, rejection, supersession, or publication.

---

# 8. Exact historical targets

Durable provenance must bind the exact historical target/version/state that mattered at the time of dependency.

A Publication cannot merely say it depended on durable Claim identity `C1` if `C1` later changes materially.

Conceptually:

```text
Publication P1
   ↓
Rendition version R3
   ↓
Rendition Unit U6
   ↓
Claim C1 @ the historical version/state used
   ↓
Basis operative at that time
```

Current Claim state may later differ without changing the historical publication chain.

The same principle applies to identity Decisions, Notice disposition, approval, and correction lineage.

> **Durable dependency cannot float silently to the newest version of its target.**

---

# 9. Forward and reverse traversal are both mandatory

Every durable dependency admitted by the model must be queryable in both directions.

Forward provenance:

```text
Claim → what supports or contradicts it?
Decision → what was reviewed?
Publication → what Claims/evidence justified this unit?
```

Reverse provenance:

```text
Excerpt → what Claims use this?
Claim version → what Rendition Units depend on it?
Identity Decision → what later Claims/Notices/Publications may be affected?
```

This is an architectural requirement, not a reporting convenience.

The Identity correction contract specifically depends on reverse traversal.

---

# 10. Correction impact is discovery, not silent rewrite

When an upstream governed dependency is later corrected or superseded, downstream governed objects must not be silently rewritten.

Example:

```text
Identity Decision D1
      ↓
Claim C7
      ↓
Rendition Unit U4
      ↓
Publication P2

D9 supersedes D1
```

The system should identify `C7`, `U4`, and `P2` as potentially affected.

Then the relevant human/governed correction workflow decides what, if anything, changes.

Rebuildable projections may recompute under their own contracts. Governed semantic/public history remains explicit.

---

# 11. Model analysis is proposal provenance, not evidentiary Basis

Model-generated analysis may notice a pattern, contradiction, similarity, or possible inference.

That analysis can legitimately become provenance of:

- a Notice;
- a proposed Claim;
- a research lead;
- an explicitly derived analytical Claim whose Record dependencies are visible.

The model's prose itself is not evidence merely because the model said it.

Bad path:

```text
LLM said X → evidentiary support for X
```

Required path:

```text
model notices X
      ↓ proposal provenance
Notice / proposed Claim
      ↓ explicit dependencies
Record evidence / Claims
```

The system may preserve which model/Run produced the proposal without laundering that proposal into external-world evidence.

---

# 12. Not every runtime dependency is durable Basis

Durable provenance is required when a durable semantic, authority, investigative, editorial, or public object materially depends on another object in a way that may later need audit or correction.

Strong candidates include:

- Claim Basis;
- Decision review Basis;
- Notice Basis;
- identity-resolution dependencies;
- source-independence judgments;
- Rendition Unit bindings;
- Publication provenance;
- correction dependencies.

Not every temporary computation deserves durable history.

Examples that are rebuildable by default:

- search result order;
- FTS/trigram ranking;
- embedding neighbors;
- transient summaries;
- UI sort order;
- graph layout;
- cached counts.

> **Nothing durable may depend only on rebuildable state.**

But rebuildable computation does not automatically become durable Basis.

---

# 13. Physical provenance design remains open

The semantic contract intentionally does not choose between:

1. narrow typed provenance tables with direct foreign keys;
2. a constrained shared Record-object identity spine;
3. a hybrid where common traversal uses a narrow spine while high-value relationships retain typed tables/FKs.

Any accepted physical design must prove:

- referential integrity;
- allowed source/target type combinations;
- explicit semantic relation kinds;
- exact historical target/version binding;
- efficient forward traversal;
- efficient reverse traversal;
- no dangling dependency solely into rebuildable state;
- no generic polymorphic junk drawer that permits semantically invalid edges.

PostgreSQL convenience does not override these requirements.

---

# 14. Worked proof

1. Capture A produces Excerpt `X1` and Observation `O1`.
2. `O1` supports Claim `C1`.
3. Capture B produces Observation `O2` that contradicts `C1`.
4. Both relationships remain explicit and typed.
5. Human Decision `D1` confirms the current posture of exact Claim version `C1v2` after reviewing both sides.
6. `D1` preserves its review Basis.
7. Claim `C2` plus `C1v2` support derived Claim `C3`; the derivation is explicit.
8. Rendition Unit `U6` binds exact `C3` state and the evidence/provenance required to substantiate its public assertion.
9. Publication `P1` preserves the exact approved Rendition/version chain.
10. Later Decision `D9` supersedes an identity Decision on which `C2` depended.
11. Reverse provenance finds `C2`, then `C3`, then `U6`, then `P1` as potentially affected.
12. None of those governed objects is silently rewritten.
13. A human correction/review process decides what changes.
14. As-of reconstruction still explains why `P1` was publishable under the Record state that existed at the time.

If the physical design cannot perform this proof, the Basis/Provenance contract has failed.

---

# 15. Open before ADR/schema promotion

1. Exact Basis/provenance relation vocabulary.
2. Allowed source/target type matrix.
3. Physical typed-table vs shared-spine vs hybrid design.
4. Exact version-target mechanism for mutable/versioned governed objects.
5. Whether Excerpt-direct Claim support is limited to specific Claim shapes.
6. How Claim-on-Claim derivation distinguishes inference from proposition equivalence.
7. Minimum Basis requirements by Decision consequence/risk.
8. Reverse-provenance query/index strategy in PostgreSQL 18.
9. How Run/model proposal provenance connects to Notice/Claim proposals without becoming evidence.
10. Correction-impact status/read model without creating an automatic guilt/suspicion score.
11. How public-safe provenance projection redacts private/internal Basis while preserving auditability.
12. Idempotency rules for repeated proposal/binding operations.

---

# 16. Rejected shortcuts

- source count as Claim authority;
- generic unlabeled edges whose semantics must be inferred from prose;
- treating support and contradiction as the same relation;
- making every Claim depend only on Observations even when exact Excerpt evidence is the real support;
- treating model prose as evidence;
- hiding counterevidence after a Decision;
- floating dependencies that silently follow the newest target version;
- forward-only provenance;
- silent downstream rewrite after an upstream correction;
- persisting every temporary search/ranking/cache dependency as durable provenance;
- one universal polymorphic relation table before type/integrity constraints are proven.

---

# 17. Contract test

The Basis/Provenance foundation is good enough only if all five are mechanically supportable:

> **The Desk can show exactly what supports and contradicts a durable proposition or Decision.**

> **Basis never manufactures human authority.**

> **A durable dependency binds the exact historical target that mattered at the time.**

> **Every admitted durable dependency can be walked both forward and backward.**

> **When an upstream correction matters, the Desk can find downstream work without rewriting history.**
