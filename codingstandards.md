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

**Database access.** SQLAlchemy Core, not the ORM. `STRICT` tables. `PRAGMA foreign_keys=ON`
and WAL set per connection. A new connection path that does not set the pragma is a defect,
not a style issue — SQLite defaults it off and foreign keys then silently do not enforce.

**Transport separation.** Human-only operations are wired to `/api` only and must never
become reachable from `/mcp`. Adding one to the MCP surface should read as an obvious mistake.

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
