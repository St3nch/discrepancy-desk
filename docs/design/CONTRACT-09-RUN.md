# Foundation Contract 09 — Run

**Status:** NON-AUTHORITATIVE DESIGN DRAFT

**Depends on:** `FOUNDATION-MODEL-V2.md`, `CONTRACT-02-CLAIM-DECISION.md`, `CONTRACT-04-BASIS-PROVENANCE.md`, `CONTRACT-06-LLM-NATIVE-RECORD-SURFACE.md`, `CONTRACT-07-OBSERVATION-PROPOSITION-SHAPE.md`, `CONTRACT-08-NOTICE.md`

**Purpose:** Define the durable execution/provenance envelope for model-assisted work so mode, producer identity, capability ceilings, parent/child lineage, and Quinton isolation are enforceable rather than prompt convention.

> **A Run records how governed work was produced. It does not decide whether that work is true.**

---

# 1. Run contract

A **Run** is the durable execution/provenance envelope for one governed body of machine-assisted work under one declared mode and capability ceiling.

Conceptually, a Run may carry:

- durable Run identity;
- declared mode;
- producer/provider/model/build identity where available;
- rubric/prompt-policy/tool-surface versions where relevant;
- parent Run lineage where applicable;
- capability ceiling;
- lifecycle state;
- governed inputs/outputs or references to them;
- creation/start/completion provenance.

A Run is not an agent personality, a human actor, a Claim, a Decision, or an epistemic authority.

> **Producer provenance is not human authority.**

---

# 2. One mode per Run

A Run has one declared operational mode/voice contract for its governed lifetime.

It must not silently switch modes because the conversational prompt changes.

Bad path:

```text
research Run
   ↓ "make it spooky"
Quinton voice
   ↓ "now extract facts again"
research writes under same authority envelope
```

Required path:

```text
R1 research
   ↓ governed handoff / referenced Record outputs
R2 editorial
```

If work materially changes mode, create another Run.

---

# 3. Foundation mode vocabulary

The first semantic mode vocabulary is intentionally small:

1. **research** — neutral Record investigation, evidence-bound extraction, and proposal work;
2. **skeptical-review** — adversarial / Devil's Advocate analysis and counter-reading;
3. **editorial** — Quinton/Rendition work over governed Record material.

These are semantic mode names for the foundation drafts, not necessarily final API enum spellings.

Implementation/admin coding-agent activity is not automatically part of the production Record Run model. Admit an administrative/product-operations mode only if execution proves the product needs it.

---

# 4. Mode-to-operation capability matrix

The operation surface must enforce a mode→operation policy. Prompts do not substitute for it.

Foundation direction:

| Operation family | research | skeptical-review | editorial |
|---|---:|---:|---:|
| Read governed Record | yes | yes | yes, bounded by handling policy |
| Propose Observation | yes | no by default | no |
| Propose Claim | yes | yes, including explicit counter/inference Claims | no |
| Propose Notice | yes | yes | no |
| Open Question | yes | yes | no |
| Add research Basis/dependencies | yes | yes | no |
| Draft Rendition | no by default | no | yes |
| Human Decision | no | no | no |
| Authoritative Entity resolution | no | no | no |
| Claim posture mutation | no | no | no |
| Notice disposition | no | no | no |
| Arbitrary Evidence/Vault mutation | no | no | no |

Research may later receive narrow governed acquisition/capture operations under the Evidence contract. That does not grant arbitrary Vault authority.

Every concrete mutation command must map to an allowed operation family. An operation with no declared mode rule fails closed.

---

# 5. Skeptical review may produce durable proposals

Devil's Advocate work is not forced to remain ephemeral prose.

If skeptical review discovers a proposition such as:

```text
The apparent three-source corroboration may derive from one underlying filing.
```

it may propose a Claim or Notice when:

- the proposal is explicit as inference/candidate work;
- its Basis walks to governed Record material;
- counterevidence and ordinary explanations remain available;
- no posture or Decision authority is implied.

Skeptical mode does not gain epistemic authority merely because its purpose is criticism.

---

# 6. Child Runs cannot escalate authority

A child Run's capability ceiling is bounded by the intersection of:

```text
parent capability ceiling
∩ requested child-mode capabilities
∩ caller authorization
```

Never use the union.

Therefore a restricted editorial Run cannot spawn a research child and recover research write authority merely by naming the child `research`.

If broader authority is needed, create a separately authorized Run outside that restricted parent chain.

> **Run lineage may reduce authority. It cannot manufacture authority.**

---

# 7. Research may hand off to editorial as reduced authority

A research Run may create an editorial child or separately authorized editorial Run whose capabilities are a safe subset.

Useful pipeline:

```text
R1 research
   ↓ governed Record outputs / explicit references
R2 editorial / Quinton
   ↓
Rendition draft
```

The editorial Run may inherit provenance references and bounded context. It does not inherit research mutation authority merely because its parent possessed it.

This preserves:

> **Serious underneath. Entertaining on top.**

---

# 8. Producer/model identity is provenance, never authority

A Run should preserve enough machine identity to answer what produced governed work when the information is available and useful.

Examples may include:

- provider/model family;
- relevant model/build/version identity;
- rubric or policy version;
- tool/operation-surface version;
- parent Run;
- declared mode.

Those facts are provenance.

```text
Claude produced proposal X
```

and

```text
Grok produced proposal X
```

