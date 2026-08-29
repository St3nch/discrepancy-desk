# Claude Foundation Review — Steward Reconciliation

**Status:** NON-AUTHORITATIVE DESIGN REVIEW

**Reviewed target:** `e27d5b6e7a0981550761715078d4f831c33b3f23`

**Reviewer:** Claude Code, read-only, project-local `domain-modeling` skill

**Steward reconciliation baseline:** `2911370eb202bc19c100d833a8ae992dc07f1b0f`

**Purpose:** Preserve the independent Claude review as working input, record the Project Steward's disposition of D1–D24, and identify the decisions that must be resolved before schema/migration promotion. This document is not project authority and does not itself accept any semantic change.

> **Review verdict accepted:** Contracts 01–06 are coherent enough for worked schema design, but not ready for `0001_initial`.

The review passed the first Pocock-skill calibration goal: it found substantive reversible-identity and workflow defects without requiring a re-foundation or adding noun sprawl.

---

# 1. Disposition summary

| Finding | Disposition | Steward note |
|---|---|---|
| D1 human Decision authentication | ACCEPT | Authority requires an unforgeable human-only channel, not an actor label. |
| D2 as-of admission ordering | ACCEPT WITH CORRECTION | Wall clocks are insufficient, but an ordinary PostgreSQL sequence is also not commit-ordered. Physical design must prove committed-visibility ordering. |
| D3 version pinning vs stale refusal | ACCEPT | Split reference binding from state-precondition binding. |
| D4 Claim binding granularity | ACCEPT | Define one canonical historical Claim binding that separates content version from operative posture Decision. |
| D5 identity split/distinctness | ACCEPT WITH CORRECTION | A distinctness/split semantic is needed, but a negative edge cannot blindly override contradictory positive paths. Conflicting Decision sets must be resolved or surfaced explicitly. |
| D6 identity target granularity | ACCEPT WITH CORRECTION | Preserve no-top-level-`Mention`; require a stable addressable identity slot/occurrence inside Observation structure. |
| D7 automatic derived-state dependency capture | ACCEPT | Machine-captured operative dependencies are distinct from human-authored review Basis and are required for reverse provenance. |
| D8 Notice contract missing | ACCEPT | Notice is load-bearing and needs its own contract before schema if it remains slice-1/admission-facing. |
| D9 Run contract missing | ACCEPT | Run is authorization-bearing and needs a contract plus explicit mode/capability rules. |
| D10 Rendition approval/bindings | ACCEPT, DEFER TO PUBLICATION GATE | Exact Unit bindings must be approval-bound before first Publication; not required for an evidence-only initial slice. |
| D11 direct Excerpt → Claim | MODIFY | Do not delete automatically because Product previously accepted a narrow direct path. Restrict it to a worked, explicitly named Claim shape where the proposition is material/content presence; otherwise require Observation. |
| D12 append-only enforcement | ACCEPT WITH MECHANISM CAUTION | Governed append-only state must be enforced below agent/application convention using DB roles/privileges and constraints/triggers where appropriate. Not every table is append-only. ADR candidate. |
| D13 destruction/tombstone | ACCEPT | Legal/privacy destruction must be distinguishable from missing/corrupt payload and preserve non-content audit identity. Resolve before valuable evidence accumulates. |
| D14 untrusted content + sensitivity | ACCEPT, SPLIT | Untrusted-content marking is immediate LLM-envelope doctrine. Sensitivity/handling classification needs a dedicated access/read design before sensitive internal material is admitted. |
| D15 Observation shape | ACCEPT | Observation is a hinge noun and its structured content/identity-slot model must be settled jointly with Claim proposition shape. |
| D16 clock vocabulary drift | ACCEPT | Freeze canonical semantic clock names before schema; column names remain a later physical decision. |
| D17 idempotency | ACCEPT | Idempotency is request identity only; reused key with changed canonical payload is a conflict. Independent semantic proposals are not silently deduplicated. |
| D18 duplicated open registers | ACCEPT | Consolidate into one foundation open-item register with owner/status and links back to contracts. |
| D19 duplicate Entity read envelope | ACCEPT — FIXED | Contract 03 now delegates generic envelope ownership to Contract 06. |
| D20 skill adaptation contradictions | ACCEPT — FIXED | `to-spec`, `to-tickets`, and `code-review` no longer contain live tracker/triage instructions that contradict Desk mode. |
| D21 Steward authority laundering | ACCEPT — FIXED | Steward reconciliation now yields proposed authority changes; CHAZ explicitly accepts promotion. |
| D22 Contract 06 Markdown separators | ACCEPT | Cosmetic rendering defect; fix separately without semantic change. |
| D23 chronology detector target | ACCEPT | Foundation proof should pin first deterministic chronology conflict to source-local Observations; Claim-level conflict is a later/higher detector concern. |
| D24 relationship gating asymmetry | ACCEPT WITH CLARIFICATION | Source-stated relationship Claims may promote from Observations; inferred relationship candidates pass through Notice before Claim promotion. |

