# Foundation Contract 03 — Identity

**Status:** NON-AUTHORITATIVE DESIGN DRAFT

**Depends on:** `FOUNDATION-MODEL-V2.md`, `CONTRACT-01-EVIDENCE.md`, `CONTRACT-02-CLAIM-DECISION.md`

**Purpose:** Define reversible Entity identity and resolution semantics before Entity schema, source genealogy, recurrence intelligence, or cross-Case traversal are designed.

> **Identity resolution improves the current Record without rewriting what the Desk previously knew.**

---

# 1. Entity contract

An **Entity** is a durable identity anchor intended to denote one real-world subject the Desk needs to refer to across evidence, Claims, Cases, time, and publications. Multiple Entity anchors may temporarily refer to the same real-world subject until human resolution establishes the current Record view.

Potential subject families include people, organizations, places, programs, and other concrete identity-bearing subjects. The taxonomy is not settled by this contract.

An Entity is **not** a bag of asserted attributes.

Names, aliases, identifiers, addresses, roles, domains, descriptions, and other source-presented identity material enter through evidence-bound Observations.

The Entity supplies durable identity; evidence supplies what sources present about that identity.

---

# 2. No first-class Mention yet

Do not admit `Mention` as a foundation noun in the first model.

The evidence chain already preserves exact local wording and location:

```text
Artifact → Surface → Locator → Excerpt → Observation
```

An Observation can record that a source presents `Bob Smith` in a particular local context without asserting which Entity that text denotes.

Identity work then proceeds:

```text
Observation("Bob Smith" presented here)
        ↓
Notice(kind=identity_candidate)
        ↓
Decision
```

Admit a separate Mention object only if execution proves that one Observation routinely needs multiple independently addressable identity occurrences with semantics that cannot be represented cleanly through evidence-local Observation structure.

---

# 3. Candidate identity

Candidate identity uses the general candidate-intelligence envelope:

```text
Notice(kind=identity_candidate)
```

Do not create a separate `IdentityCandidate` truth system.

A candidate may be supported by deterministic anchors, lexical/contextual similarity, temporal overlap, shared attributes, or later analytical methods. Those inputs affect Basis and review priority, not authority.

Deterministic evidence can make a candidate extremely strong. It still does not create an authoritative identity resolution automatically.

> **The machine proposes identity. The human resolves identity.**

---

# 4. Human resolution

An authoritative identity resolution is a human **Decision** against exact durable identity candidates/anchors.

The Decision records the accepted or rejected resolution and preserves its Basis, decided time, actor, and lineage according to the Claim/Decision contract.

Examples:

- accept that Entity `E17` and `E42` denote the same real-world subject;
- reject that proposed resolution;
- later supersede an accepted resolution when new evidence shows it was wrong.

Model confidence, identifier equality, source count, graph similarity, or repeated prior use never substitutes for the Decision.

---

# 5. Global Record identity

Authoritative Entity resolution belongs to the shared Record, not to an individual Case.

> **Case is scope of investigative attention, not scope of identity truth.**

A Case may carry a non-authoritative hypothesis that challenges an accepted resolution, but it does not create a parallel Case-local identity universe.

If later evidence changes the authoritative understanding, the shared Record changes through a new Decision with preserved lineage.

---

# 6. Merge means resolution, not destructive rewrite

When two Entity anchors are accepted as the same identity, do not bulk-rewrite historical Observations, Claims, evidence bindings, or Publications onto one surviving ID.

Conceptually:

```text
E17 ─┐
     ├─ D1: accepted same-identity resolution
E42 ─┘
      ↓
current resolved-identity projection
```

Both Entity IDs remain durable and addressable.

Current reads may expose one preferred/current resolved identity, but the projection is explained by Decisions rather than evidence mutation.

Old IDs must never become dead historical references merely because a later resolution exists.

---

# 7. Resolution clusters and transitivity

Accepted same-identity Decisions may produce a transitive current resolution cluster:

Same-identity and distinctness are both effects expressed through the existing human `Decision` primitive; this contract does not add a second identity-authority noun.

```text
D1: E17 = E42
D2: E42 = E99

current projection: {E17, E42, E99}
```

The projection may infer cluster membership transitively, but the system must not manufacture a human Decision that was never made.

Every authoritative supporting Decision/edge remains inspectable.

If a supporting Decision is later superseded, the current cluster is recomputed from the surviving accepted Decisions and any operative distinctness Decisions.

