# HT-01 Through HT-20 Closure Ledger

## Closure classification

The executable evidence command is:

```powershell
uv run python scripts/run_ht_evidence.py
```

The latest generated record is written outside Git at:

```text
runtime/ht-evidence/latest-ht-evidence.json
```

A status of `complete` means the invariant has named pytest node IDs, an explicit expected result, a real execution result, and deterministic machine-readable evidence. `Deferred by approved scope` is not a test pass; it records that the capability is not admitted in M03.

| HT | Invariant | Named evidence | Closure |
|---|---|---|---|
| HT-01 | Exact authored-text approval binding | exact binding mutations | complete |
| HT-02 | Approval freshness and exact revision | stale binding, wrong-state rollback, successor supersession | complete |
| HT-03 | Lifecycle legality and invalidation | illegal transition, authority bypass, bounded rejection | complete |
| HT-04 | Stable external identity | fabricated FK, stable replay, mutable username update | complete |
| HT-05 | Canonical evidence integrity | path escape, missing file, hash mismatch | complete |
| HT-06 | Database/filesystem reconciliation | valid restore, orphan rejection, DB/byte disagreement | complete |
| HT-07 | Connection foreign-key enforcement | pragma contract and fabricated relationship rejection | complete |
| HT-08 | Uniqueness and idempotency | exact replay, conflicting reuse, duplicate publication identity | complete |
| HT-09 | Transaction atomicity | transition, approval, and publication rollback proofs | complete |
| HT-10 | Concurrency and busy handling | real overlapping-writer fixture | complete |
| HT-11 | Audit integrity | append-only triggers and out-of-band chain tamper | complete |
| HT-12 | Metric observations | replay, conflict, append-only correction | complete |
| HT-13 | Explicit unknown states | explicit query vocabulary and invented-state rejection | complete |
| HT-14 | Mention classification | no classifier admitted in M03 | deferred by approved scope |
| HT-15 | Platform isolation | cross-platform/account publication rejection | complete |
| HT-16 | Dirty migration state | blocking, matching-clear requirement, startup refusal | complete |
| HT-17 | Interrupted migration recovery | retained marker, verified completion, bounded empty discard | complete |
| HT-18 | Backup and disposable restore | backup, deterministic ZIP, real age round-trip, tamper rejection | complete |
| HT-19 | Three-way restore reconciliation | database, manifest, and raw-byte disagreement rejection | complete |
| HT-20 | Detector/classifier non-authority | flagged, non-detected, errored advisory outcomes and bypass rejection | complete |

## Current execution result

```text
Executed: 19
Passed: 19
Failed: 0
Deferred by approved scope: 1
```

## Exit interpretation

The M03 persistence, authority, recovery, service-loop, and thin-interface technical gates pass. HT-14 does not block M03 because mention classification was not admitted into this milestone and no classifier implementation exists to test.

The remaining M03 gate is owner acceptance of the workflow boundary and closure package. The thin web interface remains a disposable contract harness and is not accepted as the future product UI.

# M04 Grouped Executable Coverage

M04 retains the accepted 60-row adversarial matrix in the documentation repository. The executable runner adds six grouped M04 proof records without replacing the row-level planning matrix.

| Evidence ID | Coverage | Named test surface | Current result |
|---|---|---|---|
| M04-G01 | editorial organization, tags, schedule authority, horizon, lineage, replay, dormancy, targets | `tests/test_m04_editorial_schedule_contract.py` | passed |
| M04-G02 | account-isolated derived queries, Ready-to-Post, Need-a-Post, Reserve, empty-slot behavior | `tests/test_m04_operator_queries.py` | passed |
| M04-G03 | Command Center, schedule, pipeline, state-aware web actions, refusal behavior | `tests/test_m04_web_workflow.py`; `tests/test_web_control_room.py` | passed |
| M04-G04 | two-account editorial week, all lanes, schedule-only approval preservation, content invalidation, publication match/mismatch/replacement, honest metrics, replay | `tests/test_m04_editorial_week_scenario.py` | passed |
| M04-G05 | migration `0004`, dirty/interrupted recovery, manifest, archive, backup, restore | migration/recovery/restore test modules | passed |
| M04-G06 | inherited lifecycle, exact approval, publication, metric, idempotency, concurrency, and audit contracts | persistence/operator/lineage test modules | passed |

## Current M04-inclusive execution result

```text
Executed: 25
Passed: 25
Failed: 0
Deferred by inherited scope: 1
```

The runtime JSON is provisional until rerun against the accepted Package C implementation commit. The final evidence SHA-256 and exact commit binding belong in `docs/m04-exit-gate-review.md`.
