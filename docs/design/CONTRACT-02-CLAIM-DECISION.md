# Foundation Contract 02 — Claim and Decision

**Status:** NON-AUTHORITATIVE DESIGN DRAFT

**Depends on:** `FOUNDATION-MODEL-V2.md`, `CONTRACT-01-EVIDENCE.md`

**Purpose:** Separate source-local evidence from Desk propositions and human authority before any Claim schema or write API is designed.

---

# 1. The three-layer distinction

```text
Source presents X
      ↓
Observation

X as a proposition
      ↓
Claim

What the Desk decides about X
      ↓
Decision
```

This distinction is foundational.

> **Storage adjacency must never turn “the source says X” into “the Desk says X.”**

---

# 2. Observation boundary

Observation is governed by the Evidence contract.

An Observation is source-local and evidence-bound. It may record what a source states, names, dates, identifies, depicts, or otherwise presents.

Observation does not carry Desk confirmation posture.

An Observation can exist without any Claim.

Examples:

- source states appointment year 2005;
- filing lists Person P as officer of Organization O;
- article quotes Witness W saying event E occurred;
- page metadata declares publication date D.

Whether those propositions are true is downstream.

---

# 3. Claim contract

A **Claim** is a durable proposition represented by the Desk.

The Claim is about the proposition itself, not about who happened to say it first.

Examples:

- Person P began Role R in 2005.
- Organization A received Grant G.
- Person P was an officer of Organization O during interval T.
- Event E occurred at Location L on Date D.

A Claim may be proposed because of:

- one or more Observations;
- one or more existing Claims;
- a human-authored proposition;
- later, an accepted analytical Notice that causes a Claim proposal.

Those origins are Basis/provenance, not Claim truth.

## Claim properties

The final physical model is open, but a Claim needs conceptually:

- stable durable identity;
- proposition content/structure;
- explicit version/record lineage;
- Basis/provenance references;
- temporal semantics where the proposition is temporal;
- current human-authority posture derivable from Decisions;
- ability to retain contradictory competing Claims when propositions genuinely conflict.

## Global Record rule

Current strong direction:

> **A Case is a scope of investigative attention, not a scope of truth.**

Claims live in the shared Record.

Cases associate Claims for relevance, inquiry, hypothesis, salience, or editorial work.

If a proposition appears to mean something different in a different Case, first test whether the proposition is underspecified. Prefer a more precise Claim over duplicated Case-local truth.

Case-scoped Claims remain an open escape hatch only if a worked example proves they are necessary.

---

# 4. Claim identity and proposition precision

Claim identity is not automatically sentence identity.

These may be different propositions:

```text
P joined O in 2005.
P became an officer of O in 2005.
P worked with O sometime in 2005.
```

Likewise, two differently worded statements may express the same proposition.

The Desk must not silently deduplicate Claims merely because text is similar.

Semantic similarity may propose candidate equivalence later. It does not merge Claims.

The final model must decide what proposition structure is canonical enough for identity/reuse without forcing every Claim into an over-engineered ontology.

---

# 5. Claim posture

Posture is human-governed state about a Claim.

The exact vocabulary is open and should remain small.

Candidate dimensions may eventually include states such as:

- unreviewed/proposed;
- confirmed/supported for Desk use;
- disputed;
- rejected;
- superseded;
- unresolved.

These are illustrative, not yet canonical enums.

Important:

- posture is not a model confidence score;
- posture is not inherited from a source;
- corroboration count does not automatically determine posture;
- elapsed time does not determine posture;
- viewing does not determine posture.

Human Decision is the authority mechanism.

---

# 6. Decision contract

A **Decision** is an explicit human-authority act against an exact durable target/version.

Decision is a general conceptual primitive, not permission to create one weak polymorphic table.

A Decision conceptually carries:

- actor identity;
- decided time;
- target object and exact target version/state;
- action/decision kind;
- rationale where required;
- Basis/review material where relevant;
- relationship to a prior Decision if superseding/correcting it.

## Decision examples

- confirm/reject/dispute a Claim;
- accept/reject an Entity-resolution candidate;
- dismiss/defer/promote a Notice;
- judge source/evidence independence;
- approve an exact Rendition version;
- authorize Publication;
- record a correction/takedown/public-safety action.

The effect of a Decision is typed by domain context.

Do not let a generic Decision table become a place where arbitrary string actions bypass domain validation.

---

# 7. Actor and machine provenance

Human Decisions always identify a human actor, even in a single-operator system.

Machine proposals separately preserve:

