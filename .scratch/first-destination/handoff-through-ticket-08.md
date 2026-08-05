# Handoff through ticket 08 → next session: ticket 09 (Lead inbox)

**When:** 2026-08-05  
**HEAD:** `c53e240` on `main` (pushed). Foundation `4037bd6` (01–06), then one commit per ticket: `65bcc27` (07), `c53e240` (08).  
**Next work:** `.scratch/first-destination/issues/09-lead-inbox.md` — do not re-open 01–08 unless review finds a defect.

This document holds only what is *not* already in tickets, ADRs (`docs/adr/`), `../discrepancy-desk-docs/`, `CONTEXT.md`, `codingstandards.md`, or commit messages. Read those first; use this for seams that live only in the code.

---

## Settled references (do not re-derive)

| Concern | Where |
|---|---|
| Product doctrine, D12–D15, D13 close ordering | `../discrepancy-desk-docs/decisions/run-registry-and-tool-surface.md`, VISION |
| Capture-then-cite, byte-exact quote, pull claim | `docs/adr/0001`, `0008`, `0009` |
| Two transports, one service layer | `docs/adr/0010`, `src/desk/transports/wiring.py` |
| Coding seam rules + smell vocabulary | `codingstandards.md` |
| Glossary (run status, dispositions, examined) | `CONTEXT.md` (updated through 08) |
| Review findings F-01–F-32 | `.scratch/first-destination/review-*.md` where present; later F-notes live in chat/commits |
| Issue list | `.scratch/first-destination/issues/01` … `14` |

---

## Suggested skills / entry for the next agent

1. Read `AGENTS.md`, `CONTEXT.md`, `codingstandards.md`, then issue `09-lead-inbox.md`.
2. Read ADR 1 (capture) + D10 leads (material not claims) before inventing a second fetch path.
3. For implementation: follow the existing package layout under `src/desk/` (service → transports → alembic → client → seam tests). Prefer `/implement` or normal agent flow; run `uv run pytest` and `uv run ruff check src tests`.
4. After ticket 09: **one commit only after review passes** (convention from foundation commit message).
5. Code review if asked: `/code-review` or project review skill against standards + issue acceptance criteria.

---

## Migration map (11 revisions — what each actually bought)

Read the filenames under `alembic/versions/`; this is the *meaning* chain a successor otherwise reconstructs by opening every file:

| Rev | Meaning |
|---|---|
| `0001_probe` | Temporary dual-transport probe tables — **gone** after 0003 |
| `0002_cases` | Cases only; **no `account_id`** (D17 — one brand per deployment) |
| `0003_runs` | Full run-status CHECK vocabulary from day one; drops probe tables |
| `0004_captures` | Vault envelope + elements/regions; capture status CHECK; `capture_budget` on runs |
| `0005_claims` | Claims + quote/inference bindings; dimension CHECKs = full VISION §11 |
| `0006_leases` | `lease_expires_at` only |
| `0007_claim_tokens` | `claim_token` — claim *instance*, not executor identity |
| `0008_suspensions` | Projection columns on `runs` for latest suspension (list UI) |
| `0009_suspensions_rows` | Durable `run_suspensions` history (F-28); projection may be overwritten freely |
| `0010_run_close` | `open_questions` + `run_low_confidence`; dispositions + agenda_decision CHECKs |

**Alembic heads:** tests run `command.upgrade(cfg, "head")` against a temp SQLite path. No multi-head branches.

---

## Conventions that emerged in code (not fully restated in docs)

### Transport split is total

`MCP_AND_API` is **empty**. Every operation is deliberately MCP-only or API-only (`wiring.py`). Adding an op to both would be a regression of the transport rule, not a convenience. Human authority ops (dispatch, approve, answer suspension, cancel, agenda decisions, operator open questions) never appear on MCP.

### Governed operation shape

- One Pydantic in/out model per service function; transports only map paths/bodies.
- Path params + body: service input is complete (`run_id` + fields); HTTP body models omit path fields (`AnswerSuspendedRunBody`, `DecideOpenQuestionBody`, `CreateOperatorOpenQuestionBody`).
- `connection_scope` = one transaction per service call (`engine.begin()`). Compose two service calls = two transactions.
- Refusals: `DeskRefusal` → HTTP **always 409** with five fields; MCP tool error via `raise_tool_refusal`. Idle/empty is success (`claim_next_run` → `run: null`), not a refusal.

### Claim / lease choke points

- Mutative work tools: `validate_and_refresh_claim` (claimed + token + unexpired lease → refresh).
- Suspend: `validate_claim(..., refresh=False)` then clear lease (no pointless write).
- `read_case_context`: `validate_claim(..., allow_suspended=True, refresh=True)` — suspended has no lease to refresh; claimed refreshes.
- Atomic status flips: conditional `UPDATE ... WHERE status=X AND claim_token=Y`; `rowcount != 1` → `RUN_CLAIM_STALE`.
- Token compare: `hmac.compare_digest`.
- Reclaim: only `status=claimed` with expired lease → `approved`, clear token/lease. **Suspended is never reclaimed by lease** (no lease while waiting). Escape hatch: human `cancel_run`.
- `reclaim_expired_leases` is also called from **list/approve/cancel** (lazy evaluation). `list_runs` mutates as a side effect — documented in `lease.py` module docstring; do not “clean up” without moving expiry elsewhere.
- `cancel_run` calls reclaim first so a page-stale claimed→approved run does not refuse oddly; **does not** change capture examination status (deliberate; only `close_run` + explicit ids).