have the same authority status absent a separately governed project rule.

The model vendor never becomes a truth role.

---

# 9. Writes require Run provenance; read auditing is risk-based

Every durable model-produced proposal/write must identify the Run that produced it.

This includes at minimum model-produced:

- Observations;
- Claims;
- Notices;
- Open Questions;
- Basis/dependency proposals;
- Rendition drafts/versions.

Ordinary Record reads do not automatically become permanent semantic history. Logging every read forever is not a foundation requirement.

Read auditing is risk-based:

- sensitive/restricted material may require durable access audit under handling policy;
- ordinary reads may use bounded operational logs;
- durable semantic provenance records what influenced admitted durable work, not every transport request.

---

# 10. Run lifecycle does not rewrite produced objects

Run lifecycle is operational provenance.

Illustrative lifecycle states may include running, completed, failed, cancelled, or abandoned. Exact vocabulary remains open.

Changing Run lifecycle state does not delete or retract already admitted governed objects.

Example:

```text
R7 produces Notice N3
R7 later fails
```

`N3` remains durable with provenance showing that it came from `R7`. Its own disposition/lineage follows the Notice contract.

Likewise, cancelling a Run does not rewrite Claims, Observations, or Renditions that were already admitted before cancellation.

---

# 11. Quinton is editorial voice over the Record

Quinton/editorial voice may transform governed Record material into engaging Rendition language.

Example:

```text
Record Claim:
Company A acquired X in 2004.

Editorial Rendition:
"And that's where the filing cabinet starts making noises."
```

The editorial framing belongs to the Rendition layer.

It must not be copied back into neutral research state as though it were source-local or epistemic content.

Quinton/editorial mode has no legal write path into:

- Observation semantic content/admission;
- Claim canonical proposition content or posture;
- Entity resolution;
- Notice analysis/disposition;
- neutral preferred Entity labels;
- human Decision rationale represented as neutral Record material;
- Evidence/Vault authority.

> **Quinton is a voice over the Record, not a voice inside the Record.**

---

# 12. Human authority remains out of every model Run

No Run mode may invoke the human Decision authority channel defined by the Claim/Decision and LLM-surface contracts.

This remains true even when:

- CHAZ initiated the Run;
- the model acts inside CHAZ's interactive session;
- the model recommends exactly the Decision CHAZ later makes;
- a child Run was spawned by a human-started parent Run.

Human authority requires the independently authenticated human-only path. A Run capability cannot present or assume that credential/channel.

---

# 13. Worked proof

1. Research Run `R1` begins with a bounded research capability ceiling.
2. `R1` reads captured evidence and proposes Observation `O1`.
3. `O1` records producer provenance pointing to `R1`.
4. `R1` proposes Claim `C1` with Basis.
5. `R1` cannot confirm `C1`; human Decision authority is unreachable from the Run.
6. Skeptical Run `R2` reads `C1` and its counterevidence.
7. `R2` proposes Notice `N1` that apparent corroboration may share one source lineage.
8. `N1` remains candidate work; `R2` cannot disposition it.
9. Human review later makes an appropriate Decision through the human-only path.
10. Research Run `R1` creates reduced-authority editorial child `R3`.
11. `R3` can draft a Quinton Rendition from governed Claims but cannot propose Observations or mutate research state.
12. `R3` attempts to spawn child `R4(mode=research)`.
13. `R4` cannot gain research mutation capabilities because child authority is bounded by the parent ceiling.
14. If broader research work is needed, a separately authorized research Run is created.
15. `R3` later fails after producing a Rendition draft; the draft remains addressable with `R3` provenance.

If the final system cannot perform this proof without relying on prompt obedience, the Run contract has failed.

---

# 14. Open before schema/API promotion

Canonical unresolved items are owned by `FOUNDATION-OPEN-ITEMS.md`.

Run-specific physical/API work still includes:

- exact Run lifecycle vocabulary;
- physical capability-set representation;
- exact mode→command mapping as the command vocabulary settles;
- root/sibling/child authorization handshake;
- model/build/rubric identity retention fields;
- sensitive-read audit requirements and retention;
- relationship between Run completion and transaction/job orchestration;
- safe handoff/context-reference shape between research and editorial Runs.

Do not create duplicate differently worded foundation questions here when the register already owns them.

---

# 15. Rejected shortcuts

- mutable mode/persona inside one governed Run;
- child Run authority greater than the parent's ceiling;
- model/vendor identity as epistemic authority;
- Quinton/editorial writes into research objects;
- human Decision authority exposed to any Run mode;
- skeptical review forced to remain untraceable prose when a durable proposal is warranted;
- Run failure deleting previously admitted governed outputs;
- permanent logging of every ordinary read as semantic provenance by default;
- implementation/admin coding-agent activity silently sharing the production Record Run model;
- prompt-only mode restrictions without operation-layer enforcement.

---

# 16. Contract test

The Run foundation is good enough only if all six are mechanically supportable:

> **Every durable model-produced object can identify the Run and mode that produced it.**

> **A Run cannot silently change mode while retaining its prior authority.**

> **A child Run can lose authority but cannot gain authority beyond its parent ceiling.**

> **Skeptical review can produce explicit durable proposals without gaining Decision authority.**

> **Quinton can produce Renditions without any legal path back into neutral research truth state.**

> **Run lifecycle changes never erase already admitted governed history.**
