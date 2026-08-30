# FND-PG01: Execute PostgreSQL 18 foundation proofs

**Status:** accepted

**Owner:** Project Steward

**Designated Writer:** Claude Code (temporary substitution while Grok Build is usage-limited)

**Implementation start commit:** pinned by the Project Steward to the exact clean post-ticket commit in the Writer handoff. The Writer must refuse a different HEAD.

**Blocked by:** None. The non-authoritative physical sketch and scratch harness are complete enough to make the proof executable and falsifiable.

## What to build

Implement the smallest proof-only runner needed to execute the three PostgreSQL 18 scratch proofs defined by `docs/design/POSTGRESQL-SCRATCH-PROOF-HARNESS-01.md` against the connection supplied in `VEDAOPS_POSTGRES_URL`.

This ticket does **not** create the production Desk schema, a migration framework, `0001_initial`, a persistent database, or a general PostgreSQL abstraction. It exists only to turn the accepted scratch harness into executable evidence.

The runner must leave container provisioning and teardown to VedaOps. It receives one already-provisioned PostgreSQL 18 connection URL, creates three isolated temporary proof databases, executes Proof A / B / C, force-drops every proof database, and emits a bounded machine-readable plus human-readable execution report.

After implementation review, the Project Steward will bind the reviewed fixed argv into trusted external VedaOps operator policy as a dedicated `postgres-foundation-proofs` task. The Writer must not modify external VedaOps registry state.

## Authority and source contract

The executable behavior is governed by:

1. `docs/design/POSTGRESQL-SCRATCH-PROOF-HARNESS-01.md` for exact proof semantics and required report evidence;
2. `docs/design/POSTGRESQL-SCHEMA-SKETCH-01.md` for the candidate physical design being falsified;
3. `docs/design/FOUNDATION-OPEN-ITEMS.md` for the unresolved questions the results may inform;
4. `docs/design/DEVELOPMENT-METHOD.md` for Writer/review boundaries.

If implementation convenience conflicts with the scratch harness, the harness wins unless the Steward explicitly reconciles a defect first.

## Acceptance criteria

- [ ] The runner refuses to start unless `VEDAOPS_POSTGRES_URL` is present and parseable; it never silently falls back to localhost, the host PostgreSQL cluster, Docker metadata, or another DSN.
- [ ] Before any proof, it connects to the supplied server and records `SELECT version()`, `SHOW server_version_num`, `SHOW server_version`, and `SHOW track_commit_timestamp`.
- [ ] It converts `server_version_num` to an integer and fails closed unless the numeric major is exactly 18.
- [ ] It creates three uniquely named temporary databases inside the supplied disposable server: one each for Proof A, Proof B, and Proof C.
- [ ] Every proof database starts empty, all proof objects live under schema `proof`, and each database is force-dropped after its proof even when the proof fails.
- [ ] Proof A uses two genuinely independent PostgreSQL client connections to the same proof-A database. Session B attempts the advisory lock while Session A still owns it; the runner observes blocking rather than merely executing two statements sequentially.
- [ ] Proof A demonstrates that lock-obeying committed admissions allocate ordinals in serialized gate order and that a rolled-back sequence allocation leaves a semantically meaningless gap.
- [ ] Proof B exercises the exact D1/D2/D3/D8/D9 identity data and supersession relation from the harness at boundaries B=14, B=16, and B=21.
- [ ] Proof B demonstrates the full positive cluster with no conflict at B=14, explicit `CONFLICTED` state without arbitrary partition at B=16, repaired E17-vs-E42/E99 structure with no conflict at B=21, and preservation of the historical B=14 answer after D9 exists.
- [ ] Proof C creates the typed provenance tables, reverse indexes, and read-only normalized traversal view from the harness.
- [ ] Proof C demonstrates the required forward and reverse traversals for C7V1, O4, D2, and D20.
- [ ] Proof C executes the nonexistent-FK and invented-relation adversaries inside recoverable savepoints and treats rejection by PostgreSQL constraints as the expected result. Unexpected success is a proof failure.
- [ ] SQL execution is explicit and reviewable. The runner must not reinterpret failed assertions into a passing outcome or substitute different data/queries that weaken the harness.
- [ ] The runner emits enough evidence to reconstruct each PASS/FAIL decision: exact connected PostgreSQL version/settings, proof database names, exact or deterministically identified SQL steps, observed result rows/values, expected-vs-observed assertions, teardown result, and whether any statement unexpectedly succeeded or failed.
- [ ] The report explicitly states that the host-installed PostgreSQL cluster was not selected by the runner. It must not claim network-level proof beyond what the supplied VedaOps connection contract and observed DSN/server evidence establish.
- [ ] No database URL password or other credential is printed, persisted, committed, included in test snapshots, or returned in the report.
- [ ] A proof failure produces a non-zero process exit and still attempts all required cleanup for state already created.
- [ ] A successful run exits zero only when all three proofs and all teardown checks pass.
- [ ] The implementation includes deterministic automated tests for runner logic that do not require or fake a successful physical PostgreSQL proof. Physical PASS evidence comes only from the later Steward-run VedaOps commissioning execution.
- [ ] The Writer returns the exact fixed argv required to run the proof runner so the Steward can bind only that argv to the external VedaOps task `postgres-foundation-proofs`.
- [ ] No production schema, migrations, application domain package, public API, UI, publication path, provider/network call, or unrelated refactor is added.