### Projection vs history

Pattern established twice: **history is never the projection.**

- Suspensions: durable `run_suspensions` rows; `runs.suspension_*` / `human_answer` are latest-only rendering.
- Open questions: durable rows; run-close view lists them by run; case lists all.

### Close / examined (ticket 08 — easy to re-break)

- `examined_capture_ids` on `close_run` is the only path to `examined`. Uncited + omitted stays `unexamined`. Cited cannot be reported examined (`EXAMINED_CAPTURE_ALREADY_CITED`).
- Captures start `unexamined`; `propose_claim` promotes bound captures to `cited`.
- Operator agenda authority: `create_operator_open_question` works with **empty** proposed list (D5/F-31). `decide` alone is not enough.

### Capture / Vault

- Quotation surface is `elements.text` (and `e/n/r/start-end` slices), not raw vault bytes.
- Budget counts **retained** captures only; failed fetch/SSRF does not consume budget.
- SSRF: resolve + block private; re-check on redirects.
- Locator map cap from settings; truncation ≠ examination.

### Client

- Thin fetch wrappers only for `/api`. No MCP from the browser.
- Run close UI order is product law (D13), not layout preference: agenda → counts → low confidence → fold. Claims in the fold carry “not for confirmation here.”
- Unconfirmed claims are visually loud on the case page (ADR 2).

### Tests

- Seam tests call service functions in-process with temp SQLite + migrations.
- MCP e2e: real uvicorn + MCP client for tool registration and selected flows.
- Enum drift: `tests/test_check_enums.py` parametrizes **all** CHECK enum columns vs Python frozensets. Extend that list when you add a CHECK — do not invent a third per-table pattern. Reject-unknown integrity tests remain elsewhere for some columns.

### Commands that exist

```bash
uv run pytest
uv run ruff check src tests
# app factory: create_app; client Vite under client/
```

No elaborate Makefile; AGENTS.md “Commands” block was left thin intentionally.

---

## Open threads (do not forget on ticket 09+)

1. **`read_case_context` is thin** — claims/captures/open questions yes; “prior angles / full case narrative” still stubs. Grow ticket by ticket; do not invent a second executor read tool.
2. **Inference → publication_risk inheritance** — noted F-24 in `claims.py`: ticket 11 must close before confirmation/use.
3. **`abandoned` status** — in CHECK vocabulary; reclaim path uses `approved` + cleared token, not transition to `abandoned`. Do not invent abandoned transitions without doctrine.
4. **Lead capture identity** — ticket 09 requires leads and runs to produce **identical capture records** for the same URL (same store/hash/parse). Factor shared capture write path if `capture_url` is still run-bound; leads have no claim_token/run. Schema today ties `captures.run_id` NOT NULL — **likely needs nullable run_id or a lead_id** and a migration. Design this before forking fetch code.
5. **Auth-walled / identity-only leads** — distinct from SSRF-blocked; product state “not captured” is not the same as fail-closed SSRF refuse.
6. **No `add_lead` on API-only by default** — tool surface lists `add_lead` as an executor tool in D15, but lead *inbox* operator actions (attach/promote/dispose) are human. Split carefully like suspend vs answer.
7. **Review files** — only `review-01` and `review-02` under `.scratch/first-destination/`; later F-findings were closed in-session without always writing `review-NN.md`. Do not assume missing review file means missing decision.

---

## Current MCP tool set (8-tool doctrine; subset live)

Registered today (`mcp_tool_names()`):  
`claim_next_run`, `read_case_context`, `capture_url`, `read_capture`, `propose_claim`, `suspend_run`, `close_run`  

Still not implemented from the fixed surface: **`add_lead`** (09), and anything after. Do not invent a ninth production tool for problems already solvable by extending `read_case_context`.

---

## Ticket 09 focus cues

- Same Vault path as ticket 04 — extract shared “write capture from bytes” if needed; do not copy SSRF/parser.
- Lead holds material, never claims until case attachment + run work (D10).
- Tests must assert identical capture record shape for lead drop vs run capture of same URL.
- Human ops for attach / promote / dispose on `/api`; `add_lead` placement per ADR tool surface (likely MCP, but confirm D10/D15 against operator inbox UX — inbox drop may be browser-only; reconcile product text with transport rule before coding both).

---

## What the last session did *not* do

- Did not start ticket 09.
- Did not leave uncommitted work after `c53e240`.
- Did not reconstruct retrospective commits for 01–06 (single foundation checkpoint by design).