---

# 2. Blocking semantic corrections

## D1 — human authority channel

An actor field containing `CHAZ` is evidence of a claimed actor, not authentication.

Required semantic rule:

> **A human Decision is accepted only through an authenticated human-authority channel that no model Run capability can present or assume.**

Physical design should separate the service/database capability used for human-authority Decisions from every capability available to model Runs, and preserve the authenticated principal/channel in audit provenance.

Do not require the human to hold raw database credentials. The important boundary is that the model cannot invoke or impersonate the human-authority operation.

## D2 — Record admission ordering

`as_of` must reconstruct the state that had actually become part of the governed Record by the requested historical point.

Wall-clock timestamps cannot prove this ordering. PostgreSQL transaction timestamps are not commit-order clocks.

The review suggested a commit-ordered sequence as one possibility. **An ordinary `nextval()` sequence is not sufficient:** allocation order can differ from commit order when transactions overlap.

Required physical proof:

- system-assigned;
- immutable/non-backdatable;
- ordered consistently with governed committed visibility;
- deterministic for historical reconstruction;
- distinct from human-supplied `decision time`, source time, or world time.

Possible mechanisms must be evaluated in schema design rather than named prematurely. A serialized admission ledger/lock is one candidate; the contract requires the property, not that implementation.

## D3 — two target-binding modes

The contracts need two explicit semantics:

1. **Reference binding:** a new durable object intentionally cites the exact historical target/version it inspected. Later target movement does not silently retarget the reference and does not by itself invalidate creation.
2. **State-precondition binding:** an operation intends to change or rely on the target's current governed state. If current state changed after inspection, fail closed as stale.

Every mutation-capable operation declares the applicable mode. Missing declaration fails closed.

## D4 — canonical Claim binding

Stop using `Claim/version/posture` and `version/state` as slash-vocabulary.

A historical/public binding must distinguish at least:

- stable Claim identity;
- exact Claim proposition/content version;
- exact operative posture-determining Decision or Decision set relevant to the binding.

This is a semantic tuple, not necessarily a new top-level noun.

## D5 — identity split and distinctness

The triangle counterexample is valid:

```text
E17 = E42
E42 = E99
E17 = E99
```

Superseding only one positive equality Decision does not split the connected component.

The model therefore needs authoritative **distinctness/split semantics** in the existing Decision primitive.

However, a negative edge cannot simply be declared to "cut" a cluster while contradictory positive paths remain. Same-identity is an equivalence relation. The current Decision set must not silently encode both `A = B` and `A != B` through transitive paths.

Required behavior:

- distinctness is authoritative and supersedable;
- current projection detects contradictory positive/distinctness constraints;
- a split action must identify/supersede the conflicting positive Decisions or otherwise leave the cluster explicitly unresolved/conflicted until the human resolves the set;
- no projection may hide the contradiction by choosing an arbitrary partition.

## D6 — identity target slot

The no-first-class-`Mention` decision stands unless execution proves otherwise.

But an Observation must expose stable addressable identity-bearing slots/occurrences when more than one identity reference can exist inside the Observation.

This should be designed with the Observation shape, not smuggled in later as an unnamed requirement.

## D7 — operative derived-state dependencies

Human review Basis alone cannot guarantee reverse provenance.

When a durable governed operation consumes derived state, the system must automatically preserve the durable inputs that made that derived state operative.

Examples:

- identity cluster membership → exact operative identity Decisions;
- current Claim posture → exact posture Decision;
- preferred Entity label → exact governed selection/input state where consequential.

Call this machine-captured operational dependency/provenance in the physical model; do not confuse it with human-authored rationale.

---

# 3. Missing contracts before first migration

## Observation / proposition shape

Observation is already a slice-1 hinge and cannot remain merely "structured statement".

Resolve jointly:

- canonical Observation content representation;
- how one Observation addresses subject/object/identity-bearing slots;
- relationship to exact Excerpt/Locator material;
- promotion/mapping to Claim proposition structure;
- temporal interpretations attached to or derived from Observation;
- whether one Observation may contain multiple independently resolvable identity slots.

This should be the next foundation contract because Notice and identity targeting depend on it.

## Notice

Notice needs an explicit lifecycle before schema if it remains slice-1:

- identity/dedup key semantics;
- deterministic re-fire suppression;
- dismissed/deferred/promoted dispositions;
- re-raise conditions when evidence changes;
- Basis and counterevidence;
- which dispositions are human-only;
- no automatic promotion to Claim truth or publication truth.

