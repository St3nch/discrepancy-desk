# Foundation Contract 07 — Observation / Proposition Shape

**Status:** NON-AUTHORITATIVE DESIGN DRAFT

**Depends on:** `FOUNDATION-MODEL-V2.md`, `CONTRACT-01-EVIDENCE.md`, `CONTRACT-02-CLAIM-DECISION.md`, `CONTRACT-03-IDENTITY.md`, `CONTRACT-04-BASIS-PROVENANCE.md`, `CONTRACT-05-TEMPORAL-AS-OF.md`, `CONTRACT-06-LLM-NATIVE-RECORD-SURFACE.md`

**Purpose:** Define the minimum structured semantic shape shared by source-local Observations and Desk-level Claims without collapsing those objects, inventing a new durable Proposition noun, or pushing core meaning into ungoverned JSON.

> **Observation records what preserved evidence presents. Claim represents the proposition the Desk is considering. Shared grammar does not make them the same object.**

---

# 1. Observation atomicity

An Observation represents one source-local semantic assertion. One assertion may contain multiple participants, values, qualifiers, or temporal elements.

`"Alice joined Acme in 2005."` may therefore be one Observation with independently addressable participant/value slots. But `"Alice joined Acme and later founded Beta."` normally decomposes into two Observations sharing evidence where appropriate.

Do not split mechanically on punctuation. Split when independently correcting, resolving, contradicting, promoting, or citing one semantic assertion would otherwise require rewriting an unrelated assertion.

---

# 2. Typed hybrid rather than free text or universal triples

Observation and Claim content use a typed hybrid representation.

The foundation rejects both opaque free text as the only semantic representation and one universal subject/predicate/object ontology forced onto every assertion.

Governed assertion shapes may instead provide typed roles appropriate to the assertion family, for example:

```text
kind: role_membership
person: <participant slot>
organization: <participant slot>
role: <value>
time: <temporal value>
modality: <source-local qualifier>
```

The exact shape vocabulary remains open and deliberately small.

Core participant roles, assertion kinds, temporal semantics, attribution, modality, and proposition structure must not be hidden inside unrestricted `payload jsonb`. JSONB may later hold narrowly typed payloads with explicit validation; it is not the semantic escape hatch for the Record.

---

# 3. Shared grammar does not create a Proposition object

Observation and Claim may reuse compatible semantic vocabulary and typed structures where that preserves meaning and reduces translation drift.

```text
Observation O1:
  source presents Person P as officer of Organization O during T

Claim C1:
  Person P was officer of Organization O during T
```

The reusable grammar does not require a durable `Proposition` row/table/object between them.

The authority distinction remains:

```text
preserved evidence
      ↓
Observation — source-local meaning
      ↓
Claim — Desk proposition
      ↓
Decision — human authority
```

If execution later proves distinct durable Proposition identity necessary, it must earn admission through worked scenarios rather than normalization convenience.

---

# 4. Attribution, modality, and hedging are semantic

These source-local statements are not interchangeable:

```text
P did X.
Witness W says P did X.
P allegedly did X.
P may have done X.
```

The exact wording remains preserved through Excerpt/Locator. The structured Observation retains enough typed attribution/modality to prevent extraction from manufacturing certainty or erasing who made the assertion.

Relevant distinctions may include direct assertion, attributed assertion, allegation, possibility, denial, reported belief/opinion, and an explicit negative assertion where the source actually states one. This is not permission to invent a giant modality taxonomy before execution requires it.

---

# 5. Stable addressable participant and identity slots

An Observation may contain stable subordinate participant/identity slots:

```text
Observation O17
  actor slot A1: "Robert Smith"
  organization slot A2: "Acme Corp"
```

Those slots may remain unresolved, later resolve to different Entities independently, and remain durable targets for identity candidate Notices and Decisions.

They do not become first-class `Mention` objects merely because they are addressable. Resolving `A1` must not silently resolve another `"Smith"` slot in the same or another Observation.

The physical subordinate-slot identifier strategy remains open.

---

# 6. Observation correction preserves lineage

An admitted Observation is not silently overwritten when extraction or interpretation is later found wrong.

Examples include a mistranscribed role, missed qualifier, attributed speech mistaken for narrator voice, over-normalized time, or incorrect participant segmentation.

Correction creates a new Observation version or successor under append/version lineage sufficient to reconstruct what the Desk had admitted previously. The original evidence remains unchanged.

Downstream Claims, Notices, Decisions, Rendition Units, and Publications that materially depended on the superseded Observation remain discoverable through reverse provenance.

Producer confidence, parser version, diagnostics, or model identity are provenance. They are not Claim posture and do not determine truth.

---

# 7. Temporal interpretation preserves source wording

Structured temporal interpretation may coexist with exact source wording.

```text
source wording: "early 2004"
structured interpretation:
  precision: year/period
  qualifier: early / approximate
  bounded interpretation: implementation-defined
```

