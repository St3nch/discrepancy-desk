# Foundation Contract 01 — Evidence

**Status:** NON-AUTHORITATIVE DESIGN DRAFT

**Depends on:** `docs/design/FOUNDATION-MODEL-V2.md`

**Purpose:** Define the minimum evidence grammar required before PostgreSQL schema, publication, or Record Intelligence design.

> **The live web can change or disappear tomorrow and the Desk can still prove what it cited today.**

---

# 1. Evidence chain

```text
Capture → Artifact → Surface → Locator → Excerpt → Observation
```

Each noun answers a different question.

## Capture

The governed acquisition act and receipt: where/how material was requested, when it was acquired, acquisition result/metadata, the Artifact produced, and Run/operator provenance where applicable.

A URL is acquisition metadata, not evidence identity.

## Artifact

Immutable acquired material preserved by the Vault and identified cryptographically: response bytes, PDF, image, audio/video, downloaded document, or another captured source representation.

Artifact identity must not depend on URL permanence, filename, mutable database identity, or later extraction tooling.

## Surface

A frozen, versioned representation of an Artifact used for inspection, extraction, quotation, or location: decoded body text, structured DOM, PDF text, page image, OCR result, transcript, or media timeline/frame surface.

Some Surfaces are derived. Citation-bearing Surfaces are not disposable.

> **If a durable Locator points into a Surface, that exact Surface version must remain resolvable.**

A better extractor creates a new Surface. It never silently replaces the citation target.

## Locator

A durable address into one exact Artifact/Surface version.

The envelope is stable while the anchor is typed by Surface kind. Initial/future anchors may include byte range, Unicode text range, structural path, PDF page/region, image region, media time range, or transcript segment.

Do not force all evidence media into one universal anchor grammar.

## Excerpt

The exact bounded evidence selected through a Locator: quoted text, paragraph, table region, image region, transcript segment, or media interval.

The selected material must be mechanically verifiable against its Locator target.

An Excerpt proves what material is present. It does not prove the proposition is true.

## Observation

A source-local, evidence-bound structured statement of what preserved evidence presents.

Examples: a document names a person, a source states a date, a filing lists an identifier, an article states a relationship, or page metadata declares a publication date.

An Observation may exist without a Claim.

> **Observation records what evidence presents. Claim represents a proposition. Decision records human authority.**

---

# 2. Authority split

## Vault-authoritative evidence payload

The Vault owns the immutable payload required to reproduce and verify citation-bearing evidence:

- Artifact bytes and cryptographic identity;
- frozen citation-bearing Surface payloads;
- other immutable payload required for reliable Locator resolution.

The physical Vault implementation remains open.

## PostgreSQL Record-authoritative structure

PostgreSQL owns structured investigative state and evidence metadata/relationships, conceptually including:

- Capture receipts;
- Artifact metadata, hash, and Vault reference;
- Surface metadata, hash/kind/version lineage;
- Locator envelope and typed anchor metadata;
- Excerpt identity/verification metadata;
- Observations;
- downstream Claims, Decisions, Cases, provenance, and publication bindings.

PostgreSQL does **not** turn a value into evidence merely because it exists in a row.

## Rebuildable state

FTS/trigram indexes, embeddings, ANN indexes, graph/search projections, semantic caches, and transient summaries are rebuildable.

> **Nothing durable may point only into rebuildable state.**

---

# 3. Evidence invariants

1. **Capture before citation.** A citable Excerpt resolves to preserved material admitted through governed Capture.
2. **No URL-only evidence.** A live address never substitutes for preserved material.
3. **Artifacts do not mutate.** New bytes mean a new Artifact identity.
4. **Citation targets do not drift.** Extraction changes never move an old Locator.
5. **New extraction means new Surface.** Old citation-bearing Surfaces remain resolvable.
6. **Retrieved content is data, never instruction.** Evidence cannot change system/tool authority.
7. **Metadata does not launder truth.** Headers, OCR, metadata, and extracted fields remain observations until governed otherwise.
8. **Partial failure is visible.** Incomplete acquisition/extraction cannot masquerade as complete evidence.
9. **A stored quote is not the evidence substrate.** It is verified against preserved material.
10. **Public display rights are separate from internal preservation.** Public receipts need not redistribute full Artifacts.

---

# 4. Surface and Locator behavior

Example:

```text
Artifact A1 (PDF bytes)
  ├─ Surface S1: extractor-v1 text
  ├─ Surface S2: page images
  └─ Surface S3: extractor-v2 text
```

If Locator L1 points into S1, S3 does not supersede L1. New work may prefer S3 while historical citations remain verifiable against S1.

