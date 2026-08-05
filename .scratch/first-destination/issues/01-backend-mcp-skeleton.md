# 01 — Backend and MCP tool surface skeleton

**What to build:** A running backend service with a real datastore, exposing an MCP server
with at least one working tool call, reachable end-to-end from an actual MCP client. A
minimal browser client can reach the backend and render something real (not a static page)
sourced from the datastore. This is the transport skeleton every later tool-surface call and
every human-facing operation builds on — no editorial behavior yet.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent

---

## Read this first

This ticket is precedent-setting, not scaffolding. The conventions it establishes are
inherited by all thirteen remaining tickets. Three of them are fixed below and are not open
for an implementer to choose differently; each exists because the previous build of this
project failed on it specifically.

The rest of the stack — layout, tooling, build config — is ordinary and can be decided
sensibly by whoever builds this.

---

## Fixed conventions

### 1. Governed operation signature

Every service function takes a Pydantic input model and returns a Pydantic output model.
Refusals raise typed exceptions. Transports catch and render them.

```python
def propose_claim(session: Session, params: ProposeClaimInput) -> ProposeClaimResult:
    ...  # raises DeskRefusal
```

Not loose keyword arguments: those let a caller's idea of the arguments and the service's
idea drift apart silently, which is the exact defect class that broke the previous build.
A named input model turns that drift into a type error.

Not a Result union: it works, but every caller must remember to check it, and forgetting is
silent. An uncaught exception is loud.

**No partial-update operations.** Every update takes a complete, explicit model. Absent keys
are never resolved to NULL. In the previous build, a review-status form submitted without
notes caused the service to write all four columns in one statement and silently null a
populated note field. The structural fix: **if a service writes a column, its input model has
a field for it.**

### 2. Refusal contract

One exception base carrying five fields:

```python
class DeskRefusal(Exception):
    code: str                 # stable, machine-readable
    what_happened: str
    what_was_preserved: str
    what_was_not_changed: str
    what_you_can_do: str
```

Never a raw SQLite error. Never a stack trace. At either transport.

The `code` is what lets an executor self-correct rather than stall. When `propose_claim`
rejects a quote, the response must say which verification step failed — `QUOTE_MISMATCH`,
`LOCATOR_UNRESOLVED`, and `BUDGET_EXHAUSTED` lead to completely different next actions by a
model.

**Refusal is the default.** Where a check depends on a joined row existing, an empty result
produces an explicit "unknown, treat as unresolved" — never a silent pass. In the previous
build, a person-risk inheritance loop iterated over zero rows and emitted no warning, which
read as "no risk" when it actually meant "the check never ran."

Refusals are the enforcement in this system, not an edge case. `propose_claim` rejecting a
bad quote is the product working correctly.

### 3. Database access

**SQLAlchemy Core — not the ORM — with Alembic.**

Not the ORM: the Record is full of append-only chains and supersedes pointers. The identity
map and lazy loading fight append-only semantics and obscure when writes actually happen.
The previous build's write-once defects were about whether the write path round-trips the
current head ID; that must be visible in the code, not managed on your behalf.

Not raw `sqlite3`: hand-written SQL strings across fourteen tickets is where typos live, and
there is no clean metadata for Alembic to autogenerate against.

Three settings that are cheap now and expensive later:

- **`PRAGMA foreign_keys=ON` on every connection.** SQLite defaults this **off**, so foreign
  key constraints silently do not enforce. That is a fail-open in the storage layer itself.
- **`STRICT` tables**, so column types are actually enforced.
- **WAL mode.**

---

## Toolchain

`uv`, `ruff`, `pytest`. Python backend, TypeScript browser client, per ADR 10 and
`decisions/stack.md`.

---

## Acceptance criteria

- [ ] Backend process starts, connects to a real (not mocked) datastore, and persists data
      across restarts.
- [ ] An MCP client can call at least one tool exposed by the backend and receive a response
      built from a real backend round-trip (not a stub).
- [ ] A minimal browser client can load and display data served by the backend.
- [ ] The backend/browser-client boundary holds no privileged logic in the client — the
      client calls governed backend operations only.
- [ ] A test exists at the seam agreed in the spec (in-process governed-operations layer) for
      the one implemented tool call, plus one end-to-end test exercising the real MCP
      transport.
- [ ] The one implemented operation demonstrates the governed operation signature: Pydantic
      input model, Pydantic output model, typed refusal.
- [ ] `DeskRefusal` exists with all five fields, and both transports render it without
      leaking internals. A test asserts that a refusal reaches the caller with its `code`
      intact and no stack trace or driver error text.
- [ ] SQLAlchemy Core and Alembic are in place with a first migration. Tables are `STRICT`.
      `foreign_keys=ON` and WAL are set per connection, with a test proving a foreign key
      violation is actually rejected.
- [ ] Toolchain is `uv`, `ruff`, `pytest`.
- [ ] **A commands block is added to `AGENTS.md`** listing the real typecheck, test, lint,
      and run commands for this project. Write it from what was actually created — it could
      not be written before this ticket existed, and `/implement` will otherwise guess.
