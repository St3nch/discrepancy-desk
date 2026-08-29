# PostgreSQL Schema Sketch 01 — Foundation Proofs

**Status:** NON-AUTHORITATIVE DESIGN SKETCH

**Target:** PostgreSQL 18.x

**Depends on:** `FOUNDATION-MODEL-V2.md`, Contracts 01–09, and `FOUNDATION-OPEN-ITEMS.md`

**Purpose:** Use concrete PostgreSQL shapes to test the hardest Foundation v2 invariants before any `0001_initial` migration exists.

This is not a migration, accepted schema, ADR, or implementation ticket. SQL is illustrative and may be intentionally incomplete where the point is to expose a design seam.

The sketches must prove three paths:

1. reversible Entity identity with same-identity, distinctness, conflict detection, and historical reconstruction;
2. Claim content/posture reconstruction at an exact Record admission boundary;
3. forward and reverse provenance without a weak polymorphic foreign-key junk drawer.

The sketch also exercises the adjacent enforcement seams that those paths depend on: human-only Decision authority, append-only runtime privileges, stable Observation slots, reference pinning versus stale-state refusal, and idempotent governed writes.

---

# 1. PostgreSQL facts that constrain the design

- `uuidv7()` is available in PostgreSQL 18 and is suitable for internal time-ordered identifiers; it is not a Record clock and should not be exposed as a public identifier merely because it is convenient.
- `now()` / `current_timestamp` describe transaction start, not commit time. `clock_timestamp()` advances during the transaction but still does not create a commit-order key.
- ordinary sequence allocation is concurrency-safe but not transactional: values are not reclaimed on rollback and allocation order alone is not commit order.
- `pg_advisory_xact_lock(...)` is held until the transaction ends and can serialize governed admission transactions when every durable write is forced through that gate.
- PostgreSQL can retain transaction commit timestamps when `track_commit_timestamp` is enabled, but that history is not permanent; if the Desk uses it for audit/mapping it must copy the result into durable Desk state promptly rather than treating `pg_commit_ts` as the Record.

The consequence is deliberate: **canonical historical selection uses immutable Record admission order. Civil timestamps are a mapping onto that order, not its replacement.**

# 2. Admission spine — sketch A

The Desk needs one durable ordering for **when governed semantic state became part of the Record**. That order must not be inferred from object UUIDs, human `decided_at`, transaction-start timestamps, or unconstrained sequence allocation.

Candidate shape:

```sql
CREATE SEQUENCE record_admission_order_seq;

CREATE TABLE record_admission (
    admission_order bigint PRIMARY KEY,
    admission_id uuid NOT NULL UNIQUE DEFAULT uuidv7(),
    transaction_xid xid8 NOT NULL UNIQUE,
    marked_at timestamptz NOT NULL
);
```

`marked_at` is diagnostic/audit time only. It is not the canonical historical selector.

Every governed admission transaction conceptually begins:

```sql
SELECT pg_advisory_xact_lock(<desk_record_admission_lock>);

INSERT INTO record_admission (
    admission_order,
    transaction_xid,
    marked_at
)
VALUES (
    nextval('record_admission_order_seq'),
    pg_current_xact_id(),
    clock_timestamp()
)
RETURNING admission_order;
```

The crucial ordering rule is **lock first, ordinal second**.

Because the exclusive transaction-level advisory lock remains held until transaction end, a later governed writer cannot allocate its admission ordinal until the prior governed admission transaction has committed or aborted. Therefore, among successfully committed governed admission transactions, ordinal order follows serialized transaction completion. Aborted transactions may leave gaps; gaps have no semantic meaning.

This only works if runtime roles have no direct durable-write path that bypasses the admission gate.

## 2.1 Admission batch semantics

One `record_admission` row represents one atomic governed Record admission batch.

All durable semantic rows created in that transaction carry the same `admission_order`:

```text
admission 1042
├─ Observation O9
├─ Claim version C7/V2
├─ Basis rows
└─ producer/Run provenance
```

