# FILE-01: First real investigative File

**Status:** draft — Product subject and File identity selected; awaiting verified initial source corpus and technical pre-implementation reconciliation

**Owner:** Project Steward

**Designated Writer:** TBD after ticket reconciliation

**Implementation start commit:** TBD. Implementation must start from the exact clean authority commit accepted by the Steward.

**Blocked by:** Verify and name the initial real source corpus, then complete the ticket's technical pre-implementation review. No other foundation program is a prerequisite.

## Goal

Turn the Desk from a foundation repository into a usable investigative product by completing one real internal tracer-bullet File about the Rendlesham Forest incident of December 1980, using real source material and evidence walkback.

This ticket is intentionally **not** the website, Quinton, X/social, autonomous research, a public publication workflow, a generic notebook, or a complete implementation of every noun in Foundation Model v2.

## Investigation binding

- **Public File ID:** `DD-7225`
- **Subject:** Rendlesham Forest incident, December 1980
- **Working investigation question:** “What does the contemporaneous record establish about the Rendlesham Forest incident, how did the story change in later retellings, and which reported details remain unexplained after the strongest conventional explanations are considered?”
- **Working D01 question:** “Which elements of the reported forest lights are not adequately accounted for by the known lighthouse/astronomical explanations?”

The investigation is not framed as either “Was it aliens?” or “Debunk Rendlesham.” The available Record may support mostly explained events, narrative growth, genuinely strange details, remaining unknowns, or a combination.

The D01 wording is an investigative starting question, not a predetermined conclusion. It may be reconciled against the verified corpus before this ticket is accepted.

## Required end-to-end behavior

The accepted implementation must support one real File, `DD-7225`, through this path:

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

- Create one durable File with public/tool-facing ID `DD-7225` and a separate internal storage identity.
- Preserve honest creation, admission, and revision metadata independently of the public filing number.
- Do not interpret `7225` as creation order, File count, Domain, priority, truth, or another investigative judgment. Future File IDs do not simply increment from this value.
- Treat Foundation Model `Case` references as this same File concept; do not create both objects.
- Domain/topic classification may be stored only if Rendlesham needs it. Domain is not identity.

### 2. Capture real sources

- Manually acquire a small verified corpus relevant to `DD-7225`.
- The minimum corpus must include:
  - at least one contemporaneous or official document;
  - the Halt audio recording from the best available source with documented provenance and provenance limits;
  - one additional verified item, preferably a genuinely useful contemporaneous image. If no suitable image can be authenticated, use another official/contemporaneous record and record the image gap rather than admitting dubious material.
- Each acquisition creates a Capture receipt.
- Preserve immutable original source bytes/material as Artifacts in the smallest truthful Vault shape needed by this slice.
- Create frozen inspectable/citable Surfaces and durable Locators sufficient for the admitted Observations. Text/document material may use bounded textual regions; audio requires time ranges; an admitted image may use the whole image or a bounded region.
- OCR, transcripts, frame extraction, normalization, and enhancement are derived Surfaces. Derived material must retain lineage to the exact original Artifact and must never silently replace or acquire the evidentiary authority of the original.
- An audio transcript may support search and inspection, but the recording remains authoritative. AI enhancement or reconstruction may not be treated as original evidence.
- A later acquisition of the same source creates a new Capture receipt. If bytes are identical, Artifact deduplication is allowed; the prior Capture must never be overwritten.
- Do not force video into this slice or build scheduled monitoring, Wayback-scale automation, provider acquisition machinery, or a general OCR/transcription/video-processing platform.

### 3. Admit source-local Observations

- Admit source-local Observations only from preserved/citable material.
- Each Observation must walk back to the exact preserved source version, media form, and Locator used to support what the source presents.
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

- Create `DD-7225 / D01` for a genuine unresolved tension/question surfaced by the investigation, beginning from the working question above and reconciling it against the admitted Record.
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

For audio-derived report material, walkback must continue through the transcript/inspection Surface and time-range Locator to the preserved recording Artifact and its Capture receipt. If an image is admitted, representative image material must likewise resolve through its whole-image or bounded-region Locator.

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
- general OCR, transcription, frame-extraction, or media-enhancement platform;
- video ingestion merely to check a media-type box;
- another reusable PostgreSQL foundation/fixture program;
- implementing every Foundation Model noun because it exists in design material.

## Acceptance behavior

- [ ] `DD-7225` exists with stable public identity, separate internal identity, and honest temporal metadata independent of its non-semantic filing number.
- [ ] A verified small corpus is captured through the implemented path, including at least one contemporaneous/official document, the Halt audio recording, and one additional verified item.
- [ ] The corpus records source provenance and material provenance limits rather than silently treating availability as authenticity.
- [ ] Original captured media remains evidence authority; each used derived Surface retains explicit lineage to it.
- [ ] A representative audio Observation resolves through a time-range Locator to the preserved recording. If an image is admitted, representative image material resolves through a whole-image or bounded-region Locator.
- [ ] A recapture creates a new Capture receipt without overwriting prior acquisition history.
- [ ] At least one admitted Observation resolves to exact preserved material through a durable Locator.
- [ ] At least one Claim is represented separately from source-local Observation.
- [ ] At least one human-only Decision is durably recorded without a model-authority path.
- [ ] `DD-7225 / D01` exists as a minimal File-scoped investigative handle with supporting Record references/history.
- [ ] The living internal report visibly distinguishes what sources present, what the Desk represents as Claims, what the human decided, and what remains discrepant/unresolved.
- [ ] Demonstrated report-to-Capture walkback succeeds for representative material.
- [ ] The implementation adds no website, Quinton, X/social, autonomous publication, global graph, or unrelated foundation machinery.
- [ ] Ticket-appropriate automated tests defend the real authority/provenance/lineage seams rather than reproducing the old foundation proof program.

## Pre-implementation review questions

Before mutation, the designated Writer must inspect the accepted authority and answer only the technical questions needed to make this slice implementable:

1. What is the smallest application/module boundary required now that `pyproject.toml` is explicitly proof-only?
2. What minimal production migration/bootstrap mechanism should this first PostgreSQL slice use, and why is it no broader than FILE-01 needs?
3. What exact Vault payload shape is sufficient for the verified document, audio, and optional image forms while preserving immutable source versions, derived-Surface lineage, and durable media-appropriate Locators?
4. Where is the human-Decision authority seam enforced so no model/Run path can invoke it?
5. Show the proposed report-to-Capture reverse walkback for representative document and audio material before implementation and identify every durable relation it requires.
6. Identify any requirement above that the verified Rendlesham corpus makes dishonest or impossible, rather than silently substituting toy data or weakly sourced media.

The Steward reconciles those answers before accepting the final implementation ticket and pinning the Writer start commit.

## Deferred capability record

**Intent:** A living investigative reference system that can eventually publish canonical Files and many Quinton renditions while preserving exact evidence/provenance history.

**This slice:** One real internal File from source capture through Observation/Claim/human Decision/Discrepancy to a living report with walkback.

**Deferred:** public website, publication snapshots/corrections UI, Quinton content, X/social acquisition and metrics, scheduled source monitoring, broad Workspace UX, graph/semantic retrieval, autonomous candidate discovery, and general-purpose OCR/transcription/video-processing.

**Promote when:** a real File exposes the need (`real-use`), public launch requires it (`post-MVP`), or a later idea remains merely possible (`not committed`).
