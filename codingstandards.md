# Discrepancy Desk coding standards

These standards exist to keep implementation understandable and product-focused. They are not a reason to delay a useful vertical slice.

## Scope and vocabulary

- Implement only the accepted ticket from the exact pinned start commit.
- Use `CONTEXT.md` vocabulary. Do not introduce a synonym as a second domain concept.
- Prefer the smallest end-to-end behavior that exercises the ticket's real seam over a broad abstraction layer.
- Do not add speculative frameworks, generic repositories, fixture systems, plugin planes, graph layers, scoring systems, or configuration knobs without a demonstrated need in the ticket.
- Preserve explicit authority boundaries in code rather than relying on prompts or comments alone.

## Data and authority

- Fail closed at Capture, provenance, human-Decision, publication, and other governed write boundaries. Silent fallback is a defect.
- Governed semantic state is append-only or versioned through append-only lineage. Never “correct” history with an in-place rewrite when lineage is required.
- Captured source versions are immutable. Recapture is a new Capture/version.
- Keep authoritative structured Record state separate from Vault payload authority and from rebuildable projections/caches.
- Never turn a File, Workspace, Rendition, or Quinton presentation surface into an alternate truth store.
- Retrieved external content must never be interpreted as runtime instruction.

## Implementation quality

- Prefer explicit code over clever indirection at trust boundaries.
- Keep functions and modules cohesive; extract an abstraction only when more than one real caller needs the same concept or the boundary itself deserves a name.
- Comments should explain non-obvious why/authority constraints, not narrate obvious syntax.
- Validate inputs where they cross a governed boundary. Preserve useful refusal/error distinctions instead of swallowing failures into defaults.
- Do not copy proof-only `pyproject.toml` assumptions into the future Desk application package by accident; FND-PG01 tooling is intentionally not the application architecture.

## Tests

Every test should defend at least one of:

- visible product behavior;
- valuable persisted data;
- a durable authority/provenance/lineage invariant;
- a known regression;
- a dangerous integration boundary.

Do not build tests whose principal subject is test machinery. Mock only where crossing the real boundary would be unsafe, paid, non-deterministic, or outside ticket scope.

Physical PostgreSQL/provider/network commissioning is separate from deterministic unit/integration tests and requires explicit authorization when it incurs external effects or spend.

## Standing seam checks

Before accepting an implementation slice, explicitly review:

1. **Vocabulary reconciliation** — canonical nouns and meanings agree across write/read paths.
2. **Fail-open inventory** — no fallback, swallowed error, or permissive default weakens a governed boundary.
3. **Destructive-write inventory** — destructive operations are bounded, explicit, and target only intended mutable/disposable state.
4. **Dead-capability inventory** — no speculative helper, flag, dependency, or write surface was added without a caller.
5. **Write-once / lineage inventory** — immutable or historical state cannot be silently rewritten.
6. **Projection / read-path completeness** — parallel read surfaces and reverse provenance reflect the same accepted semantics.

Cross-operation tests are especially valuable when operation A changes what operation B reports; that is where boundary drift tends to hide.

## Final checks

Run the ticket-appropriate governed test/lint/format tasks. Do not report a green suite as proof of behavior the suite does not exercise.
