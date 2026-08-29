# Foundation Contract 08 — Notice

**Status:** NON-AUTHORITATIVE DESIGN DRAFT

**Depends on:** `FOUNDATION-MODEL-V2.md`, `CONTRACT-01-EVIDENCE.md`, `CONTRACT-02-CLAIM-DECISION.md`, `CONTRACT-04-BASIS-PROVENANCE.md`, `CONTRACT-06-LLM-NATIVE-RECORD-SURFACE.md`, `CONTRACT-07-OBSERVATION-PROPOSITION-SHAPE.md`

**Purpose:** Define the durable candidate-intelligence envelope used to surface potentially meaningful Record patterns without creating a second truth system, model-governed disposition path, or suspicion score.

> **Look here. Not: believe this.**

---

# 1. Notice contract

A **Notice** is a durable, non-authoritative candidate insight about Record material that may deserve human attention or further governed work.

A Notice is not:

- a Claim;
- a Decision;
- an alert notification;
- a task;
- a confidence or suspicion score.

Conceptually:

```text
something noticed
      ↓
Notice
      ↓
human review / more research / Claim work / identity work
```

The Notice says that something may be worth examining. It does not say the implied proposition is true.

---

# 2. One candidate system

Use one Notice noun for candidate intelligence.

Examples may include:

- `identity_candidate`;
- chronology conflict;
- relationship candidate;
- source-dependency candidate;
- unusual recurrence;
- missing-expected-source candidate;
- later candidate kinds proven by execution.

Do not create separate durable nouns merely because trigger mechanisms differ.

The final governed kind vocabulary remains intentionally small and open.

---

# 3. Stable candidate identity and recurrence

A detector or model firing repeatedly against the same operative material must not create an unbounded stream of duplicate Notices.

Candidate identity is conceptually based on the Notice kind, its semantic target, and the operative evidence/dependency set that caused the candidate to exist.

The same logical candidate against the same material should converge on the existing Notice or an idempotent recurrence/provenance record.

This is not semantic truth deduplication.

A materially changed Basis may justify a successor or re-raised Notice.

Weak textual similarity or model embedding similarity must never silently collapse different candidate work.

---

# 4. Dismissal is durable memory, not a permanent blacklist

A dismissed or rejected Notice remains queryable with the material and Decision that existed when it was dispositioned.

Example:

```text
2027 N1: R. Smith may be E17
D1: reject under Basis B1

2031 new filing B2 arrives
        ↓
N2: reconsideration candidate
links to N1 / D1
```

New materially relevant Basis may justify renewed candidate work.

The system must not silently resurrect N1 as though D1 never happened, and it must not suppress the question forever merely because an earlier candidate was rejected.

The successor/re-raise path preserves why the prior Notice was closed and what changed.

---

# 5. Notice disposition is human authority

Authoritative Notice disposition is a human Decision.

Examples include:

- dismiss;
- defer;
- request more research;
- promote to Open Question;
- initiate or accept Claim work;
- initiate identity review;
- conclude that no further action is warranted.

Models may recommend a disposition, gather Basis, or perform separately authorized proposal work.

They may not manufacture the human disposition itself.

Viewing, ranking, opening, or model discussion of a Notice changes no authoritative state.

---

# 6. Deterministic and interpretive triggers share one envelope

Deterministic and interpretive Notices use the same durable Notice concept but preserve different trigger provenance.

A deterministic trigger should preserve enough information to reproduce or audit the trigger, including conceptually:

- detector identity/version;
- exact input dependencies;
- rule or comparison performed;
- deterministic result.

An interpretive trigger should additionally preserve, where material:

- producing Run/model/rubric;
- explanation of the candidate;
- ordinary explanations;
- counterevidence;
- what the Notice does not establish.

Do not split these into `DeterministicNotice` and `InterpretiveNotice` nouns merely for implementation convenience.

---

# 7. Notice is not publication evidence

A Notice has no direct factual publication path.

Bad path:

```text
Notice → Rendition
```

Normal factual path:

```text
Notice
  ↓ research / proposal
Observation / Claim work
  ↓
Claim
  ↓
Decision
  ↓
Rendition Unit
```

A Publication may accurately discuss the Desk's own investigative process when that process statement is itself governed and appropriately bound. That does not convert the candidate insight into external-world evidence.

Raw Notice content must never become a second truth path around Claim and Decision.

---

# 8. Skeptical framing is part of interpretive candidate quality

Where interpretation is materially responsible for why something looks interesting, the Notice envelope must support skeptical context rather than storing only the suspicious-looking pattern.

Conceptually useful fields include:

```text
candidate observation
Basis
counterevidence
ordinary explanations
what this does not establish
```

