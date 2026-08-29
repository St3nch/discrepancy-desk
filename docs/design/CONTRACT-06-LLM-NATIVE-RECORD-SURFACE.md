# Foundation Contract 06 — LLM-Native Record Surface

**Status:** NON-AUTHORITATIVE DESIGN DRAFT

**Depends on:** `FOUNDATION-MODEL-V2.md`, `CONTRACT-01-EVIDENCE.md`, `CONTRACT-02-CLAIM-DECISION.md`, `CONTRACT-03-IDENTITY.md`, `CONTRACT-04-BASIS-PROVENANCE.md`, `CONTRACT-05-TEMPORAL-AS-OF.md`

**Purpose:** Define the governed machine interface through which production LLMs read, traverse, propose, and draft against the Record without arbitrary database authority or human-only Decision power.

> **The model gets doors, not the master key.**

---

# 1. LLM-native, not LLM-owned

The structured Record is intended to be directly useful to production LLMs over long research and editorial Runs. That does not make the model authoritative over the Record.

```text
LLM
 ↓
governed domain operations
 ↓
validation + authorization + provenance + concurrency checks
 ↓
PostgreSQL / Vault-backed Record
```

Production LLMs do **not** receive arbitrary SQL, unrestricted table writes, database credentials, or generic object mutation.

The Record is human-authoritative and LLM-native.

---

# 2. Small stable read surface

Prefer a small stable resource vocabulary with bounded envelopes and explicit traversal over a bespoke tool for every relationship.

Conceptually:

```text
read Entity E17
  ↓
bounded envelope
  ↓
explicit legal expansions / traversals
```

The exact transport grammar remains open.

A read envelope should expose enough context to prevent confusion about current versus historical Record state, world-time filtering, or stale versions. It may conceptually include:

- stable object ID and type;
- exact version/state identity where applicable;
- Record-view time semantics;
- world-time filters or qualification when requested;
- epistemic/posture summary;
- compact provenance summary;
- warnings/limitations;
- bounded links;
- available expansions/actions;
- pagination cursor when needed.

Example field names are not schema decisions. Temporal perspective must never be implicit.

---

# 3. Bounded reads and expansion budgets

Default reads must be useful without becoming context dumps.

For an Entity, a default envelope may expose a preferred display label, current resolution summary, bounded observed names/identifiers, warnings, counts, compact provenance, and available expansions.

The model walks deliberately:

```text
expand names
expand identifiers
expand identity decisions
expand candidate notices
expand claims
expand cases
expand evidence
```

There must be no accidental `expand=everything` path capable of returning unbounded Record state.

Pagination and expansion limits are part of the governed interface.

A Claim read should expose enough provenance by default that the model does not have to guess whether support, contradiction, or a current human Decision exists. Full Basis traversal remains an explicit expansion.

---

# 4. Writes are semantic commands

Mutation-capable LLM operations declare the semantic action being requested.

Illustrative commands include:

```text
propose_observation
propose_claim
propose_identity_match
propose_notice
bind_evidence
open_question
submit_rendition
```

Names are provisional.

Reject generic escape hatches such as `write_record(type, json)`, `update_any_object(...)`, or `execute_sql(...)`.

Each operation validates object-specific invariants, allowed references, provenance, caller role, Run mode, exact target state, and required preconditions.

---

# 5. Human-only authority has no LLM write path

Human Decisions remain legally unreachable from production LLM mutation authority.

Examples include:

- Claim posture Decisions;
- authoritative identity resolution;
- human-only Notice disposition;
- Rendition approval;
- Publication authorization;
- correction/takedown/safety Decisions;
- source-independence Decisions where doctrine requires human judgment.

An LLM may read requirements and prepare proposals or review material. It cannot invoke the authoritative Decision path.

This boundary must exist in the operation/authorization layer, not merely in prompts.

No credential, capability, session token, database role, or delegated authority available to a model Run may be sufficient to invoke the human-Decision path. Human actor labels are metadata, not authorization.

The human-only channel/capability must be independently authenticated and recorded with the resulting Decision under the Claim/Decision contract.

---

# 6. Producer provenance is distinct from human authority

Machine-produced proposals preserve producer provenance separately from later human authority.

```text
proposal produced by Claude Run R7
Decision made by CHAZ
```

Do not overload one actor field so model production can be mistaken for human Decision authority.

Model/vendor identity may be useful provenance. It never creates epistemic authority.

The same governed operation may be performed by OpenAI, Claude, Grok, a local model, or another approved worker. Authority comes from the operation contract, caller capability, Run mode, accepted project policy, and human Decision where required.

> **The method belongs to the project, not the model vendor.**

---

# 7. Run identity and mode participate in authorization

Every governed operation should be attributable to a durable Run or equivalent execution context.

A Run declares one operational mode/voice contract for its governed work.

Likely modes include, without freezing names:

- neutral research;
- skeptical / Devil's Advocate review;
- editorial / Quinton;
- implementation/admin modes where later execution requires them.

Run mode affects which operations are legal. It does not alter evidence truth.

A Quinton/editorial Run has no legal write path into authoritative Evidence state, Observation admission/meaning, Entity resolution, Claim posture, human-only Notice disposition, or Decisions. It may draft Renditions from governed Record material.

A governed Run does not silently switch from neutral research to editorial voice and then back into evidence extraction while retaining the same write permissions. If work needs another mode, create a new separately authorized Run or an explicit governed child Run.

A child Run's operation/capability authority is always a subset of its parent's authority ceiling. Child creation cannot be used to regain an operation the parent was forbidden to invoke.

If work requires broader authority than the parent Run possesses, that broader authority requires a separately authorized Run outside the parent escalation path.

---

# 8. Idempotent, replay-safe mutations

