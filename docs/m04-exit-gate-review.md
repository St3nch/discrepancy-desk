# M04 Exit-Gate Review — Provisional Technical Record

## Status

Package C implementation and technical proof are prepared for owner review. M04 is not closed until the accepted implementation is committed, the executable evidence is rerun against that exact commit, documentation is synchronized, repositories are clean, and the owner explicitly accepts closure.

## Implemented Capability

The owner can operate the admitted workflow through the local FastAPI/Jinja control room:

- register and select owned accounts;
- capture and organize work;
- assign Archive, Docket, or Flash Release lanes;
- record topic, priority, notes, dormant state, and normalized tags;
- schedule inside the rolling 90-day horizon;
- reschedule while preserving schedule history and exact approval binding;
- return work to the Unscheduled Reserve;
- use account-scoped Command Center and pipeline views;
- inspect deterministic Ready-to-Post reasons;
- use Need-a-Post without filler pressure;
- continue the M03 exact-review, manual-ready, publication, reconciliation, correction, and metric loop;
- receive operator-safe refusal explanations.

## Realistic Editorial-Week Proof

`tests/test_m04_editorial_week_scenario.py` uses two synthetic X accounts and four synthetic work items across all three lanes. It proves:

- account isolation;
- in-horizon scheduling;
- rescheduling and schedule history;
- return to Reserve;
- approval preservation after schedule-only change;
- approval supersession after content change;
- Ready-to-Post true and false results;
- empty Need-a-Post behavior;
- manual publication match and reconciliation;
- publication mismatch, successor revision, renewed approval, and replacement publication lineage;
- honest `unavailable` and `errored` metric states;
- exact replay without duplicate audit mutation;
- intact audit-chain verification.

No real platform write occurs. All external IDs and URLs are synthetic fixtures.

## Validation

Current pre-commit results:

```text
uv run ruff check .                         passed
uv run pytest -q                            67 passed
uv run python scripts/run_ht_evidence.py    25 executed, 25 passed, 0 failed
Inherited HT-14 scope deferral              1
```

The provisional evidence file is:

```text
runtime/ht-evidence/latest-ht-evidence.json
```

Provisional evidence SHA-256:

```text
9a3568b6b6e00efb0482c0fd997786e4a36a1c20d032aeb6902d1112fa1422b6
```

That provisional run is bound to application commit:

```text
55a276e34003508df0dd17687d09d68185ae6a21
```

Because Package C changes are currently uncommitted, this hash is not final closure evidence. After owner acceptance and implementation commit, the hammer command must be rerun and the final evidence hash recorded against the new exact commit.

## Migration and Recovery

The full regression and grouped hammer evidence preserve proof for:

- fresh upgrade through Alembic `0004`;
- upgrade from the M03 schema without losing existing rows;
- dirty/interrupted migration refusal and bounded recovery;
- migration manifest verification;
- deterministic archive behavior;
- backup and disposable restore;
- evidence/database/manifest reconciliation;
- no destructive downgrade claim.

## Current Findings

No lifecycle expansion, provider dependency, platform API requirement, destructive migration, direct agent authority, or evidence deletion was required.

The implementation remains inside the accepted M04 change surface and the owner-authorized regression-test amendment.

## Remaining Closure Actions

1. Owner reviews and accepts the Package C batch.
2. Stage and inspect the exact application diff.
3. Commit and push the application batch.
4. Rerun Ruff, the full test suite, and executable hammer evidence against the exact implementation commit.
5. Record the final commit SHA and evidence SHA-256 here.
6. Synchronize the docs repository and milestone status.
7. Owner explicitly accepts M04 closure.