Rows inside the same committed admission are simultaneously visible from the Record-history perspective. Their intra-transaction SQL command order is not a separate institutional-history clock.

## 2.2 Civil-time mapping

Canonical query:

```text
Record as_of admission_order = 1042
```

is exact.

Convenience query:

```text
Record as_of 2028-06-03T14:00:00-04:00
```

must first resolve that civil time to an admission boundary.

Candidate durable receipt:

```sql
CREATE TABLE record_admission_commit_receipt (
    admission_order bigint PRIMARY KEY
        REFERENCES record_admission(admission_order),
    committed_at timestamptz NOT NULL,
    receipt_copied_at timestamptz NOT NULL,
    clock_order_ok boolean NOT NULL
);
```

A post-commit finalizer may obtain PostgreSQL's commit timestamp while it is still available and copy it here. The copied row becomes Desk audit state; PostgreSQL's transient commit-timestamp store does not.

Rules:

1. missing receipt never changes ordinal-based `as_of`;
2. time-based `as_of` fails closed if the required civil-time boundary cannot be resolved safely;
3. if serialized admission order and recorded commit timestamps regress because the host clock moved backward, mark the affected interval ambiguous rather than manufacturing a false civil-time ordering;
4. the exact finalizer/recovery mechanism remains a physical proof item before migration.

This sketch therefore gives FND-002 a concrete candidate without pretending it is already fully solved.

---
# 3. Common immutable envelope — sketch B

Internal IDs may use PostgreSQL 18 `uuidv7()` for locality and operational convenience. Public IDs remain separate.

Minimal envelopes:

```sql
CREATE TABLE entity (
    entity_id uuid PRIMARY KEY DEFAULT uuidv7(),
    admitted_order bigint NOT NULL
        REFERENCES record_admission(admission_order)
);

CREATE TABLE claim (
    claim_id uuid PRIMARY KEY DEFAULT uuidv7(),
    admitted_order bigint NOT NULL
        REFERENCES record_admission(admission_order)
);

CREATE TABLE observation (
    observation_id uuid PRIMARY KEY DEFAULT uuidv7(),
    admitted_order bigint NOT NULL
        REFERENCES record_admission(admission_order),
    excerpt_id uuid NOT NULL
);
```

The real schema will need stronger Evidence FKs; omitted here because this sketch is proving identity/provenance mechanics rather than re-specifying Contract 01.

Runtime semantics are append-only. A corrected semantic object creates a successor/version under its own contract rather than updating the old row.

---

# 4. Stable subordinate Observation slots — sketch C

Contract 07 requires addressable identity-bearing occurrences without admitting a top-level `Mention` noun.

A composite subordinate key is sufficient:

```sql
CREATE TABLE observation_slot (
    observation_id uuid NOT NULL
        REFERENCES observation(observation_id),
    slot_no smallint NOT NULL,
    role_code text NOT NULL,
    presented_text text NOT NULL,
    PRIMARY KEY (observation_id, slot_no)
);
```

Example:

```text
Observation O17:
  slot 1 / actor        / "Robert Smith"
  slot 2 / organization / "Acme Corp"
```

An identity candidate binds `(O17, 1)` independently of `(O17, 2)`.

If an Observation is superseded by a corrected Observation version, the old composite slot remains permanently addressable. The successor Observation receives its own slot namespace.

This is a physical subordinate structure, not a new domain noun with an independent lifecycle.

---

# 5. Decision envelope and authority separation — sketch D

The semantic `Decision` primitive can have one durable envelope while effects remain typed.

```sql
CREATE TABLE decision (
    decision_id uuid PRIMARY KEY DEFAULT uuidv7(),
    admitted_order bigint NOT NULL
        REFERENCES record_admission(admission_order),
    human_actor_id uuid NOT NULL,
    authority_channel_id uuid NOT NULL,
    decided_at timestamptz NOT NULL,
    rationale text
);

CREATE TABLE decision_supersession (
    new_decision_id uuid NOT NULL
        REFERENCES decision(decision_id),
    superseded_decision_id uuid NOT NULL
        REFERENCES decision(decision_id),
    PRIMARY KEY (new_decision_id, superseded_decision_id),
    CHECK (new_decision_id <> superseded_decision_id)
);
```