Every mutation-capable operation supports a governed idempotency identity appropriate to its semantics.

If a response is lost after a committed `propose_claim` and the model retries, the retry must not create duplicate semantic state.

Return the same accepted logical result or an explicit conflict/refusal.

Do not implement idempotency through weak textual deduplication that could merge distinct propositions or evidence.

---

# 9. Stale-target writes fail closed

A model may read an object, reason for some time, and then attempt a mutation after the target changed.

Reads must expose enough version/state identity for writes to bind to the exact inspected state where the operation requires it.

If the target is stale, refuse rather than silently rebasing intent onto newer state.

Conceptually:

```text
refused
reason = stale_target
required_next_step = reread_target
```

This protects concurrent model work, human/model races, and ordinary retries.

---

# 10. Structured refusals and legal next actions

Failure/refusal is part of the machine contract.

Illustrative refusal reasons include:

- evidence not captured;
- target/version missing;
- stale target;
- unauthorized operation;
- forbidden Run mode;
- human Decision required;
- invalid provenance relation;
- duplicate/idempotent request;
- invariant violation;
- expansion/page limit reached.

Where safe, expose a bounded legal next step.

A resource envelope may also advertise legal next actions or expansions for the current caller/Run. Human-only actions must not appear as executable model actions merely because they exist conceptually.

The server remains authoritative about legality. The model does not invent its own workflow.

---

# 11. Current and historical reads are explicit

The model must distinguish:

```text
What does the Desk currently believe?
```

from:

```text
What did the Desk know/decide as of date X?
```

and from:

```text
What current Record material concerns world-time interval Y?
```

These are distinct semantic questions even if one transport later represents them through parameters.

Later knowledge may change current reconstruction without contaminating earlier as-of views.

---

# 12. Nothing durable depends only on hidden model context

If a durable Claim, Notice, Decision review package, Rendition Unit, or other governed object depends on model reasoning, it must walk back to addressable Record dependencies under the Basis/Provenance contract.

The model's private conversational context is not durable evidence.

Model analysis/prose may be preserved as producer provenance when useful, but it cannot become the sole support for durable epistemic state.

> **If the model cannot walk the result back toward addressable Record material, it is not a valid durable Record dependency.**

---

# 13. Worked proof

1. Neutral research Run `R1` reads Entity `E17` in current Record view.
2. The bounded envelope exposes stable identity, resolution summary, warnings, compact provenance, and legal expansions.
3. `R1` expands identity Decisions and Claims using bounded pagination.
4. `R1` reads Claim `C4` at exact version/state `V3` and sees supporting and contradicting Basis.
5. `R1` proposes Claim `C9` derived from governed Claims `C4` and `C8` with explicit Basis.
6. The request carries Run/producer provenance, idempotency identity, and exact target-state expectations.
7. A retry returns the same logical proposal rather than creating another Claim.
8. Another actor changes `C4` before a later mutation from `R1`.
9. The later mutation is refused as stale; `R1` must reread.
10. `R1` cannot invoke a human Claim-confirmation Decision.
11. CHAZ later makes Decision `D20` through the human-authority path.
12. Producer provenance still shows the proposal originated in `R1`; Decision provenance shows the human actor separately.
13. Quinton editorial Run `R2` may draft a Rendition from governed Record material.
14. `R2` cannot mutate Entity resolution, Claim posture, Evidence, or human Decision state.
15. An as-of query reconstructs the Record before `D20` without back-projecting that Decision.

If the final operation surface cannot perform this proof without arbitrary SQL, generic JSON writes, prompt-only authority boundaries, or unbounded context dumps, this contract has failed.

---

# 14. Open before schema/API promotion

1. Exact resource/read operation grammar.
2. Exact mutation command vocabulary and request envelopes.
3. Read-envelope field names and version/state identity representation.
4. Pagination/cursor model and maximum expansion budgets.
5. Exact Record-as-of and world-time query grammar.
6. Run semantics, parent/child lineage, and mode vocabulary.
7. Capability/role model for model workers versus human authority paths.
8. Idempotency identity, retention, conflict semantics, and replay window.
9. Stale-target conflict semantics by object type.
10. Structured refusal vocabulary and next-action policy.
11. Available-actions generation without authorization leakage.
12. Model/vendor/build identity retained in producer provenance.
13. Internal/public identifier strategy.
14. Default provenance-summary depth by object type.
15. Audit requirements for model reads versus writes.
16. Whether safe bounded bulk traversal is needed for research Runs.

---

# 15. Rejected shortcuts

- arbitrary SQL for production LLMs;
- direct database credentials for model workers;
- generic JSON/object mutation;
- LLM-accessible human Decision authority;
- model/vendor brand as truth authority;
- Quinton/editorial mode writing authoritative research state;
- silent Run-mode switching;
- unbounded `expand=everything` reads;
- stale writes silently rebased;
- duplicate semantic writes after retry;
- prose-only refusal semantics;
- model prose as sole evidentiary Basis;
- durable objects depending only on hidden conversational context;
- default reads hiding contradiction/posture/provenance;
- a sprawling tool per relationship when bounded resource traversal can express the same capability.

---

# 16. Contract test

The LLM-native Record surface is good enough only if all six are mechanically supportable:

> **A production model can traverse the Record deeply without arbitrary SQL or unbounded dumps.**

> **A model can propose durable work through narrow semantic commands without gaining human Decision authority.**

> **Every mutation can fail closed on stale state, illegal mode, missing provenance, or replay ambiguity.**

> **Producer/model provenance remains distinct from human authority.**

> **Current and historical Record views are explicit to the model rather than hidden context.**

> **The same governed method can serve Claude, Grok, OpenAI, or another approved model without changing who holds authority.**
