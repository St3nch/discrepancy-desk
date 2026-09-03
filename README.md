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
src/discrepancy_desk/         FILE-01 application, migration, and operator commands
tests/desk/                   application and PostgreSQL 18 integration tests
data/                         ignored operator-selected Vault root when explicitly configured
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

Captured documents, images, audio, and video remain authoritative relative to Desk-derived
Surfaces. Capture provenance states whether an Artifact is an original, access copy, or other
known generation. OCR, transcripts, extracted frames, normalization, and enhancement retain
explicit lineage; they never silently replace the captured Artifact.

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

FILE-01's bounded application slice is implemented and proven against governed disposable
PostgreSQL 18. It provides the production migration, content-addressed Vault, evidence and
Record operations, capability-separated Decision path, living internal report, exact
walkback, and a small operator command surface.

No real File Record has been admitted by the implementation tests. Reacquiring the
accepted corpus onto the VPS, creating a persistent database and runtime credentials, choosing
the absolute Desk data root, admitting the first real Record, and recording CHAZ's exact first
Decision remain explicit runtime gates.

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

The installed operator surface is:

```text
uv run python -m discrepancy_desk --help
```

It deliberately performs no network acquisition. `capture` accepts an already-downloaded
local file and requires the accepted SHA-256, byte size, detected media type, and observed
page count or duration where applicable. It records the server-reported media type separately
from the detected Artifact type and refuses bytes that do not match the accepted digest and
size.

Runtime configuration fails closed:

```text
DESK_POSTGRES_URL          ordinary append/read capability
DESK_HUMAN_POSTGRES_URL    separate human-Decision capability
DESK_ADMIN_POSTGRES_URL    explicit bootstrap/migration authority
DESK_DATA_ROOT             absolute root for content-addressed Vault payloads
```

`bootstrap` creates non-login capability roles and applies the migration, but real bootstrap,
login credentials, and persistent storage remain CHAZ-authorized operational steps. The
current FILE-01 schema intentionally cannot mark source identity `verified`; it preserves
`unverified` or `contested` assertions until a durable verification seam is authorized.

No ticket means no implementation. Any capable available model may perform a bounded task,
but Codex remains the VedaOps Project Steward and CHAZ remains Product Owner. Nothing is
pushed without fresh explicit CHAZ authorization.
