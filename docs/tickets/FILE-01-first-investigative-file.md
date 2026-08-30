# FILE-01: First real investigative File

**Status:** draft — awaiting CHAZ selection of the real-world subject for `DD-0001`

**Owner:** Project Steward

**Designated Writer:** TBD after ticket reconciliation

**Implementation start commit:** TBD. Implementation must start from the exact clean authority commit accepted by the Steward.

**Blocked by:** CHAZ selects the subject of `DD-0001`. No other foundation program is a prerequisite.

## Goal

Turn the Desk from a foundation repository into a usable investigative product by completing one real internal tracer-bullet File with real source material and evidence walkback.

This ticket is intentionally **not** the website, Quinton, X/social, autonomous research, a public publication workflow, a generic notebook, or a complete implementation of every noun in Foundation Model v2.

## Required end-to-end behavior

The accepted implementation must support one real File, `DD-0001`, through this path:

```text
File
  → Capture / Artifact / Surface / Locator
  → Observation
  → Claim
  → human Decision
  → File-scoped Discrepancy
  → living internal report
  → evidence walkback
```

The Writer should implement only the schema, storage, operations, and operator-readable surface required to make that path real.

## Scope

### 1. Open the first File

- Create one durable File with public/tool-facing ID `DD-0001` and a separate internal storage identity.
- Treat Foundation Model `Case` references as this same File concept; do not create both objects.
- Domain/topic classification may be stored only if the real subject needs it. Domain is not identity.

### 2. Capture real sources

- Manually acquire at least 2–3 real sources relevant to `DD-0001`.
- Each acquisition creates a Capture receipt.
- Preserve immutable source bytes/material as Artifacts in the smallest truthful Vault shape needed by this slice.
- Create a frozen inspectable/citable Surface and durable Locator shape sufficient for the admitted Observations.
- A later acquisition of the same source creates a new Capture receipt. If bytes are identical, Artifact deduplication is allowed; the prior Capture must never be overwritten.
- Do not build scheduled monitoring, Wayback-scale automation, or provider acquisition machinery.

### 3. Admit source-local Observations

- Admit source-local Observations only from preserved/citable material.
- Each Observation must walk back to the exact preserved source version and Locator used to support what the source presents.
- Observation means “this source presents X,” not “X is true.”

### 4. Represent Claims without laundering source assertions

- Create at least one durable Claim relevant to the File.
- Where the real sources disagree, preserve competing Claims/positions rather than forcing premature reconciliation.
- An Observation may support or contradict a Claim but may not silently set Claim posture or human judgment.

### 5. Exercise a human-only Decision

- Record at least one explicit human Decision acting on an exact durable Claim/version.
- The implementation must contain no model/Run path that can impersonate that human Decision.
- The Decision must preserve prior state/lineage rather than rewriting history.

### 6. Create the first durable Discrepancy

- Create `DD-0001 / D01` for a genuine unresolved tension/question surfaced by the investigation.
- Persist only the minimal durable shape: ID, concise question/description, current lifecycle state, supporting Record references, and update history.
- D01 is an investigative handle, not a Claim posture, truth score, proof of conspiracy, or node in a global discrepancy graph.

### 7. Render a living internal report

- Provide an operator-readable current File report/projection generated from durable state.
- It must visibly distinguish source presentation/Observation, Desk-level Claim, human Decision, and unresolved Discrepancy.
- It must not require a fake `Conclusion` when the File remains unresolved.
- Do not hard-code the full future public report section list as a schema or workflow engine.

### 8. Prove evidence walkback

From material shown in the living report, the operator must be able to walk back through the relevant durable objects to the exact captured source version/Locator.

At minimum, the implementation/review must demonstrate:

```text
report statement
  → Claim / Observation / Discrepancy reference
  → Observation / Excerpt or equivalent bounded evidence selection
  → Locator
  → Surface
  → Artifact
  → Capture receipt
```

## Storage and application boundary

- PostgreSQL 18 is the authoritative structured Record store per ADR-0001.
- Vault payload authority remains distinct from PostgreSQL structured Record state.
- The FND-PG01 proof environment is not the application package and its scratch SQL is not a production migration.
- The Writer must propose the smallest application/module and migration/bootstrap shape needed for this slice during pre-implementation review. Do not reopen the PostgreSQL decision or select a public UI framework merely because one will eventually be needed.

## Explicitly out of scope

- public website or public File page;
- Quinton Renditions/articles/posts;
- X API, Chrome extension, reply drafting, posting, or social metrics;
- autonomous research dispatch;
- full Workspace/notebook application;
- Entity merge/split system unless the chosen File makes identity resolution unavoidable;
- global discrepancy ontology/graph;
- embeddings, semantic retrieval, graph database, universal FTS layer;
- complete publication/revision/corrections workflow;
- another reusable PostgreSQL foundation/fixture program;
- implementing every Foundation Model noun because it exists in design material.

## Acceptance behavior

- [ ] `DD-0001` exists with stable public identity and separate internal identity.
- [ ] At least 2–3 real sources are captured through the implemented path with immutable source-version provenance.
- [ ] A recapture creates a new Capture receipt without overwriting prior acquisition history.
- [ ] At least one admitted Observation resolves to exact preserved material through a durable Locator.
- [ ] At least one Claim is represented separately from source-local Observation.
- [ ] At least one human-only Decision is durably recorded without a model-authority path.
- [ ] `DD-0001 / D01` exists as a minimal File-scoped investigative handle with supporting Record references/history.
- [ ] The living internal report visibly distinguishes what sources present, what the Desk represents as Claims, what the human decided, and what remains discrepant/unresolved.
- [ ] Demonstrated report-to-Capture walkback succeeds for representative material.
- [ ] The implementation adds no website, Quinton, X/social, autonomous publication, global graph, or unrelated foundation machinery.
- [ ] Ticket-appropriate automated tests defend the real authority/provenance/lineage seams rather than reproducing the old foundation proof program.

## Pre-implementation review questions

Before mutation, the designated Writer must inspect the accepted authority and answer only the technical questions needed to make this slice implementable:

1. What is the smallest application/module boundary required now that `pyproject.toml` is explicitly proof-only?
2. What minimal production migration/bootstrap mechanism should this first PostgreSQL slice use, and why is it no broader than FILE-01 needs?
3. What exact Vault payload shape is sufficient for the chosen 2–3 real sources while preserving immutable source versions and durable Locators?
4. Where is the human-Decision authority seam enforced so no model/Run path can invoke it?
5. Show the proposed report-to-Capture reverse walkback before implementation and identify every durable relation it requires.
6. Identify any requirement above that the chosen real-world subject makes dishonest or impossible, rather than silently substituting toy data.

The Steward reconciles those answers before accepting the final implementation ticket and pinning the Writer start commit.

## Deferred capability record

**Intent:** A living investigative reference system that can eventually publish canonical Files and many Quinton renditions while preserving exact evidence/provenance history.

**This slice:** One real internal File from source capture through Observation/Claim/human Decision/Discrepancy to a living report with walkback.

**Deferred:** public website, publication snapshots/corrections UI, Quinton content, X/social acquisition and metrics, scheduled source monitoring, broad Workspace UX, graph/semantic retrieval, autonomous candidate discovery.

**Promote when:** a real File exposes the need (`real-use`), public launch requires it (`post-MVP`), or a later idea remains merely possible (`not committed`).
