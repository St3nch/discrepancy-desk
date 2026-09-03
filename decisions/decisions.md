# Discrepancy Desk Decisions

This register contains settled Product and project decisions. Each entry preserves the
reason and rejected alternative so future work does not reopen it accidentally.
Technical choices that meet the ADR bar remain under `docs/adr/`.

## D1 — The Desk is an investigative record and publishing system

**Decision:** The Desk gathers and preserves factual material, breaks difficult subjects
into inspectable questions, represents competing explanations and discrepancies, and
produces accountable living Files and later outward-facing Renditions.

**Why:** Contested subjects require durable research and visible reasoning rather than a
one-shot answer.

**Cost:** The Product must preserve provenance, disagreement, revision, and uncertainty
instead of optimizing only for fast prose generation.

**Rejected:** A generic note application, chatbot, debunking site, belief engine, or
content generator wearing an evidence-themed hat.

## D2 — Observation, Claim, and Decision remain distinct

**Decision:** An Observation states what a preserved source presents. A Claim is a durable
Desk-level proposition. A Decision is an explicit human-authority event acting on an exact
durable target or version.

**Why:** Source assertions are not automatically true, and model output or repetition is
not human judgment.

**Cost:** The implementation needs explicit links and additional write boundaries.

**Rejected:** One fact table, one status field, model confidence as authority, or silently
promoting an Observation into an accepted Claim.

## D3 — A File is attention; Workspace and Record are different

**Decision:** A File is the durable scope of investigative attention. Foundation Model
`Case` and Product `File` name the same object. Workspace holds ordinary notes, leads,
questions, snippets, hypotheses, and story ideas. Record contains governed durable
investigative state.

**Why:** Investigative work needs freedom to think without laundering every note into
institutional memory or creating private truth per File.

**Cost:** Useful Workspace material requires deliberate admission before it can support
durable findings or publication.

**Rejected:** Separate Case and File objects, File-scoped truth stores, or treating every
written note as Record.

## D4 — Evidence is media-neutral and originals retain authority

**Decision:** Evidence follows `Capture → Artifact → Surface → Locator → Observation`
across documents, images, audio, and video. Original media remains authoritative.
OCR, transcripts, extracted frames, normalization, and enhancement are versioned derived
Surfaces with explicit lineage.

**Why:** The Desk must inspect and cite mixed media without silently replacing evidence
with an extractor's interpretation.

**Cost:** Media-specific Locators and derived-Surface lineage must be supported where real
Files require them.

**Rejected:** An HTML/PDF-only system, transcript-as-recording, OCR-as-document, or AI
enhancement presented as original evidence.

## D5 — Discrepancies are File-scoped investigative handles

**Decision:** A Discrepancy records something in the available Record that does not fit
cleanly and deserves investigation. It carries a concise question or description,
minimal lifecycle/history, and links to relevant Record material.

**Why:** The Desk needs durable unresolved attention without pretending the tension proves
an explanation.

**Cost:** Discrepancy state must remain separate from Claim posture and conclusion.

**Rejected:** Proof-of-conspiracy labels, universal discrepancy graphs, suspiciousness
scores, or discrepancies that autonomously become conclusions.

## D6 — Durable semantic state preserves lineage and walkback

**Decision:** Captured source versions are immutable. Governed semantic state is
append-only or versioned through append-only lineage. Reports and later Publications must
walk back through exact Record references to preserved evidence.

**Why:** The Desk must show what it knew, why it said something, and how its understanding
changed.

**Cost:** Correction and supersession require explicit history rather than convenient
in-place replacement.

**Rejected:** Destructive correction, floating citations, durable references into only
rebuildable indexes, or summaries without evidence walkback.

## D7 — Public File numbers are archival-looking but non-semantic

**Decision:** Public/tool-facing File IDs use `DD-####`. The numeric portion is
non-semantic and non-sequential. It does not encode creation order, archive size, Domain,
priority, truth, or another investigative judgment. Internal identity and honest
creation/admission/revision history remain separate.