## Required physical execution report

The later Steward-run physical execution must report, for each proof:

- VedaOps substrate image `postgres:18-alpine`;
- connected `server_version_num` and proof of numeric major 18;
- VedaOps-selected loopback host/port metadata without credentials;
- proof database name and force-drop result;
- exact PostgreSQL version and relevant settings;
- executed proof steps and observed results;
- PASS/FAIL with explicit reason;
- design consequences for `FND-002`, `FND-008`, `FND-009`, `FND-010`, and `FND-011`;
- explicit statement that no production Desk database/schema was created and that the host-installed PostgreSQL cluster was not selected as the substrate.

The report must distinguish **physical behavior proved by PostgreSQL** from **design conclusions inferred by the Steward**. Passing SQL does not automatically resolve an open item.

## Standing seam checks

Before implementation is accepted, review this slice for:

1. **Vocabulary reconciliation** — use the existing names Admission, Decision, Claim version, Observation, Basis/provenance, and identity effects exactly as the governing documents define them.
2. **Fail-open inventory** — no DSN fallback, version fallback, skipped proof, swallowed cleanup error, or unexpected SQL success may become PASS.
3. **Destructive-write inventory** — all destructive SQL is confined to uniquely named disposable proof databases; no host or production Desk database is targeted.
4. **Dead-capability inventory** — every helper/flag/dependency added must be exercised by this proof path; no speculative fixture framework.
5. **Write-once inventory** — proof evidence is execution output, not authoritative Record state; do not introduce mutable semantic state under the guise of proof bookkeeping.
6. **Projection completeness** — forward and reverse provenance proof results must agree, and identity current/historical projections must be tested at every specified boundary.

## Pre-implementation review questions

The designated Writer must answer these before implementation:

1. Identify any harness statement that is ambiguous or impossible to prove with the supplied VedaOps connection contract.
2. Explain the concrete concurrency choreography for Proof A and how the test proves B attempted the lock while A still held it.
3. Explain how cleanup remains reliable when setup, a proof assertion, or report generation fails.
4. Identify every place credentials could accidentally leak and how the implementation prevents it.
5. State the proposed fixed argv for the later VedaOps task and every new dependency it requires.
6. Confirm the changed-path surface and justify why no production schema/migration/application path is needed.

Implementation does not begin until the Steward accepts the adversarial pre-implementation review.

## Steward commissioning acceptance — 2026-08-30

FND-PG01 is commissioned and accepted as a **foundation checkpoint**, not as a production schema milestone.

The governed VedaOps PostgreSQL execution used PostgreSQL 18 (`server_version_num = 180006`) and reported:

- **Proof A PASS** — advisory-lock admission ordering was physically exercised, including rollback/sequence-gap behavior;
- **Proof B PASS** — historical identity projection, explicit conflict state, supersession/repair, and historical reconstruction were physically exercised;
- **Proof C PASS** — typed provenance, forward/reverse traversal, and exact default-deny adversaries were physically exercised;
- all proof databases and the disposable PostgreSQL substrate were removed after execution;
- no production Desk schema or migration was created.

Steward consequence:

- `FND-002` received partial physical evidence;
- `FND-008` received candidate projection evidence;
- `FND-010` received typed/default-deny candidate evidence;
- `FND-009` and `FND-011` were not exercised by this checkpoint.

This acceptance does **not** authorize another general foundation-proof series. Remaining physical questions should be resolved when a real vertical product slice encounters them. `docs/adr/0001-postgresql-record-store.md` records the promoted Record-store decision; successful scratch SQL is evidence for implementation choices, not the production schema itself.