The structured interpretation supports querying, comparison, conflict detection, and Claim construction. It never replaces the exact wording and may itself be corrected through Observation lineage.

Do not treat `2004`, `early 2004`, `around 2004`, and `2004-01-01` as equivalent.

---

# 8. Observation-to-Claim promotion is explicit

An Observation does not automatically generate, confirm, or deduplicate a Claim.

Promotion may reuse compatible semantic structure, but it is a new governed act.

```text
O1: Source A presents P as officer of O in 2005.
O2: Source B presents P as officer of O in 2006.

possible Claims:
  C1: P was officer of O in 2005.
  C2: P was officer of O in 2006.
```

Both Claims may coexist. Source attribution/hedging on an Observation must not disappear from the Basis path merely because a proposed Claim omits that source-local framing.

---

# 9. Relationship assertions follow provenance

A source-stated relationship may proceed directly:

```text
Excerpt
  ↓
Observation(relation_as_stated)
  ↓
Claim(shape=relationship)
  ↓
Decision
```

A Desk/model-inferred relationship follows the candidate path:

```text
Observations / Claims
       ↓
Notice(kind=relationship_candidate)
       ↓
Claim(shape=relationship) when warranted
       ↓
Decision
```

Notice is therefore not mandatory ceremony around every source-stated relationship.

---

# 10. Observation shape is fail-closed

The system must not quietly admit malformed or semantically ambiguous structured Observations merely because source text was captured.

If an extractor cannot safely determine required roles or qualification for a chosen Observation kind, it may emit no Observation with diagnostics, choose a less specific valid shape, or create a candidate Notice where the uncertainty itself is worth review.

It must not invent participants, dates, attribution, certainty, or relation direction merely to satisfy a schema.

---

# 11. Worked proof

1. Capture A preserves: `"Robert Smith allegedly joined Acme in early 2004; Smith later denied the appointment."`
2. The evidence chain preserves exact text and durable Locators.
3. `O1` records the source allegation that Robert Smith joined Acme in early 2004.
4. `O1` has independently addressable person and organization slots.
5. `O2` records that Smith denied the appointment.
6. `O1` preserves allegation modality and approximate temporal interpretation without replacing `"early 2004"`.
7. Identity Notice `N1` proposes `O1.person_slot → E17`; human Decision accepts it.
8. `O2.person_slot` remains independently unresolved until supported.
9. Claim `C1` is proposed with Basis to `O1`; `O1` does not automatically confirm it.
10. Later review discovers the extractor misread `"joined"`; the source actually says `"joined talks with"`.
11. Corrected `O1v2` is appended/supersedes `O1v1`; evidence bytes remain unchanged.
12. Reverse provenance identifies `C1` and downstream governed work potentially affected.
13. Historical as-of reads still reconstruct the period when `O1v1` was admitted.

If the physical design cannot perform this proof without overwriting Observation history, resolving every same-name occurrence together, or hiding core meaning in opaque JSON, this contract has failed.

---

# 12. Open before schema/API promotion

1. Minimal governed Observation/Claim shape vocabulary for slice 1.
2. Physical representation of typed participant/value/temporal slots.
3. Stable subordinate-slot identifier strategy.
4. Exact Observation version/supersession representation.
5. Canonical Claim content/version representation compatible with this grammar.
6. Exact attribution/modality vocabulary required for slice 1.
7. Typed temporal-value representation shared with the Temporal contract.
8. Whether Observation kinds are governed rows, code-defined vocabulary, or another constrained mechanism.
9. Default-deny validation matrix for Observation kinds and allowed slot roles.
10. Command/refusal/idempotency contract for `propose_observation` and correction.

---

# 13. Rejected shortcuts

- one Observation containing unrelated assertions merely because they share a sentence or source;
- free text as the only semantic representation;
- universal RDF-style triples forced onto every assertion;
- unrestricted JSONB carrying core proposition meaning;
- durable `Proposition` noun admitted solely for normalization convenience;
- first-class `Mention` before a worked scenario proves it necessary;
- dropping attribution, allegation, uncertainty, or denial during normalization;
- global same-string identity resolution;
- silent overwrite of admitted Observations;
- model/extractor confidence used as truth or Claim posture;
- normalized temporal interpretation replacing source wording;
- Observation admission automatically creating or confirming Claims.

---

# 14. Contract test

The Observation / Proposition Shape foundation is good enough only if all six are mechanically supportable:

> **One admitted Observation can be corrected without rewriting its evidence or unrelated source-local assertions.**

> **Source attribution and uncertainty survive structure rather than being normalized into certainty.**

> **Identity can resolve one stable participant occurrence without resolving every similar string.**

> **Observation and Claim can share typed semantic grammar without collapsing their authority boundary.**

> **Core proposition meaning is queryable and constrained without a universal ontology or opaque JSON escape hatch.**

> **A historical as-of read can reconstruct the Observation version the Desk had actually admitted at that time.**
