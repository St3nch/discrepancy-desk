# FND-PG01 Steward Reconciliation 01

**Status:** accepted

**Date:** 2026-08-29

**Owner:** Project Steward

**Amends:** `FND-PG01-postgresql-foundation-proofs.md` and, for this ticket only, conflicting execution details in `POSTGRESQL-SCRATCH-PROOF-HARNESS-01.md`.

**Reason:** Reconcile the designated Writer's read-only adversarial pre-implementation review before implementation begins.

Where this amendment conflicts with the original FND-PG01 ticket or scratch-harness execution choreography, this amendment controls for FND-PG01. It does not promote the physical schema sketch to authority and does not authorize production schema or migration work.

## 1. Review disposition

The review's blocking findings B1, B2, B3, B4, and B6 are accepted in substance and reconciled below. B5 is accepted as a real first-mover risk but is resolved here as a proof-tooling boundary rather than escalated into an application-architecture decision.

The review's proposed Proof A choreography is **not** accepted verbatim: it attempted to observe the sequence at A's value before A had allocated that value. The corrected choreography below allocates A's ordinal before B attempts the lock.

The review's suggested Proof A negative control (a lock-second writer) is not required by this ticket. FND-PG01 proves the sufficiency and observable behavior of the lock-first governed admission gate. It does not need to prove that every alternative discipline fails.

## 2. Proof A — corrected concurrency proof

Proof A uses three independent connections to the same proof-A database:

1. Session A;
2. Session B;
3. a read-only observer.

The fixed advisory-lock key remains `90201001`.

### 2.1 Required choreography

1. A begins a transaction and records `pg_backend_pid()`.
2. A acquires `pg_advisory_xact_lock(90201001)`.
3. A performs the harness INSERT, including `nextval('proof.record_admission_order_seq')`, and records the returned A ordinal. A keeps the transaction open using a client-side synchronization gate. `pg_sleep(8)` is not normative for the programmatic runner and must not be used as proof of blocking.
4. B begins a transaction and records `pg_backend_pid()`.
5. On an independent execution path, B records its before-lock timestamp and calls `pg_advisory_xact_lock(90201001)`. B must not execute `nextval` before that call returns.
6. While A is still open and B's lock call has not returned, the observer polls to a bounded deadline and must obtain positive PostgreSQL state showing:
   - A's advisory lock row is `granted = true`;
   - B's corresponding advisory lock row is `granted = false`;
   - B reports `wait_event_type = 'Lock'`;
   - `pg_blocking_pids(B_pid)` contains A's pid;
   - the sequence `last_value` still equals the ordinal already allocated by A.
7. Only after all observer assertions pass does the runner commit A.
8. B's advisory-lock call must then return within a bounded deadline. B records its after-lock timestamp, performs its INSERT/`nextval`, and commits.
9. PASS requires A's committed ordinal to be lower than B's and requires the observer evidence above. Elapsed time alone is not sufficient evidence.

For a single-`bigint` advisory key, identify the lock using PostgreSQL's documented representation: `objsubid = 1` and `((classid::bigint << 32) | objid::bigint) = 90201001`. Filter to the proof database and the known A/B backend pids. Do not match only `objid = 90201001`.

The runner may parameter-bind backend pids. It must not interpolate caller-controlled text into observer SQL.

### 2.2 Rollback gap

The rollback result is deterministic for this proof. Capture C's exact returned ordinal before rollback. PASS requires:

- C's exact ordinal is absent from `proof.record_admission` after rollback;
- D's committed ordinal is strictly greater than C's allocated ordinal;
- the missing value is reported as a sequence-allocation gap with no semantic meaning.

## 3. Proof B — pin the missing cluster projection

The programmatic runner must bind boundary `B` as a SQL parameter. The psql `\set B` / `:B` notation in the harness is illustrative, not a requirement to invoke psql or rewrite values into SQL text.

In addition to the harness operative/conflict query, run the same `operative`, `positive_edge`, and `reach` CTEs and finish with exactly this projection shape:

```sql
SELECT DISTINCT src, dst
FROM reach
WHERE src < dst
ORDER BY src, dst;
```

Expected undirected reachable pairs are:

```text
B = 14
E17 E42
E17 E99
E42 E99

B = 16
E17 E42
E17 E99
E42 E99

B = 21
E42 E99
```

At B=16, the positive connected component remains visible **and** D8 must be reported as `CONFLICTED`. The runner must not resolve that contradiction by silently cutting an edge or choosing a representative Entity.

At B=21, D9's explicit supersession removes D1, D3, and D8 from the operative set; D2 remains operative. E17 is therefore outside the surviving positive component and E42/E99 remain connected.

The later existence of D9 must not alter the reconstructed B=14 result.

## 4. Proof C — corrected traversal expectation and extra integrity adversary