- Run identity;
- provider/model identity where applicable;
- rubric/version;
- producing mode;
- Basis.

Do not blur `human actor` and `model producer` into one authority field.

The machine may propose.

The machine may not manufacture a human Decision.

---

# 8. Mutation / lineage rule

> **Governed semantic state is append-only or versioned through append-only lineage.**

Corrections do not erase earlier state.

The exact physical mechanism remains open, but the final design must support:

- prior Claim versions remaining addressable;
- prior Decisions remaining addressable;
- a later Decision superseding/changing current posture without deleting the prior Decision;
- publication bindings remaining tied to the exact historical Claim/version/posture they used;
- as-of reconstruction.

Operational/rebuildable rows such as leases, caches, heartbeats, indexes, or projections may mutate under their own contracts.

Do not turn append-only epistemic lineage into a universal event-sourcing religion for every table.

---

# 9. Contradiction and disagreement

The Record may legitimately contain competing Claims.

Example:

```text
CL1: P began Role R in 2005.
CL2: P began Role R in 2006.
```

Their supporting Observations remain preserved.

The system may surface a deterministic chronology-conflict Notice.

Human authority may later prefer one, reject one, refine both, or leave the matter unresolved.

Database integrity must not force one source/world timeline merely to keep the schema tidy.

---

# 10. Claim from Claim / Desk inference

The Desk may eventually support an inference Claim whose Basis includes other governed Claims rather than direct Observations alone.

Example:

```text
CL-A + CL-B + source-lineage Decision
          ↓
CL-C: the apparent corroboration is dependent on one underlying filing
```

Rules:

- inference must be explicit as such in provenance/Claim shape;
- it cannot hide or launder the risk/posture of its Basis;
- it must remain traversable to underlying evidence;
- publication still requires human-authority posture appropriate to the material.

This contract does not yet define the final inference taxonomy.

---

# 11. Worked proof

1. Observation `O1`: Source A presents appointment year 2005.
2. Observation `O2`: Source B presents appointment year 2006.
3. Claim `CL1`: P began Role R in 2005.
4. Claim `CL2`: P began Role R in 2006.
5. Neither Observation automatically confirms either Claim.
6. A chronology-conflict Notice may be produced from `O1/O2` or `CL1/CL2` depending on the final detector contract.
7. Human Decision `D1` leaves the matter unresolved pending stronger evidence.
8. Later Observation `O3` comes from a contemporaneous filing supporting 2005.
9. Human Decision `D2` confirms `CL1` for Desk use and explicitly supersedes the current posture established by `D1` where appropriate.
10. `D1`, `O1`, `O2`, `CL2`, and the conflict remain in history.
11. A Publication made before `D2` can still be evaluated against the earlier Record state.

If the final model requires deleting `CL2`, overwriting `D1`, or rewriting the old Publication to make this work, the contract has failed.

---

# 12. Open before ADR/schema promotion

1. Canonical Claim proposition representation: structured fields, normalized statement, or hybrid.
2. Claim deduplication/equivalence rules.
3. Minimal posture vocabulary and whether posture is one state or multiple dimensions.
4. Physical Claim versioning/supersession model.
5. Physical Decision envelope and typed effect representation.
6. Whether Decision targets require a shared Record-object identity spine or typed tables.
7. Exact relationship between Decision and Basis/review material.
8. As-of query convention over Claim versions/Decisions.
9. Whether any genuine Case-scoped Claim exists; prove with worked examples before admitting.
10. Inference-Claim representation and publication-risk inheritance rules.
11. Human actor identity model.
12. Command/refusal contract for `propose_claim` and human decision operations.

---

# 13. Rejected shortcuts

- source assertion stored as confirmed Desk Claim;
- `source_asserted` posture used to collapse Observation and Claim;
- model confidence used as Claim posture;
- automatic confirmation from source count;
- destructive overwrite of prior posture;
- silent Claim merge by semantic similarity;
- Case-local copy of a global Claim merely for convenience;
- arbitrary free-text Decision actions with no typed effect validation;
- model-created human Decision;
- publication directly from raw Notice/Observation without governed Claim path where factual assertion is made.

---

# 14. Contract test

The Claim/Decision foundation is good enough only if all four are mechanically supportable:

> **The source can say X without the Desk saying X.**

> **The Desk can represent X as a proposition without deciding it is true.**

> **The human can change the Desk's posture later without erasing the earlier decision.**

> **A historical Publication can still be evaluated against the exact Record state that existed when it shipped.**
