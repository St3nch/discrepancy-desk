# FILE-01: First real investigative File

**Status:** accepted — ready for one bounded implementation Writer

**Owner:** Project Steward

**Active Writer:** Unassigned. Any capable available model may serve, but only one Writer may mutate the shared worktree at a time.

**Implementation start commit:** Pin the exact clean HEAD in the governed Writer dispatch. The dispatch record is the operational authority for this value; it must point at a commit containing this accepted ticket.

**Blocked by:** None for code implementation. Real source acquisition, persistent database/bootstrap, new credentials, and the first human Decision remain explicit runtime gates stated below. No other foundation program is a prerequisite.

## Goal

Turn the Desk from a foundation repository into a usable investigative product by completing one real internal tracer-bullet File about the Rendlesham Forest incident of December 1980, using real source material and evidence walkback.

This ticket is intentionally **not** the website, Quinton, X/social, autonomous research, a public publication workflow, a generic notebook, or a complete implementation of every noun in Foundation Model v2.

## Investigation binding

- **Public File ID:** `DD-7225`
- **Subject:** Rendlesham Forest incident, December 1980
- **Working investigation question:** “What does the contemporaneous record establish about the Rendlesham Forest incident, how did the story change in later retellings, and which reported details remain unexplained after the strongest conventional explanations are considered?”
- **Working D01 question:** “For the Halt party’s recorded forest investigation, which reported observations, if any, are adequately accounted for by lighthouse and astronomical explanations, and which remain unresolved?”

The investigation is not framed as either “Was it aliens?” or “Debunk Rendlesham.” The available Record may support mostly explained events, narrative growth, genuinely strange details, remaining unknowns, or a combination.

D01 is an open, event-bounded investigative question, not a predetermined conclusion. It may close as adequately explained without failing this ticket. It is bound to the forest investigation preserved on the Halt recording. The Ridpath companion dates that recording to the early hours of December 28, while the Halt memorandum in the mirrored MoD compilation uses December 27 and 29 dates. FILE-01 must preserve that source-level dating tension rather than silently normalize it.

## Bounded corpus verification gate

CHAZ authorized one bounded verification pass over the core candidate URLs named below: the National Archives catalogue record, the mirrored MoD PDF, the Halt audio access copy, the Ridpath provenance companion, and the mirrored Suffolk packet. The optional FOI response was excluded.

This pass is research and ticket verification, not Capture or Record admission. It must make no provider purchase and must not invent substitutes. For each candidate, record in this ticket what was actually observed: availability and redirects, retrieval time, media type, byte size, SHA-256 digest, page/duration metadata where applicable, usable text-layer status for PDFs, asserted identity and its asserting source, and custody/completeness limitations. Facts currently described below as expected must be corrected if the retrieved material disagrees.

Final corpus selection, Locator path, and the Writer start commit are pinned only after the Steward reconciles those observations. Link rot or a materially different object requires explicit corpus reconciliation; it does not authorize silent substitution.

### Verification result — September 3, 2026

CHAZ authorized the bounded pass. Retrieval began at `2026-09-03T13:05:12Z`. No purchase, provider credential, substitution, optional FOI retrieval, Record admission, or publication occurred. SHA-256 was computed with GNU coreutils 9.4; PDF inspection used Poppler 26.05.0; audio inspection used FFmpeg/ffprobe 6.1.1.

#### National Archives catalogue identity

