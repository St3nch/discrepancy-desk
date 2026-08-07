# Coding Standards

What `/code-review`'s Standards axis reads. Also worth reading before writing code — most of
this exists because the previous build of this project failed on it specifically.

Three sections. The first is fixed conventions, the second is the seam checks, the third is
general smells. The first two are project-specific and non-negotiable. The third is ordinary
craft.

---

## 1. Fixed conventions

Established in ticket 01 and inherited by everything after it.

**Governed operation signature.** Every service function takes a Pydantic input model and
returns a Pydantic output model. Refusals raise typed exceptions; transports catch and
render. Loose keyword arguments are a defect — they let a caller's idea of the arguments and
the service's idea drift apart silently, which is precisely how the previous build failed.

**No partial-update operations.** Every update takes a complete, explicit model. Absent keys
are never resolved to NULL. **If a service writes a column, its input model has a field for
it.** No exceptions.

**Refusal contract.** `DeskRefusal` carries `code`, `what_happened`, `what_was_preserved`,
`what_was_not_changed`, `what_you_can_do`. Never a raw driver error, never a stack trace, at
either transport. The `code` must be specific enough that an executor can self-correct —
`QUOTE_MISMATCH` and `LOCATOR_UNRESOLVED` and `BUDGET_EXHAUSTED` lead to different next
actions by a model, so they must be different codes.

**MCP tool boundary is three categories (ticket 12a).** The intercept is at tool
**dispatch** (not only the body decorator), so framework argument validation is covered
while schemas stay intact:

1. `DeskRefusal` — five-field envelope, code unchanged (actionable domain refusal).
2. Framework argument validation failure — `TOOL_ARGUMENT_INVALID`, actionable: names
   the parameter and what was expected. Missing keys, wrong types, nulls. An unlearnable
   framework error here is F-54 in a new costume.
3. Anything genuinely unexpected — `TOOL_INTERNAL_ERROR`, non-correctable, no internals
   leaked, loud in the logs.

A blanket wrapper that dresses every failure as an actionable refusal is F-17 one level
up: an executor will loop trying to "fix" a programming error while the bug stays
invisible. Do not re-label domain codes inside a broad `except Exception`. Tests of the
envelope must go through the registered dispatch path, not `tool.fn` (which bypasses
validation).

**HTTP refusals are always 409.** Domain refusals render as HTTP 409 with the five-field
body. The `code` carries the meaning; do not map different refusal codes to different HTTP
statuses. A second, weaker signal invites callers to switch on the wrong one. Request-shape
validation (Pydantic/FastAPI) stays 422 — that is not a `DeskRefusal`.

**Database access.** SQLAlchemy Core, not the ORM. `STRICT` tables. `PRAGMA foreign_keys=ON`,
WAL, and `busy_timeout` set per connection **and verified by reading them back** — setting
without confirming is a fail-open one level up. A new connection path that does not set and
verify the pragmas is a defect, not a style issue — SQLite defaults foreign_keys off and
busy_timeout to 0 (fail immediately on contention). Exhausted busy_timeout surfaces as
`DeskRefusal` with code `DATABASE_BUSY` (retryable), never as a raw driver error.

**Empty result for expected absence; refusal for failure.** When an operation is
legitimately idle or has nothing to return — e.g. `claim_next_run` with no approved run —
return a successful empty payload (`run=None`, empty list), not a `DeskRefusal`. Refusals
are for failures the caller should correct or stop on. Polling and run-close tools will hit
the idle path constantly; treating it as an error forces every quiet poll through the
self-correction path.

**One brand per deployment (D17).** No `account_id` column, no account scoping in queries,
and no account-aware projection. A second editorial brand is a separate process: separate
database, separate Vault, separate config, same code. Do not reintroduce an in-instance
account boundary — it must hold in every query forever, and its failure is silent.

**Read refusals.** For `DeskRefusal` on read operations, `what_was_not_changed` states
plainly that nothing was written (e.g. `"Nothing was written."`), not a garbled claim about
what was or was not "read as missing."

**Migrations are tested against populated databases, not only empty ones.** Test
migrations run against a fresh database, where foreign key enforcement never fires because
no row exists to violate it. Any migration that rebuilds a table with inbound foreign keys
— the SQLite create-copy-drop-rename pattern — gets a test that populates the prior revision
with representative dependent rows, upgrades to head, and asserts the upgrade succeeds, the
dependent rows survive, and new columns hold the intended value for legacy rows. A rebuild
that passes on an empty database has not been tested; it has been skipped.

**Seam tests cross operations, not only layers.** Every defect that has broken this project
has been *operation A changes what operation B reports* — a capture attached by one path
that another path cannot see, a status set by one operation that another infers
differently. Tests that exercise one service function with fixture data will not find
these, because each function is individually correct. When an operation changes state that
another operation reads, test the pair in sequence and assert what the second one reports.