Supersession is many-to-many rather than a single nullable parent because one corrective Decision may need to supersede multiple previously operative Decisions.

`decided_at` is human/event metadata. Historical Record visibility is controlled by `admitted_order`.

The runtime authority channel must be separate:

```text
model/research service credential
    └─ cannot EXECUTE human Decision functions

human-authority service credential
    └─ can EXECUTE typed Decision functions
```

An `actor_id = CHAZ` value supplied through the model path is not sufficient authority.

The database sketch should ultimately use separate login/capability paths and narrow `SECURITY DEFINER` entry points owned in a trusted schema, with runtime roles lacking direct INSERT privilege on Decision effect tables.

FND-001 remains open-physical until that channel is implemented/proved.

---

# 6. Identity resolution proof — sketch E

Typed identity effect:

```sql
CREATE TABLE identity_decision_effect (
    decision_id uuid PRIMARY KEY
        REFERENCES decision(decision_id),
    entity_a uuid NOT NULL REFERENCES entity(entity_id),
    entity_b uuid NOT NULL REFERENCES entity(entity_id),
    effect text NOT NULL
        CHECK (effect IN ('same_identity', 'distinct')),
    CHECK (entity_a < entity_b)
);
```

Pair normalization prevents duplicate `(A,B)` / `(B,A)` representations.

## 6.1 Operative edge set at a boundary

For an admission boundary `B`:

1. include identity Decisions with `decision.admitted_order <= B`;
2. exclude a Decision only when a superseding Decision is itself admitted at or before `B`;
3. positive edges are operative `same_identity`;
4. negative edges are operative `distinct`.

Do **not** choose whichever edge has the newest timestamp. Supersession is explicit.

## 6.2 Cluster projection

Build transitive closure over operative positive edges.

Then test every operative negative edge:

```text
if distinct(A,B)
and A reaches B through same_identity closure
then identity projection = CONFLICTED
```

The system does not secretly remove one positive edge, choose a graph cut, or let the negative edge magically override a contradictory positive path.

Human correction must supersede enough positive Decisions to make the graph coherent.

## 6.3 Triangle torture test

Initial state:

```text
D1: E17 = E42
D2: E42 = E99
D3: E17 = E99
```

Current positive closure:

```text
{E17, E42, E99}
```

Later evidence shows E17 is distinct from E42/E99.

Bad correction:

```text
D9: distinct(E17,E42)
```

without superseding contradictory positive edges.

Result:

```text
CONFLICTED
negative: E17 != E42
positive path: E17 --D3--> E99 --D2--> E42
```

No arbitrary split is published.

Coherent correction may instead have D9 supersede D1 and D3 while asserting distinct(E17,E42), leaving D2 operative:

```text
current clusters:
{E17}
{E42,E99}
```

Historical `as_of` before D9 still reconstructs `{E17,E42,E99}`.

This proves the Contract 03 rule without rewriting Entity IDs or provenance.

---
# 7. Claim content and posture proof — sketch F

Claim identity and Claim content version are separate.

```sql
CREATE TABLE claim_version (
    claim_version_id uuid PRIMARY KEY DEFAULT uuidv7(),
    claim_id uuid NOT NULL REFERENCES claim(claim_id),
    admitted_order bigint NOT NULL
        REFERENCES record_admission(admission_order),
    previous_version_id uuid
        REFERENCES claim_version(claim_version_id),
    shape_kind text NOT NULL,
    canonical_text text NOT NULL
);
```

`canonical_text` is not the whole proposition grammar; Contract 07 still requires typed-hybrid shape storage. Shape-specific child tables can carry core references/values. This sketch only needs a durable version identity.

Example typed shape:

```sql
CREATE TABLE claim_role_membership_shape (
    claim_version_id uuid PRIMARY KEY
        REFERENCES claim_version(claim_version_id),
    person_entity_id uuid NOT NULL REFERENCES entity(entity_id),
    organization_entity_id uuid NOT NULL REFERENCES entity(entity_id),
    role_code text NOT NULL,
    world_start_lower date,
    world_start_upper date,
    world_time_qualifier text
);
```

No generic `payload jsonb` stores the core Entity refs, posture, clocks, or provenance target.

## 7.1 Posture is a typed Decision effect

```sql
CREATE TABLE claim_posture_decision_effect (
    decision_id uuid PRIMARY KEY
        REFERENCES decision(decision_id),
    claim_id uuid NOT NULL REFERENCES claim(claim_id),
    claim_version_id uuid NOT NULL
        REFERENCES claim_version(claim_version_id),
    posture_code text NOT NULL
);
```

The exact posture vocabulary remains a separate design item.

A posture Decision targets an exact Claim content version. A later Claim version does not silently inherit the old posture unless an accepted contract explicitly says so.

## 7.2 Historical reconstruction

At boundary `B`:

1. select Claim versions admitted at or before `B`;
2. determine the content version that was current/operative under explicit version lineage at `B`;
3. collect posture Decisions admitted at or before `B` targeting that content version;
4. remove Decisions explicitly superseded by a Decision admitted at or before `B`;
5. if the remaining posture Decision set is contradictory, expose conflict rather than choosing by wall-clock recency.

This makes:

```text
current Claim content
```

and:

```text
Claim content/posture as_of admission 1042
```

separate, mechanically answerable questions.

---

# 8. Exact Claim binding — sketch G

A durable downstream dependency must not bind only `claim_id`.

Candidate header:

```sql
CREATE TABLE claim_binding (
    claim_binding_id uuid PRIMARY KEY DEFAULT uuidv7(),
    claim_id uuid NOT NULL REFERENCES claim(claim_id),
    claim_version_id uuid NOT NULL
        REFERENCES claim_version(claim_version_id),
    admitted_order bigint NOT NULL
        REFERENCES record_admission(admission_order)
);

CREATE TABLE claim_binding_posture_decision (
    claim_binding_id uuid NOT NULL
        REFERENCES claim_binding(claim_binding_id),
    decision_id uuid NOT NULL
        REFERENCES decision(decision_id),
    PRIMARY KEY (claim_binding_id, decision_id)
);
```

The canonical historical binding is therefore conceptually:

```text
Claim identity
+ exact Claim content version
+ exact operative posture-determining Decision set
```

The set is explicit rather than compressed into a vague `version/state` token.

This is the candidate resolution for FND-005, but it should survive worked Publication/Rendition binding before being promoted.

---

# 9. Pin exact references; stale-refuse state mutation — sketch H

Two operation classes are materially different.

## 9.1 Reference operation

Example:

```text
propose C9 derived_from C4@V3
```

If `V3` remains durable/addressable, the proposal may pin exactly `V3` even if `C4` now has `V4`.

The dependency records what the producer actually inspected.

No silent float to V4.

## 9.2 Current-state mutation

Example:

```text
human posture Decision against current C4
expected current version = V3
```

If V4 became current before the Decision transaction:

```text
REFUSE stale_target
```

The command must reread and be re-evaluated.

Every mutation-capable operation should declare one of these binding modes. Unspecified mode fails closed.

This is the candidate semantic resolution for FND-004.

---

# 10. Typed provenance instead of a polymorphic junk drawer — sketch I

For the first executable slice, prefer **typed edge tables with real foreign keys**, then expose one derived UNION view for traversal.

Examples:

```sql
CREATE TABLE claim_version_observation_basis (
    claim_version_id uuid NOT NULL
        REFERENCES claim_version(claim_version_id),
    observation_id uuid NOT NULL
        REFERENCES observation(observation_id),
    relation_kind text NOT NULL
        CHECK (relation_kind IN ('supports', 'contradicts')),
    PRIMARY KEY (claim_version_id, observation_id, relation_kind)
);

CREATE TABLE claim_version_claim_basis (
    claim_version_id uuid NOT NULL
        REFERENCES claim_version(claim_version_id),
    source_claim_version_id uuid NOT NULL
        REFERENCES claim_version(claim_version_id),
    relation_kind text NOT NULL
        CHECK (relation_kind = 'derived_from'),
    PRIMARY KEY (
        claim_version_id,
        source_claim_version_id,
        relation_kind
    )
);

CREATE TABLE decision_observation_basis (
    decision_id uuid NOT NULL REFERENCES decision(decision_id),
    observation_id uuid NOT NULL
        REFERENCES observation(observation_id),
    relation_kind text NOT NULL,
    PRIMARY KEY (decision_id, observation_id, relation_kind)
);

CREATE TABLE decision_decision_dependency (
    decision_id uuid NOT NULL REFERENCES decision(decision_id),
    source_decision_id uuid NOT NULL REFERENCES decision(decision_id),
    dependency_kind text NOT NULL,
    PRIMARY KEY (decision_id, source_decision_id, dependency_kind)
);
```

A derived read view may normalize them:

```sql
CREATE VIEW provenance_edge_v AS
SELECT
    'claim_version'::text AS dependent_type,
    claim_version_id AS dependent_id,
    relation_kind,
    'observation'::text AS source_type,
    observation_id AS source_id
FROM claim_version_observation_basis

UNION ALL

SELECT
    'claim_version',
    claim_version_id,
    relation_kind,
    'claim_version',
    source_claim_version_id
FROM claim_version_claim_basis

-- additional explicitly admitted typed relations only
;
```

The view is for traversal, not write authority.

This gives PostgreSQL real FK integrity while still allowing a single forward/reverse provenance query surface.

The **absence of a typed table/allowed CHECK value is the default deny** for a provenance triple.

This is the leading candidate for FND-010.

---
# 11. Automatic capture of Decision-derived dependencies — sketch J

Human-authored Basis alone is insufficient for reverse provenance.

If a governed operation consumes derived state, the operation layer must persist the exact operative Decisions that made that state available.

Example:

```text
Claim C7 is proposed using:
  E42 currently resolved with E99 via D2
  C4 currently confirmed via D20
```

Candidate typed dependency:

```sql
CREATE TABLE claim_version_decision_dependency (
    claim_version_id uuid NOT NULL
        REFERENCES claim_version(claim_version_id),
    decision_id uuid NOT NULL
        REFERENCES decision(decision_id),
    dependency_kind text NOT NULL
        CHECK (dependency_kind IN (
            'identity_resolution',
            'claim_posture',
            'preferred_label'
        )),
    PRIMARY KEY (claim_version_id, decision_id, dependency_kind)
);
```

When C7 is admitted, these rows are machine-captured in the same admission transaction.

Later:

```text
D9 supersedes identity Decision D2
```

reverse traversal immediately finds C7 without relying on a human having remembered to type D2 into a rationale field.

Only material derived-state dependencies should be captured. UI sort order, search ranking, graph layout, and other rebuildable presentation state remain outside durable Basis.

This is the leading candidate for FND-009.

---

# 12. Reverse-provenance torture test — sketch K

Suppose:

```text
D2 identity resolution
    ↓ machine-captured dependency
C7/V1 Claim
    ↓ exact Claim binding
U4 Rendition Unit
    ↓
P2 Publication
```

Typed tables can support both directions with indexes on both FK sides.

Forward:

```text
P2 → U4 → claim_binding → C7/V1
   → posture Decision set
   → C7 Basis / Decision dependencies
   → D2
```

Reverse after D2 is superseded:

```text
D2
 ↓ claim_version_decision_dependency
C7/V1
 ↓ rendition-unit Claim binding
U4
 ↓ publication-unit binding
P2
```

The later Rendition/Publication tables do not need to exist in `0001` for this proof to determine the foundation rule:

> every durable typed dependency table gets indexes that support both source→dependent and dependent→source traversal.

No governed object points only to `provenance_edge_v`, a cache, a graph projection, or another rebuildable surface.