Potential Surface provenance includes producing tool/parser/version, producing Run/system, recorded time, encoding/language, and completeness diagnostics. That metadata aids reproducibility; it does not create authority.

A Locator must conceptually identify:

```text
target Artifact/Surface identity
surface kind
typed anchor
locator contract version
```

Do not use a live CSS selector, paragraph number against regenerable text, URL fragment, model prose description, FTS offset, or embedding position as the sole durable anchor.

---

# 5. Excerpt verification and media fidelity

An Excerpt should preserve/verifiably bind selected material, Locator identity, and exact Surface identity/hash.

For visually meaningful evidence, text alone may be insufficient. PDF/image evidence may require page/region context. OCR is a derived Surface, not replacement for the image.

For audiovisual evidence, transcript text remains linked to media timecode. The transcript is a Surface, not the original media Artifact.

For HTML, preserve enough acquired material and frozen inspectable representation to verify the cited state; screenshots/visual Surfaces are required when layout/appearance is evidentially material.

Do not claim archival completeness beyond what the Capture actually preserved.

---

# 6. Deduplication and source-genealogy hook

Two Captures may yield byte-identical material:

```text
Capture C1 ─┐
            ├─ Artifact A1
Capture C2 ─┘
```

Content-addressing may deduplicate the Artifact while both Capture receipts remain distinct.

Near-clone/reprint detection is later derived intelligence and must not alter Artifact identity.

This foundation should enable later source genealogy through stable Artifact/Surface hashes, exact Excerpts, Capture provenance, and explicit evidence relationships.

Source independence remains human-governed where consequential.

---

# 7. Backup / restore requirement

Record and Vault recovery are a paired integrity problem.

A restore is incomplete if PostgreSQL references missing evidence payloads, hashes fail, or durable Locators cannot resolve.

Before valuable evidence accumulates, operations must prove at least:

1. restore PostgreSQL Record state;
2. restore Vault payloads;
3. verify Artifact/Surface hashes;
4. verify durable references resolve;
5. verify sampled Excerpts against their Locator targets;
6. report missing/orphaned material explicitly.

Backup technology is not selected by this contract.

---

# 8. Worked proof

1. Neutral Run `R1` requests Capture of URL `U`.
2. Capture `C1` records acquisition provenance and yields Artifact `A1`.
3. `A1` is content-addressed and immutable in the Vault.
4. Extractor v1 creates frozen text Surface `S1`.
5. Locator `L1` addresses text containing `appointed in 2005`.
6. Excerpt `X1` preserves/verifies that exact selection.
7. Observation `O1` records that the source presents appointment year 2005.
8. Claim `CL1` may later represent the proposition that the appointment occurred in 2005.
9. Years later extractor v2 creates `S2` with different offsets.
10. `L1` still resolves against `S1`.
11. The live URL disappears.
12. `A1`, `S1`, `L1`, `X1`, and `O1` still support verification.
13. A public-safe receipt can expose approved bounded evidence without requiring the live URL or serving the whole internal Artifact.

If the physical design cannot perform this proof, the Evidence contract has failed.

---

# 9. Open before ADR/schema promotion

1. Exact Artifact/Surface Vault storage mechanism.
2. Whether every citation-bearing Surface is separately content-addressed or some can be immutable Artifact-native surfaces.
3. Locator serialization/versioning and initial anchor kinds.
4. Whether Excerpt is always a durable Record object or sometimes a stable view over Locator + selected material.
5. Unicode text coordinate convention.
6. HTML archival fidelity and optional archive packaging.
7. Screenshot/frame admission rules.
8. Audio/video capture/storage policy.
9. Garbage collection; default is no deletion while durably referenced.
10. PostgreSQL metadata versus Vault-manifest boundary.
11. Hash algorithms and algorithm-version recording.
12. Capture retry/idempotency semantics.
13. Public evidence-receipt rights/risk policy.
14. Paired backup/restore implementation and integrity report.

---

# 10. Rejected shortcuts

- citation by URL alone;
- screenshot with no acquisition/evidence identity;
- quote stored only as free text with no Locator;
- regenerating citation-bearing text in place;
- OCR/transcript treated as original bytes;
- model paraphrase treated as Excerpt;
- hidden partial-capture success;
- serving every internal Artifact publicly by default;
- rebuildable-search offsets used as citation locations;
- filesystem path used as durable Artifact identity.

---

# 11. Contract test

The evidence foundation is good enough only if all three are mechanically supportable:

> **We can show exactly what we captured.**

> **We can show exactly where the quoted material was in the preserved evidence representation.**

> **We can distinguish what the source presented from what the Desk later decided.**