**Why:** The public fiction is an established archive while the institutional record must
remain honest.

**Cost:** A future allocation mechanism must prevent collision without exposing real
sequence.

**Rejected:** `DD-0001`, incrementing the prior File number, Domain-coded IDs, or claims
about archive size inferred from the number.

## D8 — Living Files may change; Publications preserve exact history

**Decision:** The Desk may maintain a current living File report. A Publication records
the exact human-authorized Rendition/version released at that time, and later Record
changes never silently rewrite it.

**Why:** Investigation must be able to change its mind without falsifying public history.

**Cost:** Material public changes require new exact-content authorization and revision
lineage.

**Rejected:** Immutable current Files, silently updated Publications, or copy-edit theater
for changes that alter no meaning.

## D9 — Quinton presents; the Desk investigates

**Decision:** Quinton Clearance is a fictional public-facing clerk/presenter applied
during Rendition work. Quinton has no Capture, Observation, Claim, Decision, or
Record-authority path.

**Why:** A strong presentation voice must not contaminate research or become a fictional
investigator with system authority.

**Cost:** Neutral investigative material and public voice require a deliberate boundary.

**Rejected:** Quinton as autonomous researcher, evidence analyst, Decision maker, or
persistent Record identity.

## D10 — PostgreSQL owns structured Record; the Vault owns evidence payloads

**Decision:** PostgreSQL 18 is authoritative for structured Record state. Immutable
acquired payload authority remains a distinct Vault concern. FND-PG01 proved selected
PostgreSQL behaviors but did not create a production schema.

**Why:** Structured historical state requires explicit relational integrity and traversal,
while large immutable source payloads require different storage and preservation behavior.

**Cost:** The application must maintain exact provenance across the Record/Vault boundary.

**Rejected:** SQLite as the rebuild Record store, PostgreSQL blobs as the only evidence
authority, or treating proof SQL as the production migration.

**Technical authority:** `docs/adr/0001-postgresql-record-store.md`.

## D11 — FILE-01 is the next real Product milestone

**Decision:** The first real File is `DD-7225`, concerning the Rendlesham Forest incident
of December 1980. Its working question examines the contemporaneous record, later
retellings, strongest conventional explanations, and remaining unexplained details.

**Why:** A real mixed-media investigation will expose the smallest truthful Product and
research workflow better than another hypothetical foundation exercise.

**Cost:** The initial implementation must confront imperfect provenance and real document
and audio material without expanding into a general media platform.

**Rejected:** Another foundation program, toy evidence, “Was it aliens?”, “Debunk
Rendlesham”, or forcing image/video into the corpus merely to check a box.

**Work authority:** `docs/tickets/FILE-01-first-investigative-file.md`.

## D12 — CHAZ owns Product; Codex is the exclusive Project Steward

**Decision:** CHAZ is Product Owner and final authority. Codex is the VedaOps Project
Steward across projects. Claude, Grok, and other capable models may perform bounded
research, review, design, implementation, or testing, but they do not receive or assume
the Project Steward role.

**Why:** Model availability should change who performs work without fragmenting project
understanding, reconciliation, sequencing, or authority.

**Cost:** The Steward must independently understand and verify delegated work rather than
outsourcing project coherence.

**Rejected:** Permanent model-specific Writer/reviewer offices, rotating Stewardship,
self-authorizing agents, or treating an agent report as project truth.

## D13 — Project-local skills are adapted working methods, not authority

**Decision:** Reviewed copies of the Matt Pocock engineering skills live under
`.agents/skills/` and are shared with supported coding clients. Desk adaptations live in
those files and Git history; `skills-lock.json` records upstream provenance only.

**Why:** The project benefits from reusable methods while retaining control over its
Product, authority, workflow, and safety boundaries.

**Cost:** Upstream refreshes require deliberate comparison and reconciliation.

**Rejected:** Blind skill updates, skill output that self-promotes into authority, or
parallel client-specific copies that drift apart.
