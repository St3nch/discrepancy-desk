# M04 Exit-Gate Review — Final Technical Record

## Status

Package C implementation is accepted, committed, pushed, and validated against the exact implementation commit. M04 remains open only for final documentation synchronization, clean-repository verification, and explicit owner closure acceptance.

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

Final exact-commit results:

```text
uv run ruff check .                         passed
uv run pytest -q                            67 passed
uv run python scripts/run_ht_evidence.py    25 executed, 25 passed, 0 failed
Inherited HT-14 scope deferral              1
```

Final evidence file:

```text
runtime/ht-evidence/latest-ht-evidence.json
```

Final evidence SHA-256:

```text
fcf6842ab088fa99adc4e6cc3ad2f9fb0c1330dff3a95ff614c8df0c1c54729c
```

The final evidence run is bound to application commit:

```text
1455433ddee69d52b1dc67367a532b594a4a1a6c
```

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

1. Commit and push this final evidence-binding update.
2. Synchronize the documentation repository and milestone status.
3. Verify both repositories are clean and synchronized.
4. Owner explicitly accepts M04 closure.
