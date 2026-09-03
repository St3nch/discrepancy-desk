# The Discrepancy Desk

The Discrepancy Desk is a local, single-operator investigative and research system for
preserving source material, separating what sources present from what the Desk claims,
tracking discrepancies and unresolved questions, and producing accountable living
investigative Files.

The Desk investigates subjects without requiring belief or disbelief. It shows its work,
keeps competing explanations visible, and leaves final judgment with the audience.

## Current status

The repository is the active Discrepancy Desk rebuild and the sole Product and development
authority for the project.

The PostgreSQL 18 foundation checkpoint, FND-PG01, is complete and accepted. It proved
selected admission, historical identity, conflict/supersession, and provenance traversal
behavior against disposable PostgreSQL. It did not create a production schema or
migration.

The active milestone is FILE-01: the first real investigative File. No additional generic
foundation program is pending.

## Read first

Authority for agents and humans:

1. `VISION.md` — Product purpose, boundaries, evidence doctrine, and current milestone.
2. `CONTEXT.md` — canonical Desk vocabulary.
3. `decisions/decisions.md` — settled Product and project decisions.
4. `decisions/deferred.md` — useful directions deliberately left unbuilt.
5. `AGENTS.md` — roles, authority order, work method, and external-effect gates.
6. `codingstandards.md` — implementation and review discipline.
7. the relevant accepted ticket under `docs/tickets/`.
8. relevant accepted ADRs under `docs/adr/`.
9. relevant accepted specifications under `docs/specs/`, when present.

`docs/design/` preserves non-authoritative Foundation Model v2 workshop and proof-design
material. It may inform a proposal but cannot override the authority above.

## Repository shape

```text
VISION.md                     Product purpose and boundaries
CONTEXT.md                    canonical domain language
decisions/decisions.md        settled Product/project decisions
decisions/deferred.md         deliberately unbuilt work and triggers
AGENTS.md                     authority and development method
codingstandards.md            code and test discipline
docs/adr/                     accepted technical decisions
docs/specs/                   accepted normative contracts, created when needed
docs/tickets/                 bounded implementation work
docs/design/                  non-authoritative foundation workshop/history
tools/postgres_foundation_proofs/
tests/proofs/                 completed FND-PG01 proof harness
```

Directories are created only when they have real content. There is no sibling Desk
authority repository.

## Canonical investigative path

```text
File
  → Capture / Artifact / Surface / Locator
  → Observation
  → Claim
  → human Decision
  → File-scoped Discrepancy
  → living internal report
  → exact evidence walkback
```

Original documents, images, audio, and video remain evidence authority. OCR, transcripts,
extracted frames, normalization, and enhancement are derived Surfaces with explicit
lineage; they never silently replace the original.

## Active File

The first real File is `DD-7225`, concerning the Rendlesham Forest incident of December
1980.

The working investigation question is:

> What does the contemporaneous record establish about the Rendlesham Forest incident,
> how did the story change in later retellings, and which reported details remain
> unexplained after the strongest conventional explanations are considered?

FILE-01 uses a small real document-and-audio corpus to prove Capture, source-local
Observation, separate Claim, human Decision, File-scoped Discrepancy, living report, and
report-to-evidence walkback.

`DD-7225` is a non-semantic, non-sequential archival filing number. It does not state
creation order, File count, Domain, priority, or truth.

## Current work boundary

FILE-01 is a draft awaiting technical pre-implementation reconciliation against the real
corpus and existing code seams.

It does not include a public website, Quinton production, X/social tooling, autonomous
research, broad Workspace UX, a universal ontology, graph-as-truth, general OCR or media
processing, or another reusable PostgreSQL foundation program.

Strategy Layer is outside the active Desk Product scope.

## Development

Use the governed VedaOps project surface for repository work. Current configured checks
are:

```text
format-check
lint
test
postgres-foundation-proofs
```

No ticket means no implementation. Any capable available model may perform a bounded task,
but Codex remains the VedaOps Project Steward and CHAZ remains Product Owner. Nothing is
pushed without fresh explicit CHAZ authorization.
