# M04 Service and Operator Contract

## Status

Implemented for owner review under the accepted M04 exact work package.

## Authority Boundary

The FastAPI/Jinja control room is a human-operated contract harness. It does not publish, reply, like, follow, repost, or send direct messages through X or any other platform.

All mutations remain local and governed. External publication is performed manually by the owner and then recorded locally.

## Durable Operations

The admitted M04 service operations are:

- `organize_work_item`
- `set_work_item_tags`
- `schedule_work_item`
- `reschedule_work_item`
- `unschedule_work_item`
- `set_editorial_target`
- `record_manual_metric_observation`
- `record_manual_publication_result`
- `reconcile_publication_result`

Each mutation requires explicit account scope, actor identity, an operation key, request hashing, one transaction, audit evidence, and fail-closed rejection.

## Read-Only Derived Operations

The read-only query layer exposes:

- `get_command_center`
- `list_schedule`
- `list_unscheduled_reserve`
- `list_pipeline_view`
- `evaluate_ready_to_post`
- `recommend_need_a_post`

Derived views are not persisted as authority. Missing account scope and cross-account access fail closed.

## Ready-to-Post

Ready-to-Post is derived from persisted authority. It requires a current exact revision, a live exact human approval, compatible account scope, no consumed publication authority, no blocker or expired schedule, no dormant organization state, and no schedule-to-revision mismatch.

The result includes explicit refusal reasons.

## Need-a-Post

Need-a-Post ranks existing governed inventory only. It cannot create, draft, approve, schedule, publish, or mutate records. An empty candidate list is a valid result and explicitly authorizes leaving the slot empty.

## Operator Routes

- `GET /` — account-scoped Command Center
- `GET /schedule?account_id=...` — rolling 90-day schedule
- `GET /pipeline?account_id=...&view=...` — named operational queues
- `GET /work-items/{id}` — work-item details, organization, tags, schedule history, readiness, and existing M03 workflow controls
- governed POST routes for organization, tags, schedule, reschedule, unschedule, capture, evidence, revisions, review, manual-ready, publication, reconciliation, and metrics

## Trustworthy Failure Contract

A refused request states:

1. what happened;
2. what existing records were preserved;
3. what was not changed;
4. the safe next operator action.

Raw SQL, tracebacks, credentials, and internal secret material are not intentionally rendered.

## Multi-Account Rule

Every M04 durable record and derived view is account-scoped. Cross-account publication, organization, schedule, metric, and query requests fail closed.

## Explicit Exclusions

This contract does not admit autonomous posting, provider polling, Release Watch, Hermes, agent API/MCP, Truth Social automation, dossiers, Qdrant, replies, articles, asset management, causal analytics, or Tauri product work.