The harness forward query orders by `source_type, source_id, relation_kind`. The exact ordered rows are therefore:

```text
decision     D2   identity_resolution
decision     D20  claim_posture
observation  O4   supports
```

Assert both exact set membership and this exact ordered result. Do not retain the harness's prose ordering `O4, D2, D20` as an ordered assertion.

Keep the nonexistent-FK and invented-relation adversaries. Add one further recoverable adversary: attempt an INSERT through `proof.provenance_edge_v` and require PostgreSQL to reject it. The `UNION ALL` view is intentionally a read-only normalized traversal surface; unexpected successful mutation is a proof failure.

## 5. Database lifecycle and preflight

The supplied VedaOps connection is the maintenance/admin connection. The runner must:

- refuse when `VEDAOPS_POSTGRES_URL` is absent or unparseable;
- never fall back to another DSN, localhost, Docker discovery, or the host PostgreSQL cluster;
- use an autocommit maintenance connection for `CREATE DATABASE` and `DROP DATABASE`;
- fail closed if the supplied role cannot create and drop proof databases; no one-database fallback is allowed;
- create each proof database immediately before its proof and drop it immediately after that proof rather than creating all three up front;
- create proof databases from `TEMPLATE template0` so they start from PostgreSQL's pristine template rather than mutable `template1` state;
- close all runner-owned connections to a proof database before issuing `DROP DATABASE ... WITH (FORCE)` from the maintenance connection; `FORCE` is a cleanup backstop, not a substitute for closing owned connections;
- register a created proof database for cleanup immediately after successful creation;
- attempt cleanup in proof-local `finally` handling and perform a process-level backstop sweep of any still-registered proof database;
- make any cleanup failure force the overall result to FAIL/non-zero.

"Starts empty" means no Desk/proof application objects exist before that proof's setup. PostgreSQL system/template objects are not prohibited.

Capture the four harness preflight statements on the maintenance connection and repeat them in every proof database. Numeric `server_version_num // 10000 == 18` is mandatory on every connection context used as proof evidence. Also record credential-free connection observations sufficient to identify the exercised server context, such as current database/current user and `inet_server_addr()` / `inet_server_port()`, without claiming those values prove the Docker image or host-network path.

`SHOW track_commit_timestamp` is evidence only. If it is `off`, record `off`. None of FND-PG01's three proofs exercises a commit-timestamp finalizer or civil-time-to-admission-boundary receipt.

## 6. Hang and fail-open protection

Every concurrency wait and observer poll has a client-side hard deadline. A missed deadline is FAIL, followed by cleanup. Do not use B's `lock_timeout` as the mechanism for demonstrating the blocking behavior under test.

The runner must not silently truncate its own evidence. The later Steward commissioning run must also treat VedaOps `output_truncated = true` as a failed commissioning result because the evidence would be incomplete.

All proof database identifiers are runner-generated and must be composed with the driver's identifier-quoting facility. Values and boundaries are parameter-bound. No DSN-derived value is interpolated into SQL identifiers or SQL text.

## 7. Credential boundary

The raw DSN is read only from `VEDAOPS_POSTGRES_URL`; it never appears in argv.

The runner must never serialize the raw DSN, password, driver connection-info repr, environment contents, or an unfiltered driver exception. Reports contain only credential-free host/port/user/database observations. Error reporting uses runner-authored bounded messages and stable error categories.

Before emitting the final report, perform a defense-in-depth secret check against the known raw password and encoded forms. Detection forces a non-zero result and suppresses the contaminated report body.

No proof report is written into tracked repository paths. For this ticket the fixed task emits one bounded machine-readable JSON document to stdout; that document includes a concise `human_summary` field. No report-path flag is required by the governed task.

## 8. VedaOps versus runner evidence

VedaOps owns the disposable container substrate. The runner does not start or inspect Docker.

For FND-PG01 the lifecycle responsibility is divided as follows:

- **VedaOps-attested:** fixed image `postgres:18-alpine`; unique disposable container; `--rm`; no persistent volume; proof-only random credential; random loopback publication; container readiness; VedaOps-side major-18 check; final container removal/cleanup status.
- **Runner-proved from the supplied connection:** successful connection; independent numeric major-18 check; per-proof database creation/isolation; SQL behavior; observed rows; assertions; proof-database teardown; credential-free SQL-visible server context.
- **Steward-inferred/design:** what those observations mean for foundation items and whether any design may be promoted.

The governed VedaOps tool intentionally does not expose its internal container name. The FND-PG01 execution report therefore does **not** require a container name. The Steward combines the VedaOps tool result with the runner's JSON report into the physical execution evidence.

The statement "host-installed PostgreSQL was not selected as the substrate" is an attestation from the fixed VedaOps host-operation contract, not a network-level fact proved by SQL. The runner must not hard-code the current host-cluster port `5433` as a security boundary or claim that a different port alone proves a different server.