**One transaction per service call.** `connection_scope` is `engine.begin()`. Each governed
service function runs in its own transaction. Composing two service calls is two
transactions — not atomic across the pair. If a later operation needs multi-step atomicity,
that is a new shape (one service function owning the whole unit of work), not nested
`connection_scope` calls sharing a connection by accident.

**Transport separation.** Human-only operations are wired to `/api` only and must never
become reachable from `/mcp`. Adding one to the MCP surface should read as an obvious mistake.

**Quotation surface is `elements.text`, not raw Vault bytes (F-13 / ADR 9 / F-22).**
`propose_claim` verification that `quoted_text` appears "byte-exact at the locator" means
exact equality against the resolved quotation surface — not a raw byte range of the
immutable Vault object, and never a fuzzy/normalised match. Locators:

- `e/{n}` → full `elements.text` for that ordinal
- `e/{n}/r/{start}-{end}` → `elements.text[start:end]` (end exclusive)

Raw bytes remain the archival record and integrity anchor (SHA-256). The parser derives
element text; that derived text (or a slice of it) is the only surface verification checks.

**Capture budget counts retained captures, not failed fetches (F-15).** A failed fetch
(timeout, DNS, HTTP error, SSRF block) does not consume a run capture-budget slot. Budget
bounds how many Vault captures a run may *keep*, not how many HTTP attempts it may make.
Retrying a broken URL is wall-clock limited, not budget-limited — preferred so flaky sites
do not burn the operator's declared capture allowance before any material is stored.

---

## 2. Seam checks

The previous build's defects were, without exception, contract drift *between* layers rather
than failures *inside* one. Every layer's tests were individually green. Run these against
any diff that crosses a layer boundary.

**Vocabulary reconciliation.** For every controlled value existing in more than one place —
a migration `CHECK` constraint, a Python enum or frozenset, a hardcoded option list or
default in the client — confirm all of them agree exactly. Check field *type* as well as
values: a free-text input standing in for what the schema treats as an enum is worse than a
stale dropdown default, because the operator can submit anything.

**Fail-open inventory.** For every guard whose enforcement depends on a joined row existing,
ask what happens when the relationship is *absent* rather than merely unclassified. A loop
over zero rows that emits no warning is fail-open. In a system whose purpose is
publication-risk gating, a fail-open guard is not an edge case — it is the mechanism not
firing.

**Destructive-write inventory.** For every service function performing an update that writes
more than one column, list the columns it writes and the fields each caller supplies. Diff
them. A caller omitting a field the service unconditionally overwrites is a silent data-loss
path. "The form only asked about status" does not mean status is the only thing it changed.

**Dead-capability inventory.** For every service function and every client method, find a
call site. A pair with zero call sites is either genuinely unneeded or a governed action the
operator has no way to perform. The follow-up question decides severity: does the accepted
operator loop require it? If yes, blocker. If it is explicitly deferred or would collide with
a decided boundary, correctly out of scope — leave it alone rather than "fixing" it.

**Write-once inventory.** For every append-only chain, confirm three things independently:
the service refuses a second decision naming a stale or absent head, the projection returns
the current head, and every call site actually sends it back. A chain can enforce append-only
perfectly and still be write-once in practice because the caller never round-trips the ID the
projection handed it.

**Projection completeness.** For every governed decision the operator can make, confirm the
operator can also *read* its current state through the same projection that renders the form
used to make it. Overlaps with write-once by construction; check it independently, because a
projection can be complete for display while the write path still fails to round-trip.

**A clean check is worth stating explicitly in review output.** "Ran the vocabulary sweep
across all N enum columns, found no mismatches" — because a silent clean pass is
indistinguishable from a check that was never run.

---

## 3. Smells

Ordinary craft. Named because naming them is most of the work.

- **Mysterious name** — a name that does not say what the thing is. In this codebase, also
  check it against `CONTEXT.md`: using `post` where the glossary says `rendition`, or
  `verified` where it says `confirmed`, is a mysterious name even if it reads fluently.
- **Feature envy** — a function more interested in another object's data than its own.
- **Data clumps** — the same three or four values travelling together everywhere. Usually
  wants to be a model, which here it can be, since every operation already takes one.
- **Primitive obsession** — a bare string where a locator, a capture id, or an evidence
  dimension belongs. This one matters more than usual: the evidence dimensions are enums with
  fixed values, and a bare string defeats the constraint.
- **Repeated switches** — the same conditional over the same type in several places.
- **Divergent change** — one module changed for many unrelated reasons.
- **Speculative generality** — machinery for a case that does not exist. Especially relevant
  here: the fog items are deliberately unresolved, and building for them in advance is
  guessing dressed as foresight.
- **Message chains** — `a.b().c().d()`.
- **Middle man** — a class that only delegates.

---

## What this document is not

Not an audit ceremony. The previous project accumulated 99 audit files and 131 planning
packages and never published a post from the system it was documenting. These are checks a
reviewer runs against a diff, not artifacts that generate paperwork.

A finding is real once reproduced against the code. Absence of evidence is a valid finding.
