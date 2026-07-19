# HT-01 Through HT-20 Coverage Ledger

## Status

Active M03 implementation ledger. A row marked `partial` is not a satisfied exit gate.

| HT | Coverage | Evidence in current suite | Status |
|---|---|---|---|
| HT-01 | Exact authored-text approval binding | whitespace, CRLF/LF, zero-width, platform mutations | partial |
| HT-02 | Approval freshness and exact revision | stale binding rejection, wrong-state approval rollback | partial |
| HT-03 | Lifecycle legality and invalidation | legal/illegal transitions, dedicated approval gate, manual-ready/publication and mismatch gates | substantial |
| HT-04 | Stable external identity | fabricated FK, governed owned-account creation, unique external identity, and cross-platform publication rejection | substantial |
| HT-05 | Canonical evidence integrity | path escape, missing, hash mismatch | partial |
| HT-06 | Database/filesystem reconciliation | missing, orphan, hash and size disagreement on restore | substantial |
| HT-07 | Connection foreign-key enforcement | connection pragma verification and fabricated identity rejection | substantial |
| HT-08 | Uniqueness and idempotency | replay no-op, conflict rejection, publication uniqueness | substantial |
| HT-09 | Transaction atomicity | transition, approval, readiness, publication rollback tests | substantial |
| HT-10 | Concurrency and busy handling | real overlapping writer rejection | partial |
| HT-11 | Audit integrity | append-only triggers and out-of-band tamper detection | substantial |
| HT-12 | Metric observations | append-only snapshots, duplicate session handling | partial |
| HT-13 | Explicit unknown states | schema vocabulary plus explicit supported-state query semantics and unsupported-state rejection | substantial |
| HT-14 | Mention classification | explicitly deferred outside first M03 slice | deferred |
| HT-15 | Platform isolation | X/Truth Social publication crossover rejection | substantial |
| HT-16 | Dirty migration state | durable guard creation, mismatch, blocking | substantial |
| HT-17 | Interrupted migration recovery | guarded Alembic execution, retained marker, verified-complete recovery, and bounded empty-failure discard | substantial |
| HT-18 | Backup and disposable restore | safe backup, deterministic archive, restore verification | partial |
| HT-19 | Three-way restore reconciliation | database, manifest, and bytes disagreement detection | substantial |
| HT-20 | Detector/classifier non-authority | generic approval bypass rejected; flagged, non-detected, and errored detector outcomes remain advisory | substantial |

## Exit Rule

No row becomes `complete` without a named fixture, exact command, expected fail-closed result, real-engine execution where applicable, and preserved deterministic evidence record.