## Run

Run needs an authorization contract:

- durable producer/run identity;
- parent/child lineage;
- mode/voice declaration;
- mode-to-operation matrix;
- child authority cannot exceed the parent's capability ceiling;
- mode changes use a new governed Run, not prompt mutation;
- editorial/Quinton Runs cannot regain research-write authority through child-Run escalation;
- read/write audit requirements, especially for sensitive material.

---

# 4. Other accepted corrections

## D10 — approval binds Rendition Units and bindings

Before first Publication, approval must cover exact Rendition content/version **and** the exact unit-level Claim/evidence binding set reviewed. Changing either invalidates the approval.

## D11 — direct Excerpt support

Keep only as a narrow exception with a worked example where the Claim proposition is itself exact material/content presence. Ordinary factual Claims still pass through Observation.

## D12 — append-only enforcement

Application convention is not enough. Governed append-only tables should deny ordinary UPDATE/DELETE to application/model roles and use database constraints/triggers where required. Rebuildable projections and mutable operational tables are not automatically subject to this rule.

Create an ADR before schema because this is hard to reverse and affects operational remediation.

## D13 — evidence destruction/tombstone

Governed legal/privacy destruction must preserve enough non-content identity to distinguish intentional destruction from missing/corrupt data. Locator resolution must fail loudly with the destruction reason/class and restore checks must distinguish tombstoned payloads from accidental loss.

## D14 — hostile content and sensitivity

Every evidence-derived payload exposed to a model remains structurally untrusted data. No captured page/PDF/transcript text becomes instruction because it appears in a read envelope.

Sensitivity/handling classification is a separate access concern and should be resolved before admitting confidential-source, embargoed, private-person, or similarly restricted material.

## D16 — canonical semantic clocks

Proposed canonical vocabulary for Product confirmation:

1. **world time** — when something occurred/was effective in the world;
2. **source-presented time** — time language/chronology the source itself presents;
3. **capture time** — when the Desk acquired the material;
4. **Record admission time/order** — when governed state became part of the Record;
5. **decision time** — when the human Decision was made/declared;
6. **publication time** — when a Publication occurred.

Exact column names are not settled by these semantic labels.

## D17 — idempotency

Idempotency operates on request identity, not semantic similarity.

Required rules:

- key is scoped to an operation/caller execution context according to the operation contract;
- canonical request hash is retained with the key;
- same key + same canonical request → same logical result;
- same key + different canonical request → explicit conflict refusal;
- independent Runs proposing equivalent propositions are not silently collapsed by idempotency;
- semantic equivalence/dedup remains separate governed reasoning.

---

# 5. Detector and relationship clarifications

## D23 — chronology detector

For the Foundation Model worked proof, deterministic chronology conflict is source-local first:

```text
O1 + O2 → Notice(chronology_conflict)
```

Claim-level contradiction detection may exist later, but should not make the first deterministic detector depend on prior Claim promotion.

## D24 — relationship path

Distinguish two cases:

```text
source explicitly states relationship
Observation → Claim(shape=relationship)
```

versus:

```text
Desk/model infers possible relationship not directly stated
Observation(s) / Claims → Notice(relationship_candidate) → later Claim proposal if warranted
```

This preserves the general Observation→Claim path without allowing inferred adjacency to masquerade as source-stated fact.

---

# 6. Physical schema probes required before `0001_initial`

Do not write a migration yet. Use worked schema sketches/queries to force decisions for:

1. human-authority operation/DB capability separation;
2. committed Record-admission ordering;
3. Claim content-version + operative-posture binding;
4. Observation structure and identity slots;
5. typed/default-deny Basis relation matrix;
6. reverse provenance from identity Decision to affected governed/public objects;
7. identity positive/distinctness conflict and split behavior;
8. current versus historical Claim posture query;
9. typed provenance implementation: constrained shared spine versus typed/exclusive-arc tables;
10. JSONB boundary: never use JSONB for core references, posture, clocks, Decision authority, or provenance relation kinds;
11. Artifact surrogate identity plus `(hash_algorithm, digest)` uniqueness rather than hash-as-global-PK;
12. slice-1 Locator anchor kinds and Unicode offset/normalization convention.

---

# 7. Workflow calibration result

The adapted Pocock/VedaOps method passed its first calibration.

Claude found material issues in the exact area selected for calibration:

- D5 exposed an unsound transitive identity split;
- D6 exposed an unnamed addressable-occurrence requirement;
- D20 exposed project-skill header/body contradictions.

The correct response is not to adopt Claude's text wholesale. The Steward verifies the premises, preserves settled Product direction, tightens mechanisms where the review overreaches, and brings genuine Product choices back to CHAZ before promotion.

> **Independent agent review is evidence for design. It is not design authority.**
