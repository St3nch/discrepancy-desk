# Review — Ticket 01 (backend and MCP tool surface skeleton)

**Date:** 2026-08-05
**Reviewer:** Claude, out-of-loop, via filesystem access
**Scope:** `src/desk/`, `alembic/`, `tests/`, `client/` as implemented for ticket 01
**Verdict:** Accept. Findings 1 and 2 to be fixed before ticket 02; 3–5 whenever.

This is the precedent-setting review. Ticket 01 establishes conventions the remaining
thirteen tickets inherit, so the bar here is higher than the code's risk warrants.

---

## Standing checks, results stated explicitly

A silent clean pass is indistinguishable from a check that was never run.

| Check | Result |
|---|---|
| Vocabulary reconciliation | One finding (F-01) |
| Fail-open inventory | One finding (F-02) — the significant one |
| Destructive-write inventory | **Clean.** No multi-column updates exist; inserts only |
| Dead-capability inventory | One finding (F-03) |
| Write-once inventory | N/A — no append-only chains yet |
| Projection completeness | N/A — no governed decisions surfaced yet |

---

## What holds

**`wiring.py` is better than the ticket specified.** Transport separation was required as a
discipline; it was implemented as an explicit registry with three named sets. Adding a
human-only operation to `MCP_AND_API` now reads as an obvious mistake, which was the stated
goal.

**The MCP e2e test asserts `ensure_probe_parent not in names`.** That converts the transport
boundary from a convention into an enforced one. This is the single most important test in
the ticket.

**The refusal test asserts absence.** Checking for `Traceback`, `sqlite3`, and
`IntegrityError` proves what does not leak rather than only what does. Correct shape.

**Tests run real Alembic migrations, not `metadata.create_all()`.** The STRICT test therefore
tests the real schema path.

**Governed operation signature landed as specified.** Pydantic input model, Pydantic output
model, typed refusal raised from the service and rendered by both transports.

---

## Findings

### F-01 — STRICT lives only in the migration, not in the Core metadata

**Severity:** Medium

`db/schema.py` and `alembic/versions/0001_probe_tables.py` are two definitions of the same
tables. Only the migration carries `STRICT`.

Nothing calls `metadata.create_all()` today, so this does not currently bite. But if Alembic
autogenerate is used against that metadata, it emits non-STRICT tables — silently, with no
error and no test failure, because the existing STRICT test only covers tables the current
migration created.

This is the vocabulary-reconciliation class exactly: the same controlled property defined in
two places, agreeing today, with no mechanism preventing divergence.

**Fix:** a test that queries `sqlite_master` and asserts every table carries `STRICT`,
regardless of how it was created. That holds under autogenerate, `create_all`, and
hand-written migrations alike.

### F-02 — Pragmas are applied but never verified

**Severity:** Medium-high. This is a fail-open in the storage layer.

```python
cursor.execute("PRAGMA foreign_keys=ON")
cursor.execute("PRAGMA journal_mode=WAL")
```

Neither statement raises on failure. `journal_mode=WAL` returns the *resulting* mode and
silently remains `delete` where the filesystem cannot support WAL — network mounts, some
container volumes. `foreign_keys=ON` fails silently if issued inside a transaction.

The pragma tests catch this on a tmpdir. Production is unverified.

The docstring on this function states the reason the pragma exists: SQLite defaults
`foreign_keys` off, which is a fail-open in the storage layer. Not checking that the pragma
took is the same failure one level up — the guard is present but its firing is unconfirmed.

**Fix:** read both pragmas back after setting them and raise if they are not what was asked
for. Four lines, in the one place every connection passes through.

### F-03 — `api_operation_names()` is dead, and the API has no registration guard

**Severity:** Low-medium

`mcp_tools.py` validates registered tool names against `mcp_tool_names()` and raises on
mismatch at startup. There is no equivalent for the API transport, and
`api_operation_names()` has no call site anywhere.

`API_ONLY` is therefore currently decorative. Nothing detects an API route added for an
operation not present in `wiring.py`.

**Fix:** either add a test asserting every registered API route maps to a name in
`api_operation_names()`, or delete the function. An unused registry that looks authoritative
is worse than no registry — a later reader will assume it is enforced.

### F-04 — `server._tool_manager` is private API on a beta SDK

**Severity:** Low, but act on it now

The registration check reaches into `server._tool_manager.list_tools()`. The MCP Python SDK
2.x is in beta and ships breaking changes between alphas; if that attribute moves, the app
raises at startup.

The check itself is worth keeping and failing closed at startup is correct behaviour.

**Fix:** pin `mcp` to an exact version rather than a floor constraint.

### F-05 — Dead code to silence a linter

**Severity:** Trivial

```python
_tools: list[Callable[..., Any]] = [record_probe_note_tool, list_probe_notes_tool]
del _tools
```

Delete it and configure ruff instead.

---

## Conventions to record rather than fix

**All refusals render as HTTP 409.** This is defensible and arguably better than mapping
refusals to varied HTTP statuses — the `code` carries the meaning, and a second weaker signal
would invite callers to switch on the wrong one. But it is an undocumented convention that
thirteen tickets will inherit. It belongs in `codingstandards.md`.

**`connection_scope` is `engine.begin()`, so every service call is its own transaction.**
Correct for ticket 01. It means two service calls cannot share a transaction, which will
matter the first time an operation needs to compose others atomically. Not a defect; a shape
to know about before it surprises someone.

---

## Not reviewed

The browser client was not read in depth. Ticket 01 requires only that it hold no privileged
logic, and the API surface it calls is governed by definition. A closer read is warranted
when the client starts rendering governed state rather than probe rows.
