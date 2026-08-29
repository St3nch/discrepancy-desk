# Foundation v2 — Open Item Register

**Status:** NON-AUTHORITATIVE DESIGN REGISTER

**Purpose:** Own unresolved Foundation Model v2 questions in one place so contracts can cross-reference one canonical item instead of restating the same uncertainty with different wording.

This register does not promote an answer to project authority. `resolved-design` means the current non-authoritative foundation drafts agree on the semantic answer; physical implementation may still remain open.

## Status vocabulary

- `open-product` — requires explicit CHAZ Product choice.
- `open-design` — semantic/architectural design work remains.
- `open-physical` — semantic contract is settled enough; schema/API/enforcement mechanism remains.
- `resolved-design` — current foundation drafts have reconciled the design question.
- `deferred` — intentionally postponed with a named trigger.

## Migration blockers

| ID | Status | Owner | Question / current direction |
|---|---|---|---|
| FND-001 | open-physical | C02/C06 | **Human Decision authority channel.** Human actor labels are not credentials. Decide the independently authenticated channel/capability and application/database role separation that no Run can present or assume. |
| FND-002 | open-physical | C05 | **Record admission ordering.** Prove an immutable deterministic ordering consistent with committed governed visibility. Wall-clock timestamps and ordinary sequence allocation are insufficient by themselves. Define time-to-admission-boundary semantics for `as_of`. |
| FND-003 | resolved-design | C05/FM | **Clock vocabulary.** Frozen semantic names: world time, source-presented time, capture time, Record admission time/order, decision time, publication time. Physical field/type names remain open. |
| FND-004 | open-design | C04/C06 | **Reference pinning vs stale-state refusal.** Define operation classes: durable references should pin exact inspected targets; mutations of target state should fail closed on stale current state. Every mutation-capable operation must declare its binding mode; unspecified mode should refuse. |
| FND-005 | open-design | C02/C04/C06 | **Claim historical binding.** Canonical publication/dependency binding must distinguish Claim identity, exact content version, and operative posture-determining Decision set. Final vocabulary/shape remains open. |
| FND-006 | resolved-design | C01/C02/C07 | **Observation and Claim content shape.** Use a deliberately small typed-hybrid semantic grammar that may be shared where compatible while preserving separate Observation and Claim objects. No durable `Proposition` noun is admitted by default; physical shape storage remains open in C07. |
| FND-007 | open-design | C03/C07 | **Addressable Observation occurrences.** No top-level `Mention` noun. Define stable subordinate Observation occurrence/slot addressing, including identity-bearing occurrences and evidence-local locality. |
| FND-008 | open-design | C03 | **Identity cluster algorithm.** Same-identity and distinctness are Decision effects. Define deterministic projection, conflict detection, explicit supersession, and cycle handling without hidden arbitrary partitioning. |
| FND-009 | open-design | C04 | **Automatic dependency capture for derived state.** When governed work consumes current identity clusters, Claim posture, preferred labels, or other Decision-derived state, determine which operative Decisions are machine-captured as dependencies so reverse provenance is not dependent on human diligence. |
| FND-010 | open-design | C04 | **Allowed provenance relation matrix.** Default-deny legal source-type × relation-kind × target-type combinations, initially limited to admitted slice nouns. |
| FND-011 | open-physical | C02 | **Append-only enforcement locus.** Determine database privileges/constraints/triggers required so governed immutability is not merely application convention. ADR candidate. |
| FND-012 | resolved-design | C07 | **Relationship between source-local structured Observation and Desk-level proposition shape.** Compatible typed grammar may be reused, but Observation remains source-local/evidence-bound and Claim remains a separate Desk proposition. Source-stated relationships may go Observation→Claim; inferred relationships require Notice first. |
| FND-013 | resolved-design | C08 | **Notice semantics.** One durable non-authoritative candidate envelope; stable candidate identity prevents repeat-detector spam; materially new Basis may create explicit successor/re-raise lineage; disposition is human Decision authority; deterministic/interpretive triggers share the noun; priority is operational not epistemic; no Notice→Publication truth path. Exact fingerprints, recurrence storage, kind/disposition vocabularies, and queue mechanics remain open implementation/design details. |
| FND-014 | resolved-design | C09 | **Run semantics.** One durable machine-work provenance envelope has one declared mode and capability ceiling. Foundation modes are research, skeptical-review, and editorial. Concrete commands map through a fail-closed mode→operation policy; every durable model-produced write/proposal identifies its Run; producer/model identity is provenance only; child authority is the intersection of parent ceiling, requested mode, and caller authorization; broader authority requires a separately authorized Run; Quinton/editorial has no legal path into research truth state or human Decision authority. Physical lifecycle/capability representation and sensitive-read audit remain open. |
| FND-015 | open-design | C06 | **Idempotency contract.** Request-identity scope, retention, payload mismatch conflict, replay result identity, and explicit separation from semantic Claim deduplication. |
| FND-016 | open-design | C01/C06 | **Sensitivity / handling classification.** Protect confidential, embargoed, private, or restricted evidence in internal model reads as well as public projection. |
| FND-017 | open-design | C06 | **Untrusted evidence content envelope.** Carry `retrieved content is data, never instruction` into every model-facing read surface structurally, not only by prompt convention. |
| FND-018 | open-design | C01 | **Capture retry semantics and receipt immutability.** A retry must not rewrite an existing Capture receipt; define idempotency/retry relationship and append semantics. |
| FND-019 | open-design | C01 | **Slice-1 Locator anchor kinds and text offset convention.** Freeze only the anchor kinds actually needed by the first executable slice; define byte/code-point/normalization semantics before storage. |