## 9. Foundation-item consequence vocabulary

The physical report must classify affected items without over-claiming:

- `FND-002` — **PARTIAL PHYSICAL EVIDENCE** if Proof A passes. It covers serialized ordinal allocation under the lock-first gate and rollback gaps. It does not prove the civil-time/admission-boundary receipt-finalizer question.
- `FND-008` — **PHYSICAL EVIDENCE FOR THE CANDIDATE PROJECTION** if Proof B passes. Passing does not by itself promote the open-design item to resolved authority.
- `FND-009` — **NOT EXERCISED**. Proof C manually inserts dependency rows; it does not test automatic dependency capture.
- `FND-010` — **PHYSICAL EVIDENCE FOR THE TYPED DEFAULT-DENY CANDIDATE** if Proof C passes.
- `FND-011` — **NOT EXERCISED**. FK/CHECK/view enforcement is not append-only privilege/trigger enforcement.

Passing SQL never changes an item status automatically.

## 10. Proof-only Python scaffolding decision

FND-PG01 may establish the minimum Python environment needed to execute and deterministically test the proof runner, but it must not establish the future Desk application package architecture.

Use:

- Python 3.12;
- `uv` for dependency resolution/locking;
- `psycopg[binary]` as the only runtime third-party dependency;
- `pytest` for deterministic runner-logic tests;
- `ruff` for bounded lint/format checks;
- a root `pyproject.toml` and `uv.lock` explicitly scoped to proof tooling;
- implementation code under `tools/postgres_foundation_proofs/`, not `src/`;
- deterministic tests under `tests/proofs/`.

Do not add a production application package, migration package, database abstraction, ORM, web framework, or type-check stack in this ticket. The future Desk application layout remains undecided.

The reviewed fixed argv to target is:

```text
["uv", "run", "--offline", "--no-sync", "python", "-m", "tools.postgres_foundation_proofs"]
```

Commissioning reconciliation note (2026-08-29): live VedaOps registry validation rejects an absolute path in task `argv[0]` and requires a bare executable name. The finalized binding therefore invokes `uv` from the governed task environment. `--offline` forbids network access and `--no-sync` forbids runtime environment synchronization/provisioning, preserving the original requirement that dependency provisioning is a separate Steward commissioning step (`uv sync --frozen` after a reviewed lockfile exists).

The task accepts no proof-selection, DSN, host, port, image, relaxation, or skip flags. The bound VedaOps proof task must never install or resolve dependencies at run time.

The expected changed-path surface is limited to:

```text
pyproject.toml
uv.lock
tools/postgres_foundation_proofs/**
tests/proofs/**
docs/tickets/FND-PG01-postgresql-foundation-proofs.md   only if implementation status/report metadata is updated by the accepted workflow
```

No `src/`, migration, production schema, API, UI, provider, publication, or unrelated path belongs in the implementation commit.

## 11. Deterministic test boundary

Automated tests may cover parsing/redaction, numeric version gating, identifier generation/quoting, cleanup registry behavior under injected failures, assertion evaluation over recorded in-memory observations, report serialization/secret suppression, and fail-closed exit mapping.

They must not simulate a live database and then label that simulation a passing physical proof. Physical PASS evidence exists only when the Project Steward later executes the reviewed runner through VedaOps against the disposable PostgreSQL 18 substrate.

## 12. Primary PostgreSQL references used in reconciliation

- PostgreSQL 18 `pg_locks`: advisory `bigint` keys use high-order `classid`, low-order `objid`, and `objsubid = 1`; `granted = false` represents a waiting lock request; PostgreSQL recommends `pg_blocking_pids()` to identify blockers.
- PostgreSQL 18 sequence functions: `nextval` values are not reclaimed on rollback, so gaps are expected and carry no gapless-order semantics.
- PostgreSQL 18 `CREATE DATABASE` / `DROP DATABASE`: both require execution outside a transaction block; `DROP DATABASE` cannot be issued while connected to the target database; `WITH (FORCE)` attempts to terminate remaining connections.
- PostgreSQL 18 `CREATE VIEW`: a top-level `UNION` view is not automatically updatable and rejects mutation unless separately made updatable through explicit rules/triggers.

References:

- https://www.postgresql.org/docs/18/view-pg-locks.html
- https://www.postgresql.org/docs/18/functions-sequence.html
- https://www.postgresql.org/docs/18/sql-createdatabase.html
- https://www.postgresql.org/docs/18/sql-dropdatabase.html
- https://www.postgresql.org/docs/18/sql-createview.html

## 13. Gate after reconciliation

Implementation remains blocked until the designated Writer reads this amendment against the exact clean post-reconciliation commit and performs a bounded read-only confirmation that no material blocker remains. A new broad review is not required; the confirmation should identify only residual contradictions or state `READY`.