An authoritative **distinctness/split Decision** may state that specified Entity anchors must not occupy the same current resolved-identity cluster. It may also explicitly supersede the positive same-identity Decisions whose reasoning it overturns.

Distinctness is stronger than merely rejecting a candidate: rejected means "not accepted as same"; distinctness means "currently decided not to be the same identity."

If surviving positive same-identity Decisions still imply a path that conflicts with an operative distinctness Decision, the projection must not invent a hidden partition or silently choose one Decision over another. The affected resolution state is conflicted until human authority explicitly supersedes/reconciles the contradictory Decisions.

> **Identity projection may compute consequences of Decisions. It may not resolve contradictions between Decisions by itself.**

---

# 8. Split / unmerge

An incorrect historical resolution is corrected by appending a new distinctness/split Decision and, where necessary, explicitly superseding the prior positive resolution Decision(s) that conflict with the corrected identity state.

Do not delete, mutate, or rewrite the old Decision merely to make current identity tidy.

```text
D1: accept E17 = E42
        ↓ later evidence
D9: supersede D1; same-identity resolution no longer accepted
```

Current identity projections change.

Historical as-of projections preserve that D1 was the Desk's operative decision before D9.

This is the minimum required reversible-merge property.

---

# 9. As-of identity

Entity identity has at least two distinct temporal questions:

1. what identity relationship may have been true/effective in the world;
2. when the Desk resolved or changed its understanding of that identity.

Example:

```text
2027: evidence presents "R. Smith"; identity unresolved
2028: Decision resolves that occurrence/candidate to E17
```

Current view may expose `R. Smith → E17`.

An as-of-2027 Record view must still show the identity as unresolved.

Later knowledge must not be back-projected into an earlier Record state as though the Desk already knew it.

---

# 10. Identity may require temporal qualification

Not every apparent continuity is identity.

Renaming, succession, ownership, affiliation, control, membership, and similarity are different relationships and must not be collapsed into identity merely to simplify traversal.

Examples:

- a domain can transfer from Company A to Company B without becoming identical to either company;
- an organization can rename while remaining one Entity;
- a program can be replaced by a successor program that is related but not identical.

An identity Decision may carry temporal qualification where reality requires it, but not every resolution should be forced into a time range.

Do not solve a temporal relationship problem by abusing Entity merge.

---

# 11. Preferred display label

An Entity needs a useful human/LLM-facing label, but the label is not proof of identity.

Names and aliases remain source-presented Observations.

The current Entity projection may select a preferred display label from governed information:

```text
Entity E17
preferred label: Robert J. Smith
observed names:
  - Bob Smith
  - R. J. Smith
  - @rjsmith
```

Changing the preferred label does not create a new Entity and does not rewrite evidence.

The physical selection/governance rule for the preferred label remains open.

---

# 12. Rejected identity work is durable memory

Rejected candidates remain queryable with their Basis, Decision, rationale, and historical evidence context.

Example:

```text
2027 Notice: "R. Smith" may be E17
2027 Decision: rejected
2031 new evidence: identity question reappears
```

The 2031 work may create a new Notice because the evidence set changed. It must not erase the 2027 rejection.

The system should be able to answer:

> **Have we already considered this identity match, what did we decide, and what evidence existed then?**

This prevents repeated rediscovery of old dead ends and makes changed reasoning visible.

---

# 13. Resolution binds narrowly

Resolving one source-local occurrence must not silently resolve every similar string in the same source or corpus.

Observation structure therefore needs stable addressable identity occurrences/slots inside the Observation when more than one independently resolvable identity-bearing occurrence exists. These are subordinate addressable parts of an Observation, not a new top-level `Mention` foundation noun.

The occurrence/slot must preserve enough identity to target the exact source-local presentation that was reviewed, including its evidence-local address and wording/context as required by the Observation contract.

If an Observation contains only one identity-bearing subject, the Observation itself may be sufficient as the target. If it contains multiple independently resolvable subjects/occurrences, the Decision targets the stable subordinate occurrence rather than the whole Observation.

Example:

```text
"Robert Smith joined Acme..."
...
"Smith said..."
```

The first occurrence may support an identity Decision while the second remains unresolved.

Identity resolution binds to the smallest stable addressable Observation subject/occurrence that supports the Decision.