- The direct Discovery record route returned HTTP 202 with a zero-byte body and required a JavaScript/robot challenge. It supplied no citable record payload and therefore no Capture candidate.
- The official National Archives [UFO reports collection page](https://www.nationalarchives.gov.uk/explore-the-collection/explore-by-time-period/postwar/ufo-reports/) independently identifies “Correspondence on the Rendlesham Forest incident,” dated December 1980, as catalogue reference `DEFE 24/1948/1`. It also says the single-sheet report is the only event record in its holdings and that the surrounding file material is largely later handling and correspondence.
- This verifies the catalogue reference and broad archival description. It does **not** prove that the Black Vault bytes are identical to a National Archives distribution.

#### Mirrored MoD compilation

- Retrieval: HTTP 200 from the named Black Vault route; no redirect; response `Content-Type: application/pdf`.
- Bytes: `88,169,480`; SHA-256 `c870481af7658000d060621c738401e2cb9030e6543dbbbe50427c16ba64e1ec`.
- Format: PDF 1.6, 192 pages. PDF page 1 is an added Black Vault identification page; page 2 is a National Archives cover. The mirror is therefore not a clean byte-for-byte official-source Artifact.
- Content: the signed January 13, 1981 “Unexplained Lights” memorandum is visibly present at PDF page 19. Only 40 of 192 pages produced non-empty extracted text; 152 produced none. The memo page has an OCR/text layer, but it is too corrupted for exact quotation.
- Locator decision: preserve the complete 192-page mirror as acquired, record the added mirror cover, and cite the memo through a bounded operator-authored transcription Surface plus page/page-region Locator to PDF page 19. Do not cite its broken OCR text as exact evidence.

#### Halt recording access copy

- Retrieval: HTTP 200 from the named Avalon Library route; no redirect; response reported `audio/mpeg`.
- Bytes: `2,189,367`; SHA-256 `97ec012712bb18e2f3fe3d6726f3e9923138de1bf99647d0bc9feb8bfe3fbdc4`.
- Detected media: despite the `.mp3` filename and response type, the bytes are a QuickTime/MOV container carrying one mono MP3 audio stream at 16 kHz and approximately 16 kb/s.
- Duration: 1,093 seconds (`18:13`). The stream decoded end to end without error. Its embedded `2010-12-30` creation-time tag describes this digital file, not the 1980 recording event or chain of custody.
- Locator decision: time ranges target this exact captured audio Artifact. Any Desk transcript is a derived Surface. The source identity and generational history remain asserted by the acquisition host and Ridpath companion, not independently authenticated by container metadata.

#### Ridpath transcript and recording-history companion

- Retrieval: HTTP 200 from the named Avalon Library route; no redirect; response `Content-Type: application/pdf`.
- Bytes: `303,854`; SHA-256 `a3a85fbf2bf944f7c6996bc4c93a5aa18d42dd4797a5aa0575bc539c5785e3f4`.
- Format: PDF 1.7, 12 pages, usable text on all pages. Body text is extractable, though the first-page heading/sidebar layout does not extract cleanly.
- Provenance content: the companion describes the recording as the second-sighting investigation in the early hours of December 28 and describes the available copy as made by playing a copy through a loudspeaker into a microphone. These remain Ridpath's source assertions, not verified custody facts.
- Integrity lesson: the first transfer ended with only 32,768 local bytes despite a successful HTTP response and a declared 303,854-byte transfer. A clean retry matched the declared length and parsed successfully. HTTP success alone is not acquisition integrity.
- Locator decision: this separately authored source may use a frozen page-text Surface with page/text ranges for its own statements. It is not the Desk-derived transcript of the audio.

#### Mirrored Suffolk Constabulary packet

- Retrieval: HTTP 302 from the named Internet Archive route to `ia801908.us.archive.org/29/items/BritishUFOFiles/unusuallights.pdf`, then HTTP 200.
- Bytes: `231,927`; SHA-256 `c17f48a9948d15a7a0bbb1d833eda29873d2983ae0dd45b847b94891bcd4953c`.
- Format: PDF 1.4, seven pages, no usable text layer on any page.
- Content inspection: pages 1–2 are December 26, 1980 station/log material; page 3 is an October 1988 letter; page 4 is a November 1983 summary letter; page 5 is a January 2001 fax cover; pages 6–7 are a July 1999 letter. The material visibly presents Suffolk Constabulary letterhead/forms and redactions.
- Identity limit: neither this mirror transfer nor the inspected PDF independently established the previously asserted publication-scheme document ID or completeness of the historical official release.
- Locator decision: cited material requires bounded operator-authored transcription Surfaces plus page/page-region Locators to the exact scanned pages. Contemporaneous entries and later retrospective correspondence must remain distinct.

### Corpus reconciliation outcome

The three numbered corpus components are accepted without substitution: the mirrored MoD compilation; the Halt audio access copy with the Ridpath PDF as a separate provenance companion; and the mirrored Suffolk packet. The optional FOI response and image lead remain outside FILE-01.

The verified corpus requires two document citation paths, not a general OCR system: operator transcription with page/region walkback for the MoD memo and Suffolk scans, and frozen page text for the Ridpath companion. Audio walkback targets the captured recording by time range. The reusable acquisition lesson is simple and worth preserving: HTTP 200 is not integrity; digest, byte count, parse/decode, and visual inspection all matter.

## Initial source corpus

The following is the verified implementation corpus, not yet captured into the Desk. Acquisition must preserve the retrieved bytes, retrieval metadata, asserted source identity, and the limitations below. The verification digests identify the inspected candidates; the real Capture path must recompute them. A working URL is an acquisition route, not proof that the host is the origin or evidentiary authority.

### 1. MoD File DEFE 24/1948/1

- **Verified role in the File:** A 192-page mirrored compilation containing Lieutenant Colonel Charles Halt's signed “Unexplained Lights” memorandum at PDF page 19 and later government/public correspondence about the incident.
- **Asserted archival identity candidate:** [The National Archives catalogue record C10342055](https://discovery.nationalarchives.gov.uk/details/r/C10342055), reference `DEFE 24/1948/1`. The verification pass must distinguish what the official catalogue establishes from what the mirror asserts about its bytes.
- **Acquisition candidate:** [Public PDF mirror](https://documents.theblackvault.com/documents/ufos/UK/defe-24-1948.pdf).
- **Required treatment:** Capture the complete available PDF as one Artifact. Represent the Halt memorandum as a bounded document Surface/Locator within that Artifact; do not count the embedded memorandum as a second independent source.
- **Provenance limit:** The available bytes are retrieved from a non-official mirror. Do not infer that the mirrored object corresponds completely to the catalogue object, that every page is contemporaneous incident material, or that the mirror is an MoD original. Record observed page count, retrieval chain, digest, asserting source, verification state, and completeness uncertainty.

### 2. Halt field recording access copy

- **Role in the File:** Audio recorded by Halt's party during the early-hours forest investigation.
- **Acquisition candidate:** [Public MP3 access copy](https://avalonlibrary.net/Rendlesham_Forest_incident_1980/The_December_1980_Bentwaters_Charles_Halt_tape.mp3).
- **Provenance companion:** [Ian Ridpath's annotated transcript and recording-history note](https://avalonlibrary.net/Rendlesham_Forest_incident_1980/Transcript%20of%20Colonel%20Halt%20Tape%20(Ian%20Ridpath).pdf).
- **Required treatment:** Capture the audio bytes as an access-copy Artifact. Create only the bounded, time-coded transcript Surface needed by admitted Observations and link it to exact audio ranges. If the Ridpath PDF is captured, treat it as a separately authored source Artifact, not as a Desk-derived transcript Surface.
- **Provenance limit:** The candidate MP3 is not established as the original microcassette or a first-generation official copy. Available recording history describes researcher copies released in 1984 and later copying through loudspeaker/microphone playback. Do not label the captured MP3 “the original” or silently infer official MoD custody from web availability.

### 3. Suffolk Constabulary record packet

- **Verified role in the File:** A seven-page image-only packet containing December 26 station/log material and later 1983, 1988, 1999, and 2001 correspondence, including police statements relevant to the marks and Orford lighthouse.
- **Asserted historical publication identity:** Suffolk Constabulary publication-scheme document ID `cdf0ea85-e6d5-4a75-bcd4-cb5e385eb526`; retain the source and verification state of this assertion.
- **Acquisition candidate:** [Internet Archive PDF mirror](https://archive.org/download/BritishUFOFiles/unusuallights.pdf).
- **Required treatment:** Capture the complete packet as one Artifact. Use page/region Locators that distinguish the contemporaneous entries from the 1983 and 1999 retrospective material.
- **Provenance limit:** The former first-party download is no longer available at its historical URL. The mirror presents the packet as official material, but the transfer to the current mirror, correspondence to the asserted publication identity, and completeness of the release remain unverified until established by captured evidence. Record that limitation explicitly.

### Optional institutional context

The official [MoD FOI response dated May 11, 2015](https://assets.publishing.service.gov.uk/media/5a7f599240f0b6230268ef6d/20150511-FOI2015-03810-Rendlesham-Redacted-Final-Response.pdf) may be captured if the implementation needs a first-party source for later archival disposition. It is context about held/transferred records, not contemporaneous incident evidence and not a substitute for the three core sources.

### Deferred image lead

The early landing-site photograph attributed to Master Sergeant Ray Gulyas remains a useful lead, but it is not admitted to the initial corpus. Current public reproductions do not yet establish the exact source bytes, complete custody chain, or reuse rights. FILE-01 must not launder a later web reproduction into “original photographic evidence” merely to check an image-media box.

### Corpus boundary

The three numbered sources are the verified implementation corpus. The verified Locator paths are operator transcription plus page/region walkback for the MoD memo and Suffolk scans, frozen page text for citable Ridpath statements, and exact time ranges against the captured audio Artifact. Any substitution or material addition requires Steward reconciliation before implementation. The document-plus-audio mix is sufficient to prove media-neutral evidence authority in this slice; video and image processing remain deferred.

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

- Manually acquire the verified three-source corpus selected above for `DD-7225`.
- Record asserted archival/source identity, who or what asserted it, its verification state and basis, the actual acquisition host/route, and the retrieval event separately. The Record must not express verified identity that the Capture did not establish.
- Do not expand or substitute the corpus without Steward reconciliation.
- Each acquisition creates a Capture receipt.
- Preserve immutable acquired bytes/material as Artifacts in the smallest truthful Vault shape needed by this slice. A captured access copy is authoritative relative to Desk-derived Surfaces; it must not be labelled the originating original when provenance does not establish that status.
- Create frozen inspectable/citable Surfaces and durable Locators sufficient for admitted Observations. A PDF with a usable text layer may use a frozen page-text Surface and bounded page/text Locator. A scanned page without usable text may use a bounded operator-authored transcription Surface plus a page or page-region Locator into the captured document. This narrow fallback is not authorization for a general OCR platform.
- Audio requires exact time-range walkback to the captured audio Artifact. An admitted image may use the whole image or a bounded region, but no image is expected in this slice.
- Every derived Surface records its producing method, tool/operator and version when applicable, production time, payload digest, and lineage to the exact captured Artifact. Derived material never silently replaces or acquires the authority of the captured Artifact.
- A transcript may support search and inspection, but the recording remains authoritative relative to that transcript. AI enhancement or reconstruction may not be treated as original evidence.
- A later acquisition of the same source creates a new Capture receipt. If bytes are identical, Artifact deduplication is allowed; the prior Capture must never be overwritten.
- Do not force video into this slice or build scheduled monitoring, Wayback-scale automation, provider acquisition machinery, or a general OCR/transcription/video-processing platform.

### 3. Admit source-local Observations

- Admit source-local Observations only from preserved/citable material.
- Each Observation must walk back to the exact preserved source version, media form, Locator, and bounded Excerpt used to support what the source presents.
- `Excerpt` names that bounded selection. It may be implemented as a durable object or a stable projection over a Locator and selection, but it must be mechanically re-derivable and must not become a synonym for Observation.
- Observation means “this source presents X,” not “X is true.”

### 4. Represent Claims without laundering source assertions

- Create at least one durable Claim associated with the File by investigative relevance, not owned by or scoped as truth to that File. The same lifecycle rule applies to File/Capture relevance.
- Where the verified corpus presents real disagreement or competing explanations, preserve the competing Claims/positions rather than forcing premature reconciliation. Do not manufacture disagreement if the material does not support it.
- An Observation may support or contradict a Claim but may not silently set Claim posture or human judgment.

### 5. Exercise a human-only Decision

- Record at least one exact Decision explicitly made and authorized by CHAZ, acting on an exact durable Claim/version.
- Decision admission must use a positive operator-authority capability that the ordinary/model-facing Record path cannot present or assume. The ordinary path must explicitly refuse a Decision write; absence of a model UI or Run table is not proof of the boundary.
- A model may transport exact human-authorized content through a governed operation, but it may not originate, alter, or self-authorize the Decision.
- The implementation must prove that a later Decision can supersede or revise an earlier Decision without erasing it. Do not create a second fake investigative Decision merely to populate history; the lineage behavior may be demonstrated by an automated test.
- FILE-01 proves bounded capability separation, not production-grade human authentication. F13 remains deferred and does not waive this seam.

### 6. Create the first durable Discrepancy

- Create `DD-7225 / D01` as the event-bounded investigative question above, reconciled against the admitted Record. Its honest lifecycle may remain open, narrow, change wording with preserved history, or close as adequately explained.
- Persist only the minimal durable shape: ID, concise question/description, current lifecycle state, supporting Record references, and update history.
- D01 is an investigative handle, not a Claim posture, truth score, proof of conspiracy, or node in a global discrepancy graph.

### 7. Render a living internal report

- Provide an operator-readable current File report/projection generated from durable state.
- Emit a durable Record reference beside every substantive report statement so the operator can begin walkback from the report itself.
- Visibly distinguish source presentation/Observation, Desk-level Claim, human Decision, and Discrepancy state.
- Do not require a fake `Conclusion`; D01 may remain unresolved or close as adequately explained without inventing certainty.
- Do not hard-code the full future public report section list as a schema or workflow engine.

### 8. Prove evidence walkback

From material shown in the living report, the operator must be able to walk back through the relevant durable objects to the exact captured source version/Locator.

At minimum, the implementation/review must demonstrate:

```text
report statement + durable Record reference
  → Claim / Observation / Discrepancy reference
  → Observation
  → Excerpt (durable object or stable projection)
  → Locator
  → Surface or Artifact target
  → Artifact
  → Capture receipt
```

For audio-derived report material, walkback must continue through any transcript/inspection Surface and an exact time-range Locator to the preserved recording Artifact and its Capture receipt. Verification must recompute Artifact and frozen-Surface digests, validate Locator bounds, and re-derive each demonstrated Excerpt; mismatch must fail loudly. If an image is admitted after explicit corpus reconciliation, representative image material must likewise resolve through its whole-image or bounded-region Locator.

## Storage and application boundary

- PostgreSQL 18 is the authoritative structured Record store per ADR-0001.
- Vault payload authority remains distinct from PostgreSQL structured Record state. Record rows must retain exact digest/reference walkback to the authoritative Vault payload. Explicitly non-authoritative, rebuildable text or bounded selections may be stored in PostgreSQL when useful; they must not become the sole evidence authority.
- The FND-PG01 proof environment is not the application package and its scratch SQL is not a production migration.
- Introduce only the smallest application/package and forward migration/bootstrap surface needed for FILE-01. Exact module names, table names, surrogate-key types, migration implementation, and Vault fan-out are implementation choices unless another accepted authority constrains them.
- Do not import proof-only parsing or schema assumptions into the application merely because they exist.
- If application packaging changes `pyproject.toml` or `uv.lock`, preserve the governed `postgres-foundation-proofs` execution contract, make application tests discoverable by the governed `test` task, and explicitly re-provision and verify the environment rather than assuming `uv run --offline --no-sync` will adapt.
- A persistent PostgreSQL 18 substrate and any new credential or privilege boundary require their own CHAZ authorization before real Record admission. They are not prerequisites for implementing and proving the slice against governed disposable PostgreSQL 18, and they are not permission to start another foundation program.

## Accepted implementation boundary

The following choices are accepted for FILE-01. They are deliberately narrower than a complete
Desk architecture.

### Application shape

- Keep one root uv project and one lockfile for the application and the completed proof tooling.
- Add the production package under `src/discrepancy_desk/` and application tests under
  `tests/desk/`. Preserve `tools/postgres_foundation_proofs/` and `tests/proofs/`.
- Convert the existing proof-only package configuration only as far as required to make the
  application importable and both test suites discoverable. Do not add an ORM, web framework,
  migration framework, provider SDK, or another runtime dependency; `psycopg` and the Python
  standard library are sufficient for this slice.
- Preserve five cohesive seams: database admission/migration; Vault and evidence handling;
  Record semantics; report/walkback reads; and operator command composition. These are
  responsibilities, not a mandated one-file-per-seam layout. Prefer deep modules with small
  interfaces over pass-through wrappers.
- The application performs no network acquisition. An operator supplies a local file plus
  observed retrieval metadata to Capture. The application must hash, verify, preserve, and admit
  that material; it must never imply that it observed the socket transfer itself.

### PostgreSQL migration and admission

- Introduce one forward-only production SQL migration containing only the FILE-01 schema.
- Use a minimal migration ledger containing migration version, filename, SHA-256 digest, and
  application time. Hold an advisory lock while applying migrations and refuse to continue when
  the recorded digest for an applied migration no longer matches. Do not add Alembic,
  autogeneration, down migrations, branching, or a seed framework.
- Keep role/bootstrap work separate from schema migration because role creation requires elevated
  authority and new credentials.
- Carry the already-proved lock-first admission ordinal into production writes. Every governed
  semantic row must point to its admission. Commit-timestamp finalization and civil-time
  `as_of` semantics remain outside FILE-01; ordinary timestamps must not be presented as that
  deferred receipt.
- Governed Record tables are append-only for this slice. Deny `UPDATE`, `DELETE`, and
  `TRUNCATE` to runtime roles and defend the invariant in the database, not only in application
  code.
- Do not import the proof harness DSN parser or scratch schema. Reuse the proved behavior, not its
  disposable implementation.

### Vault and evidence contracts

- Require an operator-configured absolute `DESK_DATA_ROOT` for write operations and fail closed
  when it is absent, relative, or unusable. Keep the Vault outside Git.
- Store Artifact and frozen-Surface payloads by SHA-256 content address beneath that root. Writes
  must be atomic and non-overwriting; a successful write returns only after recomputing and
  matching digest and byte size.
- PostgreSQL records the hash algorithm, digest, byte size, media type, Vault reference, Capture
  receipt, and lineage. Rebuildable text or bounded selections may also be stored in PostgreSQL
  only as explicitly non-authoritative conveniences.
- Freeze only the locator contracts the verified corpus needs:
  - `document_page_char_range`: a one-based page plus half-open character range into an
    immutable UTF-8, NFC-normalized page-text Surface;
  - `document_page`: a one-based whole-page address into a captured PDF Artifact, used to anchor
    bounded operator transcription for the image-only or corrupt-text pages;
  - `media_time_range`: a half-open integer-millisecond range into the captured audio Artifact.
- Every Locator carries a contract version and one exact typed target. Unsupported kinds and
  invalid bounds fail closed. Geometric page regions are deferred until a real citation needs
  precision below the page.
- `Excerpt` may be a durable row or stable projection. In either form it must be reproducible
  from the exact Locator target and selection contract.

### Human Decision capability

- Enforce the seam first with PostgreSQL privileges. A non-login owner owns the schema. The
  ordinary Desk runtime role can read and append the non-Decision Record but cannot insert a
  Decision or Decision-effect/supersession relation. A separate human-authority role can read the
  required context and append only the Decision admission surface it needs. Neither runtime role
  may update, delete, truncate, own the schema, or grant itself privileges.
- Ordinary application code reads only `DESK_POSTGRES_URL`. The Decision operator path reads a
  distinct `DESK_HUMAN_POSTGRES_URL`, refuses when it is absent, and never falls back to the
  ordinary credential. Credentials do not enter the repository.
- Prove the negative path in PostgreSQL: an attempted Decision write using the ordinary role must
  fail with SQLSTATE `42501` (`insufficient_privilege`). Prove the positive path through the
  separately granted operator capability.
- This establishes capability separation, not a human identity system. F13 remains deferred. The
  real FILE-01 Decision is admitted only after CHAZ supplies and authorizes its exact content.

### Verification and expected change surface

- Run application integration tests through the governed `test` task against disposable
  PostgreSQL 18. The VedaOps task was verified at the acceptance baseline to receive
  `VEDAOPS_POSTGRES_URL`; application runtime configuration remains `DESK_POSTGRES_URL`.
- Preserve and rerun the unchanged `postgres-foundation-proofs` task plus lint and format checks.
- Expected implementation paths are `src/discrepancy_desk/**`, `tests/desk/**`,
  `pyproject.toml`, `uv.lock` when dependency metadata actually changes, and concise authority
  or operator documentation updates required by the delivered behavior.
- Changes under `tools/postgres_foundation_proofs/**` or `tests/proofs/**` are not expected.
  A compatibility repair there requires explicit Writer justification and Steward review.
- Before real Capture and Record admission, CHAZ must separately authorize: reacquisition of the
  accepted URLs onto the VPS; a dedicated persistent PostgreSQL 18 target and local runtime
  roles/credentials; the absolute Desk data root; and the exact first human Decision. Those gates
  do not block implementation in disposable infrastructure.

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
- Notice and Run persistence or orchestration; the Decision boundary is enforced positively, not by their absence;
- multi-user, remote, or production authentication/authorization machinery beyond the bounded local capability seam;
- another reusable PostgreSQL foundation/fixture program;
- implementing every Foundation Model noun because it exists in design material.

## Acceptance behavior

- [ ] `DD-7225` exists with stable public identity, separate internal identity, and honest temporal metadata independent of its non-semantic filing number.
- [ ] The corpus verified and finally accepted by the Steward is captured through the implemented path; no candidate URL, page count, content description, or identity assertion is treated as verified merely because this draft named it.
- [ ] The Record separates asserted archival/source identity, asserting source, verification state/basis, acquisition host/route, retrieval event, and material provenance limits. It cannot express verified identity that no Capture established.
- [ ] Each captured Artifact is authoritative relative to every Desk-derived Surface while its actual generational/custody limitation remains visible.
- [ ] Every used derived Surface records producing provenance, payload integrity, and exact lineage to its captured Artifact.
- [ ] Representative document evidence uses a durable bounded Locator supported honestly by the verified media: text-layer path when available, otherwise bounded operator transcription plus page/page-region walkback.
- [ ] A representative audio Observation resolves through an exact time-range Locator to the captured recording Artifact.
- [ ] A recapture creates a new Capture receipt without overwriting prior acquisition history; identical bytes may deduplicate only the Artifact.
- [ ] At least one admitted Observation resolves through a mechanically re-derivable Excerpt and durable Locator to exact preserved material.
- [ ] At least one Claim is represented separately from source-local Observation and associated to the File by relevance rather than File-owned truth.
- [ ] If the verified corpus presents competing Claims or explanations, the implementation preserves them without forced reconciliation.
- [ ] An ordinary/model-facing Record capability explicitly refuses Decision admission, while a separate operator-authority path admits one exact CHAZ-authorized Decision.
- [ ] Automated proof demonstrates Decision supersession/revision without erasing prior history; the real File is not padded with a fake second Decision.
- [ ] `DD-7225 / D01` exists as a minimal File-scoped investigative handle with supporting Record references/history and may honestly close as adequately explained.
- [ ] The living internal report emits durable references and visibly distinguishes what sources present, what the Desk represents as Claims, what CHAZ decided, and the current Discrepancy state without requiring a fake Conclusion.
- [ ] Demonstrated report-to-Capture walkback recomputes relevant digests, validates Locator bounds, re-derives the Excerpt, and fails loudly on mismatch.
- [ ] Vault payload authority remains distinct from PostgreSQL; any rebuildable payload copy in Record storage is explicitly non-authoritative and retains exact Vault digest/reference walkback.
- [ ] Existing proof tasks still run unchanged, application tests are discovered by the governed `test` task, and ticket-appropriate tests defend the real authority/provenance/lineage seams.
- [ ] The implementation adds no website, Quinton, X/social, autonomous publication, Notice/Run machinery, global graph, or unrelated foundation program.

## Technical review disposition

The read-only technical review and the bounded corpus verification are complete. The Steward
accepted their behavioral findings, rejected premature module/table proliferation, and settled
only the minimum implementation contracts above.

The ticket is accepted for one Writer. The exact clean implementation start commit is pinned in
the governed Writer dispatch so it cannot drift between assignment and execution. No persistent
database, credential, source acquisition, human Decision, public action, or push is implied by
ticket acceptance.

A persistent PostgreSQL 18 target and new runtime credentials are authorized separately before
real bootstrap/admission.

## Deferred capability record

**Intent:** A living investigative reference system that can eventually publish canonical Files and many Quinton renditions while preserving exact evidence/provenance history.

**This slice:** One real internal File from source capture through Observation/Claim/human Decision/Discrepancy to a living report with walkback.

**Deferred:** public website, publication snapshots/corrections UI, Quinton content, X/social acquisition and metrics, scheduled source monitoring, broad Workspace UX, graph/semantic retrieval, autonomous candidate discovery, and general-purpose OCR/transcription/video-processing.

**Promote when:** a real File exposes the need (`real-use`), public launch requires it (`post-MVP`), or a later idea remains merely possible (`not committed`).