Not every deterministic discrepancy requires prose-heavy review material.

But No Coincidences-style interpretive work must be capable of representing ordinary explanations and counterevidence at the same level as the candidate itself.

> **Crumbs are not conclusions.**

---

# 9. Priority is operational, not epistemic

Notice queue ordering or salience may exist for operator workload management.

Priority does not mean truth, suspicion, culpability, or confidence.

Potential operational inputs may eventually include:

- newness;
- consequence;
- unresolved publication impact;
- deterministic severity;
- human-specified Case priority.

Engagement, popularity, virality, or audience reaction must not increase epistemic authority or make a candidate more true.

If a priority model exists, its meaning must remain operational and explainable.

---

# 10. Shared Record Notice, Case-local attention

Authoritative Notice identity and disposition belong to the shared Record.

A Notice may be associated with multiple Cases:

```text
Notice N17
  ↙      ↓      ↘
Case A  Case B  Case C
```

Cases may assign different investigative relevance, salience, hypotheses, or editorial interest.

They do not fork Notice disposition into parallel Case-local truth.

> **Case is attention, not truth.**

---

# 11. Disposition does not equal proposition truth

Notice lifecycle state and Claim posture are different semantics.

Example:

```text
N1: chronology conflict exists
```

The Notice may be dispositioned because:

- one source contained a typo;
- two different events were conflated;
- a Claim was refined;
- further research produced no useful resolution;
- the discrepancy remains real but no further action is warranted.

None of those outcomes means a generic Notice state such as `resolved` can be interpreted as a true/false Claim posture.

Disposition records what happened to the candidate work.

Claim posture records what the human has decided about a proposition.

Never derive one automatically from the other.

---

# 12. Worked proof

1. Observation `O1` records Source A presenting 2005.
2. Observation `O2` records Source B presenting 2006.
3. Deterministic detector `T1` produces chronology-conflict Notice `N1` with exact inputs `O1/O2`.
4. Re-running `T1` against unchanged `O1/O2` does not create a duplicate Notice.
5. Human Decision `D1` defers `N1` pending stronger evidence.
6. Model Run `R4` may recommend follow-up work but cannot disposition `N1` itself.
7. Later Observation `O3` introduces materially new Basis.
8. The system may create or expose a successor/re-raised Notice `N2` linked to `N1/D1`, rather than erasing the prior disposition.
9. Interpretive review of `N2` preserves ordinary explanations and what the discrepancy does not establish.
10. Human Decision `D2` initiates precise Claim work.
11. Any factual publication path proceeds through the resulting Claim and its human-authority posture, never directly from `N1` or `N2`.
12. `N1`, `D1`, `N2`, and `D2` remain queryable institutional memory.

If the physical design cannot perform this proof without duplicate candidate spam, model-created disposition, or Notice-to-publication truth laundering, the Notice contract has failed.

---

# 13. Open before schema/API promotion

Canonical unresolved items are owned by `FOUNDATION-OPEN-ITEMS.md`, especially `FND-013`.

Remaining physical/design questions include:

- exact candidate identity and evidence-set fingerprint semantics;
- whether recurrence is modeled as Notice lineage, a recurrence record, or another narrow mechanism;
- exact re-raise materiality rules by Notice kind;
- minimal disposition vocabulary and typed Decision effects;
- Notice kind vocabulary and detector registration/versioning;
- queue/salience projection and suppression mechanics;
- allowed Notice Basis relation matrix;
- exact Case association semantics;
- whether Open Question deserves a separate foundation contract before its first write path exists.

---

# 14. Rejected shortcuts

- detector firing equals a new Notice every time;
- textual/embedding similarity as silent candidate deduplication authority;
- dismissal as permanent blacklist despite materially new Basis;
- silent resurrection that erases prior disposition;
- model-created authoritative Notice disposition;
- separate deterministic/interpretive Notice nouns without a proven semantic need;
- raw Notice as factual publication evidence;
- suspicion/confidence score masquerading as queue priority;
- engagement/popularity as epistemic priority;
- Case-local fork of Notice truth/disposition;
- Notice `resolved` interpreted as Claim `confirmed`;
- interpretive candidate stored without room for ordinary explanations/counterevidence.

---

# 15. Contract test

The Notice foundation is good enough only if all six are mechanically supportable:

> **Repeated detection of the same operative candidate does not spam durable state.**

> **A dismissed candidate remains memory but materially new Basis can reopen the question explicitly.**

> **Models can surface and analyze candidate work without gaining disposition authority.**

> **Deterministic and interpretive candidates share one envelope while preserving different provenance.**

> **Notice priority never becomes a truth or suspicion score.**

> **No factual Publication can bypass Claim/Decision authority through a Notice.**