Do not globally substitute text tokens or infer that every same-name occurrence denotes the same Entity without a separately supportable candidate path.

---

# 14. Correction dependency discovery

A bad resolution may have influenced later governed work.

If Decision `D1` joined `E17` and `E42`, later Claims, Notices, Angles, Rendition Units, or Publications may have depended on that resolution.

When `D1` is superseded, do **not** silently rewrite those governed objects.

Instead the provenance system must be able to identify potentially affected dependents:

```text
identity Decision D1
      ↓ reverse provenance
Claims / Notices / Rendition Units / Publications
```

Rebuildable projections may recompute automatically under their own contracts. Governed semantic state requires explicit review/correction lineage.

---

# 15. LLM Entity read shape

The generic LLM read-envelope, pagination, expansion-budget, and available-action contract is owned by `CONTRACT-06-LLM-NATIVE-RECORD-SURFACE.md`.

Identity contributes object-specific requirements to that shared envelope: a stable Entity ID, preferred display label, current resolution/cluster summary, bounded observed names/identifiers, temporal/identity warnings, and discoverable identity Decisions/candidates. Do not create a second Entity-specific read protocol here.

---

# 16. Worked proof

1. Capture A yields Observation `O1`: text presents `R. Smith` in a role.
2. No Entity is assigned automatically.
3. Notice `N1(kind=identity_candidate)` proposes `O1 → E17` with Basis.
4. Human Decision `D1` rejects the candidate.
5. `N1` and `D1` remain queryable.
6. Later evidence produces Notice `N2` proposing `O1 → E42`.
7. Human Decision `D2` accepts that resolution.
8. Current reads resolve the occurrence through E42 while old evidence/Observation IDs remain unchanged.
9. Separate accepted Decisions later make `E42` and `E99` members of one current resolution cluster.
10. The projection may expose the cluster transitively without inventing a new human Decision.
11. A Publication uses a Claim whose reasoning depends on that identity resolution.
12. New evidence later shows `E42` and `E99` were different people.
13. Human Decision `D9` supersedes the relevant prior identity Decision.
14. Current resolution projection splits/recomputes.
15. As-of queries still reconstruct the earlier accepted cluster.
16. Reverse provenance identifies the dependent Claim/Publications for human review.
17. No Observation, evidence binding, old Entity ID, prior Decision, or Publication is destructively rewritten.

If the final physical design cannot perform this proof, the Identity contract has failed.

---

# 17. Open before ADR/schema promotion

1. Physical Entity identity row and internal/public identifier strategy.
2. Physical representation of same-identity Decision edges and current cluster projection.
3. Exact supersession model for identity Decisions.
4. Exact stable subordinate Observation-occurrence/slot representation and addressing rules for identity targets.
5. Preferred display-label selection/governance.
6. Identifier Observation shape and whether any identifier deserves a dedicated typed structure.
7. Temporal qualification representation for identity decisions when needed.
8. Current vs as-of Entity read contract.
9. Reverse provenance representation for identity-dependent governed objects.
10. Rules preventing Entity cluster cycles/invalid combinations while preserving reversibility.
11. Whether Entity belongs in slice 1 or first appears in the first slice that actually requires identity resolution.
12. LLM candidate-identity proposal/refusal/idempotency command contract.

---

# 18. Rejected shortcuts

- automatic authoritative merge from deterministic identifiers;
- `IdentityCandidate` as a separate parallel candidate system;
- first-class `Mention` before a concrete scenario proves it necessary;
- bulk FK rewrite on merge;
- deletion/mutation of old identity Decisions on unmerge;
- dead/invalid old Entity IDs after resolution;
- Case-local identity truth for convenience;
- back-projecting later identity knowledge into historical as-of Record state;
- treating ownership, succession, affiliation, similarity, or renaming as identity by default;
- resolving every same-name occurrence because one occurrence was resolved;
- model confidence or embedding similarity as identity authority;
- silently rewriting governed Claims/Publications after an identity correction.

---

# 19. Contract test

The Identity foundation is good enough only if all five are mechanically supportable:

> **The Desk can represent an identity possibility without resolving it.**

> **The human can resolve identity without rewriting the evidence that motivated the decision.**

> **A wrong resolution can later be reversed without losing what the Desk believed at the time.**

> **Old Entity IDs and prior rejected candidates remain useful historical memory.**

> **When an identity correction matters downstream, the Desk can find what depended on it.**