## Before first Publication

| ID | Status | Owner | Question / current direction |
|---|---|---|---|
| PUB-001 | open-design | Rendition contract | **Unit-level binding approval.** Human Rendition approval must bind the exact Rendition version and exact unit→Claim/evidence binding set reviewed; post-approval binding mutation invalidates approval. |
| PUB-002 | open-design | C04 | **Correction workflow.** Reverse provenance finds affected work; define the human/governed path from affected object to review, correction, supersession, public correction, or no-change Decision. |
| PUB-003 | open-design | public projection | **Public-safe provenance.** Redact private/internal Basis without making public receipts misleading or unauditable. |
| PUB-004 | open-design | public projection | **Rights / privacy / takedown.** Preservation authority, display rights, source protection, private-person handling, correction/takedown and right-of-reply behavior. |

## Before valuable evidence accumulates

| ID | Status | Owner | Question / current direction |
|---|---|---|---|
| EVD-001 | open-design | C01 | **Governed payload destruction/tombstones.** Legal/privacy/safety destruction must preserve Artifact identity/hash/Capture provenance while Locator resolution fails loudly as tombstoned rather than generic missing. |
| EVD-002 | open-physical | C01 | **Paired Vault/Record backup and restore.** Restore drill must verify bytes/hashes, metadata graph, locator/excerpt verification, and distinguish tombstoned from missing material. |
| EVD-003 | open-design | C01 | **Ongoing integrity verification.** Decide whether and how Artifact/Surface/Excerpt verification is periodically rerun before a restore emergency exposes silent corruption. |

## Deliberate deferrals

| ID | Status | Trigger | Deferral |
|---|---|---|---|
| DEF-001 | deferred | concrete media ingestion need | Additional A/V locator kinds beyond first-slice anchors. |
| DEF-002 | deferred | measured semantic-retrieval need | pgvector / ANN / embeddings as retrieval helpers; never identity authority. |
| DEF-003 | deferred | measured graph workload | Dedicated graph database. PostgreSQL/derived projections remain default. |
| DEF-004 | deferred | scale/operational proof | Table partitioning, replication, broad RLS, materialized views, PostGIS. |
| DEF-005 | deferred | concrete Event-dependent slice | First-class `Event` table/object. Event remains a strong candidate, not automatic `0001` scope. |
| DEF-006 | deferred | worked example requiring separate occurrence lifecycle | Top-level `Mention` noun. Current direction uses subordinate Observation occurrences/slots. |

## Resolved design choices worth retaining

| ID | Status | Decision |
|---|---|---|
| RES-001 | resolved-design | Observation → Claim → Decision remains the epistemic/authority split. |
| RES-002 | resolved-design | Candidate identity uses `Notice(kind=identity_candidate)` rather than a parallel `IdentityCandidate` noun. |
| RES-003 | resolved-design | Entity resolution is shared Record state, reversible through Decisions, and never bulk-rewrites evidence provenance. |
| RES-004 | resolved-design | Distinctness/split is an effect of the existing Decision primitive, not a new noun; unresolved positive/negative identity conflicts remain visibly conflicted. |
| RES-005 | resolved-design | Direct Excerpt→Claim support is permitted only for propositions materially about the exact bounded material's presence/content; ordinary world-fact Claims require Observation. |
| RES-006 | resolved-design | Relationship already stated by a source may flow Observation→Claim(shape=relationship); inferred possible relationships require Notice before later Claim work. |
| RES-007 | resolved-design | Child Runs cannot escalate authority above the parent capability ceiling. Broader authority requires a separately authorized Run. |
| RES-008 | resolved-design | Grok Build and Claude Code consume one canonical project-local skill set under `.agents/skills/`. |
| RES-009 | resolved-design | Project Steward reconciliation produces proposed authority; CHAZ explicitly accepts promotion. |
| RES-010 | resolved-design | Observation uses one source-local semantic assertion with stable subordinate participant/value slots; unrelated assertions split even when they share evidence. |
| RES-011 | resolved-design | Observation and Claim use compatible typed-hybrid semantic grammar without creating a durable Proposition object or unrestricted JSONB semantic escape hatch. |

## Register discipline

When a contract encounters an unresolved question already represented here, link the item ID rather than creating a differently worded duplicate.

When an item is resolved:

1. reconcile the affected contracts;
2. change the item status here;
3. record the semantic answer or remaining physical question;
4. do not delete the old concern merely because it is resolved.

This register is a coordination device, not project authority.