---

# 13. Append-only runtime enforcement — sketch L

Candidate role separation:

```text
desk_schema_owner        owns schema; NOLOGIN or tightly controlled migration path
desk_record_runtime      governed research proposal/admission entry points
desk_human_authority     separately authenticated Decision entry points
desk_read_runtime        bounded read surface
```

Runtime roles should not own governed tables.

For governed semantic tables:

- revoke direct `UPDATE`, `DELETE`, and `TRUNCATE` from runtime roles;
- prefer no direct `INSERT` either when a narrow admission function can enforce the full transaction contract;
- add defensive triggers rejecting `UPDATE`/`DELETE` on append-only tables;
- allow schema-owner migration activity only through explicit governed maintenance/migration procedure.

A narrow `SECURITY DEFINER` function can be useful, but it must live in a trusted schema with a locked-down `search_path`; function ownership is authority and must not be casually granted.

This is a candidate physical resolution for FND-011 and part of FND-001.

---

# 14. Idempotency seam exposed by the sketch

A governed mutation needs request identity independently of semantic Claim identity.

Candidate receipt:

```sql
CREATE TABLE command_receipt (
    run_id uuid NOT NULL,
    operation_kind text NOT NULL,
    idempotency_key uuid NOT NULL,
    request_hash bytea NOT NULL,
    result_object_id uuid,
    admitted_order bigint
        REFERENCES record_admission(admission_order),
    PRIMARY KEY (run_id, operation_kind, idempotency_key)
);
```

Rules:

1. same key + same request hash → return same logical result;
2. same key + different request hash → explicit conflict;
3. semantic similarity of two independently submitted Claims never triggers idempotency collapse;
4. exact retention and cross-Run scope remain to be proved.

This sharpens FND-015 without closing it prematurely.

---

# 15. What this sketch resolves versus exposes

## Strong design candidates produced

1. **Admission order:** serialize governed admission with transaction-level advisory lock; allocate ordinal only after lock acquisition.
2. **Identity:** typed `same_identity` / `distinct` Decision effects; positive closure plus explicit conflict detection; no hidden graph cut.
3. **Supersession:** many-to-many Decision supersession relation.
4. **Observation occurrence:** composite subordinate `(observation_id, slot_no)` target.
5. **Claim binding:** Claim ID + exact content version + exact operative posture Decision set.
6. **Provenance:** typed FK edge tables plus read-only UNION traversal view.
7. **Derived-state provenance:** machine-capture operative Decision dependencies in the same admission as the dependent object.
8. **Append-only enforcement:** runtime roles get narrow functions/INSERT paths, no UPDATE/DELETE; defensive database enforcement.
9. **Staleness:** references pin exact inspected versions; operations that mutate current state stale-refuse.
10. **Idempotency:** request identity is separate from semantic proposition identity.

## Still not proven enough for migration

- exact civil-time → admission-boundary receipt/finalizer behavior and recovery;
- exact human authentication/channel implementation;
- exact Claim version-currentness invariant and whether any version forks are legal;
- exact posture vocabulary and multi-dimensional posture possibility;
- exact allowed provenance matrix for every slice noun;
- exact `SECURITY DEFINER` functions and database roles;
- exact command-receipt retention/scope;
- Observation/Claim typed shape tables beyond the worked role-membership example;
- slice-1 Evidence FKs and Locator anchors from FND-019.

---

# 16. Migration gate after this sketch

`0001_initial` remains blocked.

The next useful step is not more broad doctrine. It is to turn the candidates above into **three executable PostgreSQL scratch proofs** against PostgreSQL 18:

1. admission-order concurrency proof with two competing transactions, one rollback, and one delayed commit;
2. identity triangle + distinctness conflict + explicit supersession + historical boundary query;
3. typed forward/reverse provenance query over Claim/Decision dependencies.

Those proofs should run against disposable scratch tables only. They must not create the production Desk schema.

If the scratch behavior contradicts this document, change the design document. Do not code around the contradiction.
