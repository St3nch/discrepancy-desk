# FILE-01: First real investigative File

**Status:** draft — Product subject, File identity, and initial source corpus selected; awaiting technical pre-implementation reconciliation

**Owner:** Project Steward

**Designated Writer:** TBD after ticket reconciliation

**Implementation start commit:** TBD. Implementation must start from the exact clean authority commit accepted by the Steward.

**Blocked by:** Complete the ticket's technical pre-implementation review against the selected real corpus. No other foundation program is a prerequisite.

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

## Initial source corpus

The initial corpus is selected for ticket design, not yet captured into the Desk. Acquisition must preserve the retrieved bytes, retrieval metadata, source identity, and the limitations below. A working URL is an acquisition route, not proof that the host is the origin or evidentiary authority.

### 1. MoD File DEFE 24/1948/1

- **Role in the File:** Official archival compilation containing Lieutenant Colonel Charles Halt's signed “Unexplained Lights” memorandum and later government/public correspondence about the incident.
- **Official identity:** [The National Archives catalogue record C10342055](https://discovery.nationalarchives.gov.uk/details/r/C10342055), reference `DEFE 24/1948/1`.
- **Acquisition candidate:** [Public PDF mirror](https://documents.theblackvault.com/documents/ufos/UK/defe-24-1948.pdf).
- **Required treatment:** Capture the complete available PDF as one Artifact. Represent the Halt memorandum as a bounded document Surface/Locator within that Artifact; do not count the embedded memorandum as a second independent source.
- **Provenance limit:** The archival reference and file identity are official, but the available bytes are retrieved from a non-official mirror. The file is a later compilation, not 191 pages of contemporaneous material. Record the retrieval chain, hash, page count, and any completeness uncertainty rather than labelling the mirror itself an MoD original.

### 2. Halt field recording access copy

- **Role in the File:** Audio recorded by Halt's party during the early-hours forest investigation.
- **Acquisition candidate:** [Public MP3 access copy](https://avalonlibrary.net/Rendlesham_Forest_incident_1980/The_December_1980_Bentwaters_Charles_Halt_tape.mp3).
- **Provenance companion:** [Ian Ridpath's annotated transcript and recording-history note](https://avalonlibrary.net/Rendlesham_Forest_incident_1980/Transcript%20of%20Colonel%20Halt%20Tape%20(Ian%20Ridpath).pdf).
- **Required treatment:** Capture the audio bytes as an access-copy Artifact. Create only the bounded, time-coded transcript Surface needed by admitted Observations and link it to exact audio ranges. If the Ridpath PDF is captured, treat it as a separately authored source Artifact, not as a Desk-derived transcript Surface.
- **Provenance limit:** The candidate MP3 is not established as the original microcassette or a first-generation official copy. Available recording history describes researcher copies released in 1984 and later copying through loudspeaker/microphone playback. Do not label the captured MP3 “the original” or silently infer official MoD custody from web availability.

### 3. Suffolk Constabulary record packet

- **Role in the File:** Seven-page police packet containing contemporaneous December 26 call/station entries and later police correspondence, including the responding officer's account of the marks and the visible Orford lighthouse.
- **Historical official publication identity:** Suffolk Constabulary publication-scheme document ID `cdf0ea85-e6d5-4a75-bcd4-cb5e385eb526`.
- **Acquisition candidate:** [Internet Archive PDF mirror](https://archive.org/download/BritishUFOFiles/unusuallights.pdf).
- **Required treatment:** Capture the complete packet as one Artifact. Use page/region Locators that distinguish the contemporaneous entries from the 1983 and 1999 retrospective material.
- **Provenance limit:** The former first-party download is no longer available at its historical URL. The packet carries strong internal official identity, but the transfer to the current mirror and completeness of the release are not independently established. Record that limitation explicitly.

### Optional institutional context

The official [MoD FOI response dated May 11, 2015](https://assets.publishing.service.gov.uk/media/5a7f599240f0b6230268ef6d/20150511-FOI2015-03810-Rendlesham-Redacted-Final-Response.pdf) may be captured if the implementation needs a first-party source for later archival disposition. It is context about held/transferred records, not contemporaneous incident evidence and not a substitute for the three core sources.

### Deferred image lead

The early landing-site photograph attributed to Master Sergeant Ray Gulyas remains a useful lead, but it is not admitted to the initial corpus. Current public reproductions do not yet establish the exact source bytes, complete custody chain, or reuse rights. FILE-01 must not launder a later web reproduction into “original photographic evidence” merely to check an image-media box.

### Corpus boundary

The three numbered sources are the implementation corpus unless the technical review identifies a concrete evidence-walkback blocker. Any substitution or material addition requires Steward reconciliation before implementation. The document-plus-audio mix is sufficient to prove media-neutral evidence authority in this slice; video and image processing remain deferred.

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

- Manually acquire the three-source corpus selected above for `DD-7225`.
- Preserve the official/archive identity separately from the actual acquisition host and retrieval event.
- Do not expand or substitute the corpus without Steward reconciliation.
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
- [ ] The selected DEFE 24/1948/1 compilation, Halt audio access copy, and Suffolk Constabulary packet are captured through the implemented path.
- [ ] The corpus records official/source identity, acquisition host, retrieval event, and material provenance limits separately rather than silently treating availability as authenticity.
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
3. What exact Vault payload shape is sufficient for the selected document and audio forms while preserving immutable source versions, derived-Surface lineage, and durable media-appropriate Locators?
4. Where is the human-Decision authority seam enforced so no model/Run path can invoke it?
5. Show the proposed report-to-Capture reverse walkback for representative document and audio material before implementation and identify every durable relation it requires.
6. Identify any requirement above that the verified Rendlesham corpus makes dishonest or impossible, rather than silently substituting toy data or weakly sourced media.

The Steward reconciles those answers before accepting the final implementation ticket and pinning the Writer start commit.

## Deferred capability record

**Intent:** A living investigative reference system that can eventually publish canonical Files and many Quinton renditions while preserving exact evidence/provenance history.

**This slice:** One real internal File from source capture through Observation/Claim/human Decision/Discrepancy to a living report with walkback.

**Deferred:** public website, publication snapshots/corrections UI, Quinton content, X/social acquisition and metrics, scheduled source monitoring, broad Workspace UX, graph/semantic retrieval, autonomous candidate discovery, and general-purpose OCR/transcription/video-processing.

**Promote when:** a real File exposes the need (`real-use`), public launch requires it (`post-MVP`), or a later idea remains merely possible (`not committed`).
