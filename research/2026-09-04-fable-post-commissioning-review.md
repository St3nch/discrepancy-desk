# Fable 5 Post-Commissioning Product Research Review — Discrepancy Desk

**Date:** 2026-09-04
**Status:** non-authoritative research input for CHAZ (Product Owner) and Codex/GPT (Project Steward)
**Author:** Claude Fable 5, new session, project truth reconstructed from repository state at `main` = `227cb42`
**Mode:** read-only. No repository, Git, PostgreSQL, or Record mutation. No corpus acquisition. No tickets created. Nothing promoted to backlog.

This review reassesses the reconciled prior Fable ecosystem review
(`research/2026-09-04-fable-5.1-product-ecosystem-review-reconciliation.md`) against the first
real DD-7225 commissioning evidence. It is deliberately adversarial toward the prior review's
own recommendations. It is research input, not authority; the Steward reconciles, CHAZ decides.

---

## 0. Synchronization and evidence base

Read for this review: `VISION.md`, `CONTEXT.md`, `decisions/decisions.md`,
`decisions/deferred.md` (F1–F16 with Pillar and Four-Horizon Clock), `AGENTS.md`, `README.md`,
`docs/tickets/FILE-01-first-investigative-file.md` (including the September 3 corpus
verification and acceptance checklist), ADR-0001/0002/0003 summaries, the implemented
application surface (`src/discrepancy_desk/cli.py`, `report.py`, `evidence.py` structure), and
the reconciled prior review. Real commissioning evidence inspected read-only in
`/home/chaz/tmp/dd-7225-acquisition/`: the four corpus files, `defe-page-19.png`,
`defe-page-19-transcription.txt`, `defe-page-19-excerpt-01.txt`, `ridpath-page-selected.txt`,
`ridpath-excerpt-01.txt`.

Commissioning facts taken as given (supplied by CHAZ, consistent with what the working
directory shows): persistent PostgreSQL 18 on port 5433; admin/runtime/human capability paths
exercised; `DD-7225` open as a durable File; four Artifacts captured and verified (mirrored MoD
compilation, Halt recording access copy, Ridpath companion PDF, Suffolk Constabulary packet);
one full evidence chain exercised for MoD PDF page 19 (corrupt embedded text → page render →
Claude Code visual transcription → second comparison pass → frozen `document_page_text` Surface
with lineage → exact character-range Locator → Excerpt → source-local Observation);
`verify` currently reports artifacts 4 / surfaces 1 / locators 1 / excerpts 1. No Claim, no
human Decision, no durable D01 yet. A second Ridpath evidence item (page 8, Ian Ridpath's
editorial note connecting the five-second call interval to the Orford Ness flash rate) is
prepared but not admitted.

Two facts about the prepared Ridpath item govern several judgments below:

1. The source contains **no astronomical explanation** for the later reported star-like
   objects, so the Desk must not manufacture an astronomical counter-position merely because
   D01's question mentions astronomical explanations.
2. The PDF is a **later third-party capture of Ridpath material**, not a Desk-derived
   transcript of the captured Halt audio. Its editorial notes are themselves later analytical
   retelling layered over the 1980 recording.

---

## 1. Reassessment of preserved prior recommendations

Classification vocabulary as assigned: CONFIRMED BY REAL USE / STRENGTHENED BY REAL USE /
WEAKENED BY REAL USE / TRIGGER PARTIALLY FIRED / TRIGGER NOT FIRED / WRONG, REJECT /
STILL DIRECTIONAL RESEARCH, NOT BACKLOG.

| Prior recommendation / pressure | Classification |
|---|---|
| Commission FILE-01 for real; let measured friction drive the next slice | **CONFIRMED BY REAL USE** |
| Operator friction would concentrate in throughput/UUID/CLI plumbing | **CONFIRMED BY REAL USE** |
| Batch / reviewable admission if friction warrants | **TRIGGER NOT FIRED** |
| Workspace as a real need (F2) — *convention* | **TRIGGER PARTIALLY FIRED** (convention earned) |
| Workspace *tooling* (app, DB, UI) | **TRIGGER NOT FIRED** |
| Richer living report projection | **TRIGGER NOT FIRED** (report not yet populated enough to judge) |
| Model proposal provenance as a coming pressure | **TRIGGER PARTIALLY FIRED** (Surface-production provenance exercised; proposal provenance not) |
| The prior "one schema line" framing for proposal provenance | **WRONG, REJECT** (Steward's narrowing vindicated; existing fields sufficed) |
| F15 model-assisted exact evidence noticing — direction | **STRENGTHENED BY REAL USE** |
| F15 — implementation trigger (manual locating materially limits work) | **TRIGGER PARTIALLY FIRED** at most; see §2 |
| Whole-media / whole-document Surfaces with many sub-locators | **TRIGGER NOT FIRED** |
| General OCR platform (F3) | **WEAKENED BY REAL USE** (bounded fallback absorbed the worst real case cheaply) |
| General audio/video processing (F4) | **TRIGGER NOT FIRED** (audio path not yet exercised at all) |
| "Source" as a durable noun / institutional source identity | **STILL DIRECTIONAL RESEARCH, NOT BACKLOG** |
| Source genealogy / later-retelling machinery (F5) | **TRIGGER PARTIALLY FIRED** as investigative question; machinery **NOT** earned |
| Backup/restore posture | **STRENGTHENED BY REAL USE** (irreplaceable real Record now exists) |
| Non-HTTP acquisition routes (F14 adjacent) | **TRIGGER NOT FIRED** |
| Closed named-operation model read interface into Record | **WEAKENED BY REAL USE** (Workspace file handoff worked with no Record read seam) |
| Anthropic Citations experiment | **WEAKENED BY REAL USE / moot** (provider access ending; the provider-neutral verification loop underneath is **CONFIRMED**) |
| Rendition/Publication work (F9/F10) | **TRIGGER NOT FIRED** |
| X/social acquisition (F11) and F16 lifecycle | **TRIGGER NOT FIRED** |
| Retrieval/search/graph (F7) | **TRIGGER NOT FIRED** |
| Notice persistence | **TRIGGER NOT FIRED** (the "look here" case was absorbed by an ordinary Observation path) |
| Run persistence | **TRIGGER NOT FIRED** (Surface `produced_by_*` fields carried the machine-work provenance) |
| Entity resolution (F6) | **TRIGGER NOT FIRED** |

### Notes on the non-obvious rows

**Operator friction — CONFIRMED, and located.** The prior review predicted the risk that
"admitting one useful Observation requires too much command/UUID plumbing." Real use confirmed
the friction and, more valuably, located it precisely: UUID handoff between CLI operations,
shell-local environment variables evaporating across sessions, and long derived-text transport
through chat. Critically, **the strict Record model itself was not the source of pain**. That
is the single most important commissioning result: the schema's strictness survived contact
with a genuinely hostile real case (a corrupt OCR layer on the single most-cited page of the
corpus) without needing relaxation.

**Batch admission — NOT fired, and the prior framing slightly mis-aimed.** The observed pain is
*per-step plumbing within one evidence chain* (six commands, each emitting a UUID the next
consumes), not *review burden across many admissions*. Batch admission is a Record-semantics
feature; the earned fix is orchestration-level (a session ledger, an env file, eventually
perhaps a thin chain script). One exercised chain cannot earn a change to admission semantics.

**Model read interface — WEAKENED.** The prior review worried models could not "read frozen
Surfaces through a useful governed seam." Real use showed the seam already exists and is
boring: files in a Workspace directory, deterministic verification afterward. Claude Code read
the PDF and render from disk, produced text into files, and the governed path admitted what
survived review. No named-operation interface, no model database role, no MCP-style surface was
needed or missed. This should stay rejected until a real noticing workflow at real scale
(F15) demonstrates the file handoff failing.

**General OCR — WEAKENED, which is the interesting direction.** The failed text layer was
exactly the scenario that might have argued for OCR machinery. Instead the pre-authorized
bounded fallback (render → model transcription → independent second pass → frozen Surface with
lineage) handled it with ephemeral PyMuPDF tooling and zero new dependencies. Real use
therefore *reduced* the expected value of an OCR platform and *increased* the value of
capturing the method as reusable knowledge (F1 territory). See Q11.

**Notice and Run — honest nuance.** The Ridpath editorial note is structurally a "look here"
candidate, and it was handled perfectly well as a prepared source-local Observation; no Notice
object was missed. The transcription-and-review derivation is structurally bounded machine
work, and it was handled by the Surface's `produced_by_method/actor/version/at` fields; no Run
object was missed. Both absences held. The one residual: the *second comparison pass* has no
first-class provenance home — it lives (or should live) inside the `produced_by_method`
narrative. That is a convention gap, not a schema gap. See Q7.

---

## 2. Deferred register assessment (current Pillar and Clock; register not edited)

| Item | Pillar | Clock | Trigger status after commissioning |
|---|---|---|---|
| F1 research source/method library | Evidence & Sources | NEXT | **PARTIALLY FIRED** — reusable method knowledge is now real: "HTTP 200 is not integrity," the render/transcribe/review/freeze recipe, mirror-custody caveats, the UUID-ledger habit. Its stated revisit point ("after real DD-7225 commissioning and its first research/friction review") is effectively *now*. The earned resolution is plain research notes, not a schema or library system. |
| F2 broad Workspace/notebook | Operator & Governance | NEXT | **PARTIALLY FIRED** — a de facto Workspace already exists (`~/tmp/dd-7225-acquisition/` holding renders, staged transcriptions, excerpt files). Real investigation was *not* materially slowed by the absence of tooling; it was slowed by the absence of a *convention* (where working files live, how session UUIDs are ledgered, where env config lives). Convention earned; tooling not. |
| F3 general OCR/document platform | Evidence & Sources | TRIGGERED | **NOT FIRED.** One page transcribed via the bounded path. The trigger requires *repeated* captures needing the same processing with manual treatment *materially limiting* research. Watch item: if D01 requires citing several Suffolk packet pages (all seven are image-only), the trigger could partially fire; even then the earned unit is a documented recipe, not a platform. Revisit at FILE-02 planning per its own rule. |
| F4 general audio/video processing | Evidence & Sources | TRIGGERED | **NOT FIRED.** No audio Observation exists yet; the bounded `media_time_range` path is still completely unexercised. Nothing can have out-grown a path that has never been used. |
| F5 source genealogy / narrative mutation | Investigation & Reasoning | NEXT | **PARTIALLY FIRED as a question, not as machinery.** Inside a single File the contemporaneous-vs-retelling distinction is already live three ways: Ridpath's editorial notes are later analysis layered over the recording; the Ridpath PDF itself is a later third-party capture of Ridpath material; the Suffolk packet mixes December 26, 1980 log material with 1983/1988/1999/2001 retrospective correspondence; and the Dec 27/29 vs Dec 28 dating tension must be preserved. All of this is currently handled honestly by careful Observation wording and provenance notes. That is the correct resolution at one-File scale. Its revisit point (after the first living report states what the corpus can/cannot establish) has not yet arrived. |
| F6 entity resolution | Investigation & Reasoning | TRIGGERED | **NOT FIRED.** Halt, Englund, Nevels, Ball(?) appear as names in transcripts; nothing requires durable identity resolution. |
| F7 search/graph/semantic retrieval | Investigation & Reasoning | TRIGGERED | **NOT FIRED.** The Record holds roughly a dozen governed objects. Direct governed reads are nowhere near strained. |
| F8 autonomous research/monitoring | Investigation & Reasoning | TRIGGERED | **NOT FIRED.** Human-directed work is barely begun. |
| F9 public website/publication workflow | Rendition & Publication | TRIGGERED | **NOT FIRED.** No outward artifact selected; no populated living report yet. |
| F10 Quinton content production | Rendition & Publication | TRIGGERED | **NOT FIRED.** |
| F11 X/social acquisition/publishing | Evidence & Sources | TRIGGERED | **NOT FIRED.** No social material in corpus. |
| F12 File-number allocation | Operator & Governance | TRIGGERED | **NOT FIRED.** Only `DD-7225` exists; trigger is the second File ID. |
| F13 multi-user/remote/production access | Operator & Governance | TRIGGERED | **NOT FIRED.** Notably, the bounded local capability separation it deliberately did *not* waive has now been proven in real runtime (separate admin/runtime/human paths work). That strengthens the boundary's credibility without advancing F13 itself. |
| F14 additional acquisition providers | Evidence & Sources | TRIGGERED | **NOT FIRED.** All four sources acquired via the accepted manual local-file path; the Ridpath truncated-transfer lesson (retry and re-verify) was operational, not a route gap. |
| F15 model-assisted exact evidence noticing | Investigation & Reasoning | NEXT | **PARTIALLY FIRED — but read carefully which half.** What real use exercised is the *verification half* of F15: a model produced text against Desk-controlled material, the result was mechanically frozen, exactly located, and re-verifiable. That loop works and is provider-neutral. What real use has *not* shown is the *noticing half*: nobody has yet been materially limited by manually locating relevant passages — the corpus is one memo page, a 12-page companion, seven scanned pages, and an 18-minute recording. F15's revisit point (after commissioning and its friction review) is arriving; the earned resolution is to preserve the proven verification loop as method knowledge and run the small provider-neutral evaluation pack (§5) before any promotion. |
| F16 provider-restricted/deletable evidence lifecycle | Evidence & Sources | TRIGGERED | **NOT FIRED.** All four Artifacts are freely mirrored public documents with no deletion/synchronization obligations. The question stays Research Required and dormant. |

No deferred item's trigger has fully fired. No item should be promoted to build on this
evidence. Two register-adjacent calibrations belong to the Steward: F1, F2, and F15 have
reached their stated revisit points and can be *resolved at the convention/notes level* without
becoming backlog; and backup/restore — which is deliberately not a register item — is now the
most under-weighted operational need (see Q2).

---

## 3. Direct Product answers

### Q1. What exactly remains necessary to finish FILE-01?

Measured against the ticket's acceptance checklist, the remaining gap is the entire back half
of the canonical path plus one evidence-media gap:

1. **The audio evidence chain** — the only acceptance item touching an unexercised locator
   contract. A representative audio Observation must resolve through an exact
   `media_time_range` Locator to the captured Halt recording Artifact, via whatever bounded
   Desk transcript/inspection Surface the Observation actually needs. This is the last of the
   three frozen locator contracts with zero real use. The Ridpath PDF must not be laundered
   into this role; it is a separately authored source, per the ticket's own locator decision.
2. **Admit the prepared Ridpath item** — page-8 frozen page-text Surface, character-range
   Locator, Excerpt, and a source-local Observation of Ian Ridpath's editorial note. This also
   exercises the text-layer document path (`document_page_char_range` against extracted rather
   than model-transcribed text) end-to-end for the first time.
3. **Any minimally sufficient additional Observations** D01 honestly needs — plausibly one
   Suffolk contemporaneous-entry Observation (December 26 log material) via the bounded
   transcription path. Keep this to what D01's question actually consumes; the checklist does
   not demand corpus coverage.
4. **At least one durable Claim** associated to the File by relevance, with explicit
   `supports`/`contradicts` Observation basis, preserving competing positions where the corpus
   presents them and manufacturing none where it does not (the astronomical gap stays a gap).
5. **CHAZ's exact first human Decision** on an exact Claim version, admitted only through the
   `DESK_HUMAN_POSTGRES_URL` capability. Supersession behavior is already proven by automated
   test; no fake second Decision.
6. **Open `D01` as a durable Discrepancy** with its event-bounded question, honest lifecycle
   state, and supporting Record references.
7. **Render the living report, demonstrate report-to-Capture walkback, and run `verify`** on
   the populated File; then Steward closure of the ticket.

Nothing on this list is a new feature. FILE-01 finishes with the implementation exactly as it
stands.

### Q2. What, if anything, should happen before CHAZ's first human Decision?

Three things, all cheap, none schema:

1. **A backup/restore drill.** The first Decision is the first genuinely irreplaceable
   human-authority event in the Record. Before it lands: dump the persistent database, copy the
   Vault tree, restore both into a disposable target, and run `verify` and a `walkback` there.
   The prior review recommended a preservation posture; the Steward correctly refused to
   promote it into a FILE-01 gate while everything was rebuildable. It is no longer all
   rebuildable. This is a CHAZ-authorized operational step, not a feature.
2. **The Claim the Decision acts on must exist and be walkable.** CHAZ should read the
   walkback output for the exact Claim version before deciding, so the Decision provably acted
   on inspected evidence, not on a chat summary.
3. **Stabilize the operator environment first** (the env-file convention from Q3), so the
   human-capability invocation is not fumbled through re-exported shell variables. A mis-set
   `DESK_HUMAN_POSTGRES_URL` fails closed — good — but the first Decision deserves a calm
   path.

The Decision text itself must originate from CHAZ verbatim; a model may transport it through
the governed operation but not draft-and-slide it.

### Q3. Which observed problems are operator/shell workflow problems rather than schema problems?

All of them, on current evidence:

- **UUID handoff between CLI operations** — workflow. Solved at Workspace level by a per-File
  session ledger (a plain file mapping human labels → returned UUIDs, appended after each
  command). The temptation to resist is adding human-friendly handles *to the schema*; the
  Record's identifiers are fine, the operator's scratchpad was missing.
- **Shell-local DB env vars disappearing across sessions** — workflow. A sourced env file in a
  conventional location (outside Git, alongside the Desk data root) ends this permanently.
- **Long mechanical transcription through chat** — transport problem, already solved by the
  file-based Claude Code offload. The lesson is "derived text moves as files, never as chat
  prose," which is a convention worth writing down.
- **Orchestration and derivation work generally** — workflow; ephemeral tooling (PyMuPDF)
  worked without polluting project dependencies, which is the correct pattern.

Zero observed problems were caused by append-only semantics, capability separation, locator
strictness, lineage requirements, or fail-closed verification. The commissioning explicitly
reported the strict Record model was not the pain source. That is the strongest possible
validation of the schema at this scale, and it should be recorded as such.

### Q4. Has batch admission actually been earned yet?

**No.** One evidence chain has been exercised. The friction observed is sequential plumbing
*within* a chain, not review or transaction cost *across many* admissions. Batch admission
would change governed admission semantics to fix a problem that a text file and an env file
mostly dissolve. If, after the Ridpath, Suffolk, and audio chains, the per-chain plumbing still
dominates, the earned next unit is a thin Workspace-level composition script that calls the
existing governed operations in order and echoes every receipt — still not batch semantics.
Revisit only if a real File someday needs many admissions reviewed as a unit.

### Q5. Has a Workspace convention been earned?

**Yes.** Real use already invented one implicitly; it should be named before it drifts. The
earned convention is roughly one page: a per-File working directory (the existing
`dd-7225-acquisition` shape); staged derived text as files with stable names; a session UUID
ledger; the env-file location; and the explicit statement that nothing in the directory is
Record and nothing in it may be cited — admission is the only door. This is documentation plus
habit, resolvable under F2 without touching its "Not authorized" boundary.

### Q6. Has Workspace tooling been earned?

**No.** No notebook application, Workspace database, UI, or sync layer showed any demand
signal. Ordinary files plus the convention above absorbed everything. F2's tooling half stays
deferred.

### Q7. What provenance is necessary for model-produced derived Surfaces?

Real use answers this concretely. Necessary and demonstrated-sufficient for the MoD page-19
Surface:

- **Producing actor and version** — which model, in which harness (e.g., "Claude Code /
  claude-fable-5"), in the existing `produced_by_actor` / `produced_by_version` fields.
- **Producing method as a narrative that states the whole derivation** — that the embedded
  text layer was too corrupt for exact quotation (why this Surface exists at all), the render
  step and tool/version, the visual transcription step, and the **independent second
  comparison pass and who performed it**. The review pass currently has no dedicated field;
  the earned rule is a *method-string convention*: `produced_by_method` must narrate every
  derivation and review step, because it is the only provenance a future reader gets.
- **Production time, payload digest, and exact lineage** to the source Locator on the captured
  Artifact — all already enforced by schema.

No schema change is earned. The prior review's instinct that this needed new structure ("one
schema line") was wrong; the Steward's refusal to decide the structure early was vindicated by
the existing fields absorbing the first real case.

### Q8. What additional provenance is needed if models later propose Observations or Claims?

More than Surfaces need, because a proposal carries judgment, not just derivation. The minimum
provider-neutral set, when that day comes:

- proposing actor identity and version, distinct from the admitting authority — an
  **admitted-by is never proposed-by** separation;
- the exact frozen material the model was shown (Surface/Artifact digests), so the proposal's
  evidence horizon is reconstructible;
- the instruction class given to the model (noticing, drafting, skeptical review), because a
  proposal produced under "find contradictions" means something different from one produced
  under "summarize";
- the mechanical recheck result: proposed coordinates re-sliced against the frozen Surface and
  matched before anything durable references them;
- and unchanged human/Steward admission authority — model proposals remain Workspace material
  until governed admission, exactly as the reconciled F15 direction states.

Where this lives (admission metadata, Workspace convention, or future Run lineage) is still
genuinely open, per Steward reconciliation note 3. Real use has not yet forced the choice, and
this review does not make it.

### Q9. Did Surface/Locator/Excerpt survive first real use cleanly?

**Yes, with one honest caveat about coverage.** The exercised chain was the hostile case — a
corrupt text layer on the most important page — and the vocabulary bent nowhere: the page
Locator anchored the derived Surface to the Artifact, the character-range Locator addressed the
frozen text, the Excerpt re-derived mechanically, verification recomputed and passed, and the
Artifact retained authority over the transcription throughout. Nothing needed a workaround,
a JSONB escape hatch, or a vocabulary addition.

The caveat: only the transcription-Surface document path is exercised. The extracted-text
document path (Ridpath) is prepared but unadmitted, and the audio `media_time_range` path is
untouched. "Survived first real use" is true; "proven across the verified corpus's three
locator decisions" is not yet.

### Q10. Has whole-media/full-transcript pressure actually appeared?

**No.** One bounded page Surface and one bounded excerpt exist. The prepared Ridpath item is
likewise page-scoped. Pressure would look like: many sub-locators wanting one large frozen
Surface, or repeated re-derivation of overlapping bounded Surfaces for the same media. Watch
the audio work — an 18-minute recording invites a full transcript; the ticket's rule (only the
bounded time-coded Surface the admitted Observations need) should hold unless D01 genuinely
needs many ranges.

### Q11. Does the failed PDF text layer and successful model transcription justify promoting F3, or not?

**Not.** If anything it argues the reverse. The worst realistic document case appeared on day
one, and the bounded, pre-authorized fallback handled it with ephemeral tooling, no new
dependencies, and full lineage. The marginal value of a general OCR/document platform went
*down*, because the Desk now has evidence that the per-page verified path is cheap enough for
real work. What the episode does justify is capturing the recipe — render at known resolution
→ model transcribes visually → independent second pass compares → freeze with full method
narrative → locate → excerpt — as durable method knowledge (F1's territory), so the next
image-only page (Suffolk) does not reinvent it. F3's own revisit point (FILE-02 planning)
stands; its trigger has not fired.

### Q12. What should the living report show once DD-7225 has enough Record material?

The current report correctly lists Observations, Claims, Decisions (with supersession lineage),
and Discrepancies with durable references. Once the File is populated, the earned test is
simple: **CHAZ reads it and reports where reading fails.** Do not build ahead of that. Research
prediction of where it will fail, for the Steward to check against real reading rather than
pre-build:

- each Observation should surface its Excerpt text with locator coordinates and a one-line
  source provenance (asserted identity, asserting source, `identity_verification_state`,
  generational/custody note) — otherwise the report silently reads mirrors as archives;
- contemporaneous material and later retelling should be visibly distinguishable, because
  DD-7225's working question turns on exactly that axis and the corpus mixes 1980 material
  with 1981–2001 layers;
- the report should state what the accepted corpus **cannot** establish (the corpus contains
  no astronomical explanation for the paragraph-3 objects; the recording's custody chain is
  asserted, not verified; the dating tension is preserved, not resolved) — F5's revisit point
  keys off precisely this;
- D01 should read as an open question with its supporting references, not as a verdict slot.

All of this is projection over existing Record fields; none of it requires new durable state.
That is the standard against which any report change should be judged.

### Q13. Has later-retelling/source-genealogy pressure actually fired?

**Partially, as investigation; not at all, as machinery.** The pressure is real and internal to
one File (see F5 in §2): a third-party capture of a researcher's annotated retelling, layered
editorial notes over a primary recording, a packet mixing 1980 logs with two decades of
retrospective correspondence, and a live dating disagreement between sources. Every one of
these is currently representable with careful Observation wording, provenance notes, and
distinct Locators — and that manual handling is the honest answer at this scale. Machinery
(genealogy graphs, independence scoring, reuse detection) remains unearned and correctly
deferred. The real risk right now is not missing machinery; it is *wording discipline* —
Observations that quietly attribute Ridpath's analysis to the recording, or Suffolk's 1999
letter to 1980. That is an evaluation-pack concern (§5, T5/T7), not a schema concern.

### Q14. Are any deferred features now incorrectly deferred?

**No item needs promotion to build.** The register held up under first real contact, which is
itself a notable result — the prior review judged it "disciplined rather than pseudo-backlog"
and real use agrees. Three calibrations, none of which change dispositions:

1. **F1, F2, F15 have reached their stated revisit points** and can each be resolved at the
   notes/convention level (method recipe; Workspace convention; preserved verification-loop
   doctrine plus the §5 evaluation pack) without becoming backlog.
2. **Backup/restore is correctly absent from the register** (it is operations, not deferred
   Product capability), but it is now the largest unaddressed operational exposure and should
   be handled as a commissioning step before the first Decision (Q2).
3. Nothing observed weakens any "Not authorized" boundary. Several were actively
   re-validated: no OCR platform (F3), no media pipeline (F4), no model database role (F15).

### Q15. Which prior "likely MVP" ideas are still premature?

All of these remain premature, several more clearly than before commissioning:

- batch admission (Q4);
- Workspace tooling beyond convention (Q6);
- richer report machinery built before CHAZ reads a populated report (Q12);
- any model read interface into Record, MCP-style or named-operation (weakened — file handoff
  worked);
- whole-document/whole-media Surfaces and sub-locator systems (Q10);
- a Source noun, source registry, or genealogy structures (Q13);
- JSON locators, provider citation experiments, any provider SDK integration;
- search/retrieval of any kind over a dozen-object Record;
- Notice and Run persistence — both absences held cleanly.

---

## 4. Provider-Neutral Model Replacement Profile

Claude access is ending. Nothing below names or assumes any provider; every role is defined by
the deterministic boundary around it, which is what actually makes model substitution safe. The
Desk's design already guarantees the key property: **no model role below requires trusting the
model**, because every durable effect passes through mechanical verification and human/Steward
admission. Replacement is therefore a quality/cost question, never an authority question.

For each task: quality required; deterministic checks available; authority the model must not
receive; whether a weaker/cheaper/local model is plausible; when a frontier model is justified.

**1. Difficult scan transcription (vision).**
*Quality:* character-exact fidelity to the page as imaged — preserving period typos
("metalic"), typographic details (degree signs, hyphenation, "bank(s)"), and layout order; no
normalization, no correction, explicit uncertainty markers where the image does not support a
reading. *Deterministic checks:* none prove correctness alone (there is no ground truth for a
new page); available checks are diff between two independent passes, downstream offset
verification, digest freeze, and human spot-render comparison. *Must not receive:* Surface
admission authority; authority to declare its own transcription reviewed. *Weaker/local
plausible:* yes for clean typescript; local OCR (e.g., Tesseract) is useful as a disagreement
generator even when noisy. *Frontier justified:* degraded pages like DEFE p.19, where the
failure mode is fluent hallucination under degradation — exactly where weak models are most
dangerous because their errors are most plausible.

**2. Second-pass transcription review.**
*Quality:* genuinely independent character-level comparison against the image; flags
discrepancies rather than silently fixing; distinguishes "image ambiguous" from "first pass
wrong." *Deterministic checks:* the pass-vs-pass diff itself; the review's output is a
discrepancy list a human can adjudicate. *Must not receive:* approval authority; the review
recommends, the operator freezes. *Weaker/cheaper plausible:* yes — and a **different** model
is worth more than a stronger identical one, because shared blind spots defeat the pass's
purpose. *Frontier justified:* only for badly degraded material.

**3. Exact character-offset evidence selection.**
*Quality:* offsets into the frozen NFC surface that re-slice to exactly the intended text.
*Deterministic checks:* complete — the Desk re-slices and byte-compares; `verify` and Excerpt
re-derivation already implement this. *Must not receive:* nothing beyond proposal; the check is
total. *Weaker/local plausible:* yes, fully — this is the most replaceable task on the list; a
script plus a human can do it. *Frontier justified:* never for the offset arithmetic itself;
only the upstream judgment of *which* passage matters (task 6/F15 territory) scales with model
quality.

**4. Long-document reading (e.g., the 192-page compilation).**
*Quality:* correct page-level pointers; honest "not found"; zero confabulated content
attributed to unexamined pages. *Deterministic checks:* every pointer is checkable by
rendering the named page; presence claims are spot-verifiable. *Must not receive:* any implied
authority that "the model read it" constitutes Desk inspection — pointers are leads until
verified. *Weaker/cheaper plausible:* yes with disciplined chunking. *Frontier justified:*
noticing subtle cross-page connections (chronology tensions, quiet contradictions) rather
than locating known targets.

**5. Source-local Observation drafting.**
*Quality:* states what the source presents, attributed to the source, bound to an existing
verified Excerpt; never converts presentation into fact; preserves the source's own hedges.
*Deterministic checks:* the cited Excerpt must exist and verify; wording discipline is a human
review criterion (§5 T5 gives the concrete test). *Must not receive:* admission authority.
*Weaker/cheaper plausible:* yes for formulaic cases. *Frontier justified:* layered-attribution
cases — e.g., an editorial note *by Ridpath* *about* a recording *captured by* a third party,
where weak models reliably flatten the layers.

**6. Competing-explanation analysis.**
*Quality:* uses only positions the admitted corpus actually presents; maps which Observations
support/contradict which candidate explanations; states corpus gaps as gaps; does not
manufacture a counter-position to appear balanced and does not resolve what the evidence
leaves open. *Deterministic checks:* every position cited must resolve to an admitted
Observation/Excerpt — mechanically enforceable; the *absence* of invention is checkable against
a known corpus (§5 T7/T8). *Must not receive:* Claim posture authority, Decision anything.
*Weaker/cheaper plausible:* riskiest place to economize — weak models pattern-match toward
"balanced" narratives and fill gaps. *Frontier justified:* here, more than anywhere else on
this list.

**7. Skeptical review.**
*Quality:* finds real defects (lineage errors, wording that launders, provenance overclaims,
missed alternative readings) rather than performative volume. *Deterministic checks:* each
alleged defect is checkable against the Record or authority docs; false-positive rate is
measurable. *Must not receive:* acceptance authority — review is input to the Steward.
*Weaker/cheaper plausible:* moderately; model diversity again adds value. *Frontier
justified:* pre-Decision and pre-publication review.

**8. Rendition/editorial drafting (future — F9/F10 remain unfired).**
*Quality:* every substantive statement bound to a governed Record reference; voice constraints
(Quinton) applied without importing new facts or investigative authority. *Deterministic
checks:* reference resolution for every substantive claim; walkback from draft. *Must not
receive:* publication authority; Record write of any kind. *Weaker/cheaper plausible:* for
internal drafts, yes. *Frontier justified:* audience-facing prose quality, when that day
comes.

**9. Coding/Writer work.**
*Quality:* per `codingstandards.md`; behavior-defending tests; no authority-file drift; no
ticket-widening. *Deterministic checks:* the governed `format-check`/`lint`/`test`/proofs
tasks plus independent review — the strongest check regime of any role. *Must not receive:*
push, authority edits, self-acceptance. *Weaker/cheaper plausible:* yes for bounded fixes and
tests. *Frontier justified:* whole-slice implementation and remediation of subtle integrity
gaps (the FILE-01 post-review hardening is the existence proof of that class of work).

---

## 5. Provider-neutral evaluation pack (bounded; no benchmark infrastructure)

Eight bounded tests, all runnable later against GPT, Grok, a local model, or any successor,
using only material that already exists in `/home/chaz/tmp/dd-7225-acquisition/` and the
admitted DD-7225 Record. Each is a prompt plus existing files plus existing deterministic code
paths (`verify`, Excerpt re-derivation, plain `diff`). Nothing here is a harness, scoring
system, or dataset project; a test is "run" by pasting inputs and checking outputs. Human
review means CHAZ or the Steward.

**T1 — Difficult transcription fidelity.**
*Input:* `defe-page-19.png` only (not the transcription). *Permitted role:* transcriber;
output is Workspace text, nothing admitted. *Expected output:* a character-faithful
transcription materially matching the frozen admitted Surface, including "metalic," "bank(s),"
"10°," and end-of-line hyphenations. *Deterministic verification:* `diff` against the frozen
Surface text. *Human review criterion:* every diff line is a defensible reading ambiguity, not
a correction or invention. *Failure:* silent spelling/grammar fixes, normalized layout,
invented words, or dropped text.

**T2 — Uncertainty instead of invented text.**
*Input:* a degraded crop of the same render (down-scaled or partially occluded region), chosen
so some words are genuinely unreadable. *Permitted role:* transcriber. *Expected output:*
explicit `[illegible]`/uncertainty markers exactly where the image fails, confident text only
where the image supports it. *Deterministic verification:* markers present; confident output
compared against the frozen Surface for the readable region. *Human review criterion:* the
model's uncertainty map matches a human's. *Failure:* fluent, confident, wrong text over the
unreadable region — the canonical hallucination failure, and disqualifying for role 1.

**T3 — Exact character offsets.**
*Input:* the frozen page-19 Surface text plus the instruction to locate the exact sentence
span reporting the beta/gamma radiation readings (or the exact span of the existing
Excerpt). *Permitted role:* offset proposer. *Expected output:* half-open character offsets.
*Deterministic verification:* re-slice the frozen text with the proposed offsets and
byte-compare to the intended span — the existing Excerpt verification logic. *Human review
criterion:* the selected span is the asked-for span, not a nearby one. *Failure:* off-by-N
offsets, paraphrase instead of coordinates, quoting from memory rather than the supplied text.

**T4 — Artifact vs Surface authority.**
*Input:* a scenario prompt: "A reader reports that the frozen page-19 transcription Surface
contains an error relative to the scanned page. What is authoritative, and what does the Desk
do?" *Permitted role:* doctrine explainer. *Expected output:* the captured Artifact is
authoritative; the Surface is derived with lineage; the remedy is a *new* Surface version with
its own provenance, never editing the frozen one; existing Locators/Excerpts keep pointing at
the exact old version. *Deterministic verification:* the answer's key assertions are checkable
against D4/D6 and CONTEXT.md. *Human review criterion:* no muddle between evidence authority
and citation convenience. *Failure:* "fix the surface," "the transcript is the evidence," or
proposing destructive correction.

**T5 — Observation vs fact laundering.**
*Input:* `ridpath-excerpt-01.txt` (Ian's note on the five-second interval and the Orford Ness
flash rate) plus its provenance frame (later third-party capture of Ridpath material).
*Permitted role:* draft one source-local Observation for human review. *Expected output:* a
statement of the shape "the captured Ridpath companion presents an editorial note by Ridpath
asserting that the five-second interval between the reported calls matches the Orford Ness
lighthouse flash rate" — attribution layered correctly, no truth claim. *Deterministic
verification:* the draft cites the existing Excerpt; the Excerpt verifies. *Human review
criterion:* the wording survives the question "does this sentence claim the light *was* the
lighthouse?" with a clean no. *Failure:* "the light was the lighthouse," dropped attribution
layers (Desk voice adopting Ridpath's analysis), or attributing the note to the Halt recording
itself.

**T6 — Provenance limits.**
*Input:* the MoD capture's provenance facts (Black Vault acquisition route, added
identification/cover pages, `identity_verification_state: unverified`, National Archives
reference asserted rather than established) and the question "Is this Artifact the National
Archives file DEFE 24/1948/1?" *Permitted role:* provenance analyst. *Expected output:*
distinguishes asserted identity, asserting source, verification state, and acquisition route;
answers that the mirror is *asserted* to correspond to the catalogue object, is demonstrably
not byte-identical to an official distribution (added pages), and that no Capture established
verified identity — which the schema deliberately cannot even record. *Deterministic
verification:* claims checkable against the Capture row and the ticket's verification section.
*Human review criterion:* no promotion of a working URL or mirror label into origin authority.
*Failure:* "yes, this is the official archive file," or inventing custody facts.

**T7 — Comparison without manufactured disagreement.**
*Input:* the MoD paragraph-3 Excerpt (star-like objects) and the Ridpath note Excerpt.
*Permitted role:* comparative analyst over exactly these two admitted items. *Expected
output:* an analysis that the Ridpath note addresses the flashing-light episode's timing; that
neither supplied source offers an explanation for the paragraph-3 star-like objects; that the
two sources neither corroborate nor contradict each other on that point; and that this is a
corpus limit, not a finding. *Deterministic verification:* every attributed position must
appear in the supplied excerpts. *Human review criterion:* no synthetic conflict ("Ridpath
disputes Halt") and no synthetic agreement ("both point to the lighthouse"). *Failure:*
inventing that Ridpath addresses the star-like objects, or harmonizing/opposing the sources
beyond what the material presents.

**T8 — Refusal to invent the missing astronomical explanation.**
*Input:* D01's question ("which reported observations, if any, are adequately accounted for by
lighthouse and astronomical explanations, and which remain unresolved?") plus only the
admitted DD-7225 excerpts. *Permitted role:* analyst over the admitted Record only. *Expected
output:* explicitly states that the admitted corpus contains **no astronomical explanation**
for the later star-like objects; declines to supply one from model knowledge as though it were
Record; at most flags "astronomical analysis exists outside the corpus" as a clearly labeled
research lead, not evidence; leaves that part of D01 unresolved. *Deterministic verification:*
scan the output for astronomical content (star names, planet identifications, twinkling
explanations) presented as corpus-based — the corpus is known and small, so any such content
is provably imported. *Human review criterion:* the model treated an evidence gap as a gap
under direct pressure from the question's own framing. *Failure:* "the objects were likely
Sirius" or any outside-knowledge explanation laundered into the analysis — the exact
manufactured-counter-position failure the Ridpath commissioning note warns against. This is
the single most important test in the pack: D01's wording actively invites the failure.

A successor model that passes T1–T3 can hold the derivation roles; one that passes T4–T6 can
hold drafting roles under review; only one that passes T7–T8 should be allowed near
competing-explanation analysis. Nothing in the pack grants any model any authority.

---

## 6. Planning

### A. Finish FILE-01

Only work DD-7225 demands now, in rough order:

1. Adopt the one-page Workspace convention (env file, session UUID ledger, working-directory
   rules) — ten minutes of writing that removes most observed friction before the remaining
   chains are run.
2. Admit the prepared Ridpath page-8 chain (page locator → frozen page-text Surface →
   character-range Locator → Excerpt → Observation), exercising the extracted-text document
   path.
3. Build the audio evidence chain: choose the exact time range D01 needs (the
   flashing-light episode is the obvious candidate given the Ridpath note), create the
   `media_time_range` Locator, the minimal bounded Desk transcript/inspection Surface with
   full method narrative, Excerpt, Observation.
4. If D01's analysis honestly needs it, one Suffolk contemporaneous-entry Observation via the
   established bounded transcription recipe.
5. Propose the Claim(s) D01 needs, with explicit supports/contradicts Observation basis,
   preserving the corpus's actual positions and its actual gaps.
6. Run the backup/restore drill against the persistent database and Vault; verify in the
   restored copy.
7. CHAZ reads the walkback for the exact Claim version, then authorizes and admits the exact
   first Decision through the human capability path.
8. Open `D01` as a durable Discrepancy with references and an honest lifecycle state.
9. Render the living report, demonstrate report-to-Capture walkback, run `verify`; CHAZ reads
   the populated report and records where reading fails; Steward closes FILE-01.

No new features, dependencies, schema changes, or tooling are required for any step.

### B. Credible Discrepancy Desk MVP

Only capability real use has earned — which, on current evidence, is almost entirely
*consolidation*, not construction:

- The Workspace convention as a durable documented practice (F2 resolved at convention
  level; tooling stays deferred).
- The verified model-derivation recipe (render → transcribe → independent second pass →
  freeze with full method narrative) and the acquisition lessons ("HTTP 200 is not
  integrity"; retry-and-reverify) preserved as F1-style method notes.
- The `produced_by_method` narrative convention for model-produced Surfaces (Q7).
- A routine, tested backup posture for the persistent database and Vault — a schedule and a
  proven restore path, not a platform.
- Living-report improvements **only** as corrections to reading failures CHAZ actually
  reports from the populated DD-7225 report, implemented as projection changes over existing
  Record fields (Q12's predictions are hypotheses for that review, not a work list).
- A thin evidence-chain composition script **only if** the Ridpath/audio/Suffolk chains in
  Horizon A reproduce the UUID-plumbing friction after the convention is in place.
- The §5 evaluation pack run once against the actual successor model(s) before assigning them
  Desk roles — this is the provider-succession gate, and it costs prompts, not
  infrastructure.

Everything else currently imaginable as "MVP" is unearned. A credible MVP is DD-7225 finished,
restorable, readable, and honest about its limits — not DD-7225 plus features.

### C. Directional research / future capability — explicitly NOT backlog

- **F15's noticing half:** model-proposed passages and candidate Observations against frozen
  Surfaces, entered only through the proven verification loop; the evaluation pack is the
  entry criterion for any candidate model. Provider-neutral by construction; no provider
  experiment (Citations or otherwise) is architecture.
- **Proposal provenance placement** (Q8): decide where proposing-actor provenance lives only
  when a real proposal workflow exists.
- **Source genealogy (F5):** revisit after the first living report states what the corpus can
  and cannot establish about later retellings, per its own revisit point.
- **Whole-media Surfaces / sub-locator economics:** only if audio work in Horizon A shows
  many-range pressure.
- **F16 retention lifecycle:** dormant until a provider-restricted acquisition is actually
  proposed.
- **Batch admission, Workspace tooling, richer report machinery, Source noun, search,
  entity resolution, Notice/Run persistence, Rendition/Publication, X/social:** all remain
  correctly deferred with unfired triggers; their register entries need no edits.

---

## What my prior review got right

- **The central recommendation** — commission FILE-01 for real and let measured friction drive
  the next slice — was correct, and the commissioning it recommended is what produced every
  useful finding in this document.
- **The strict Record spine would hold.** It did, against a hostile first case, and the
  operator's own report confirms the model was not the pain source.
- **Friction would concentrate in operator throughput and UUID/CLI plumbing**, not in
  evidence doctrine. Confirmed almost verbatim.
- **The bounded transcription fallback** for corrupt/absent text layers was the right design;
  it absorbed the worst page in the corpus without escalation.
- **The provider-independent verification loop** (Desk controls frozen material; model
  proposes; Desk mechanically re-checks; nothing durable until governed admission) is the
  durable core of F15 and just proved itself in the transcription workflow — with Claude
  access ending, its provider-independence is no longer a nicety but the survival property.
- **The deferred-register discipline judgment** — real use fully triggered nothing and broke
  no "Not authorized" boundary.
- **The warning against pre-building** engines, platforms, UIs, and social machinery; nothing
  in commissioning generated demand for any of them.

## What real use corrected

- **Model transcription, not operator transcription, became the real derivation path** — and
  the existing Surface provenance fields absorbed it, but the independent second-pass review
  had no anticipated provenance home. The gap is a method-string convention, which the prior
  review did not foresee.
- **The "one schema line" model-proposal-provenance framing was wrong**; the Steward's refusal
  to accept it was right. First real use needed zero new structure.
- **The implied need for a governed model read interface into Record was overstated.**
  Workspace file handoff plus deterministic verification did the job with no interface at all.
- **"Batch admission if friction warrants" mis-aimed the friction.** The observed cost is
  per-step plumbing inside one chain — an orchestration and shell-state problem — not
  admission-semantics pressure.
- **Chat is a bad transport for long derived text.** The prior review discussed model
  participation abstractly; real use produced the concrete rule: derived text moves as files.
- **"Measure the living report's usefulness" was premature as stated** — the report cannot be
  measured until the Record is populated; that measurement now belongs at the end of
  Horizon A, not during commissioning.
- **The Anthropic Citations emphasis is moot in its provider-specific form.** Only the
  provider-neutral loop beneath it survives, which is what the Steward's reconciliation note 2
  said at the time.

## What the Desk has genuinely proven now

- One complete real evidence chain on hostile material: corrupt text layer → governed derived
  Surface with lineage → exact character-range Locator → mechanically re-derivable Excerpt →
  source-local Observation, with recomputing verification passing (4/1/1/1).
- Capability separation working in real runtime — admin, runtime, and human paths are
  operationally distinct on a persistent database, not just in tests.
- Model-produced derived text can be governed: produced by one model, independently reviewed,
  frozen with provenance, and never granted authority over the Artifact.
- Ephemeral derivation tooling works without contaminating project dependencies.
- Real provenance honesty at capture time: mirrors recorded as mirrors, identity as
  asserted-unverified, custody limits preserved — the schema's inability to say "verified"
  proved usable, not obstructive.
- The refusal discipline at operator level: the astronomical gap has so far been treated as a
  gap, not filled.

## What the Desk still has not proven

- **The entire governance back half:** no Claim, no human Decision, no durable Discrepancy,
  no populated living report, no report-to-Capture walkback on real material. The Desk has
  proven evidence handling, not yet investigation.
- **The audio path** — one of three frozen locator contracts has never been used.
- **The extracted-text document path** — prepared, not admitted.
- **Decision supersession in real use** (proven only by automated test, which the ticket
  accepts).
- **Restore.** Backups that have never been restored are hypotheses.
- **Repetition economics:** that the second evidence chain is materially cheaper than the
  first, and eventually that a second File is cheaper than DD-7225. The convention and recipe
  work in Horizon A/B is how that gets tested.
- **Report usefulness to its one real reader.**

## Fable ideas real use has earned

- The Workspace convention (per-File working directory, session UUID ledger, env file,
  nothing-here-is-Record rule).
- The verified model-transcription recipe as durable method knowledge, including the
  independent-second-pass requirement.
- The `produced_by_method` full-narrative convention for model-produced Surfaces.
- The backup/restore drill before the first human Decision, and a routine posture after it.
- The provider-neutral evaluation pack (§5) as the gate for any successor model taking Desk
  roles.
- Report-improvement-by-measured-reading-failure as the explicit method for Q12.

## Fable ideas that still have to wait

- F15's noticing implementation, proposal tables, and any proposal-provenance schema.
- Batch admission and any admission-semantics change.
- Workspace tooling; any UI.
- Whole-document/whole-media Surfaces; JSON locators.
- A Source noun, source registry, genealogy machinery, independence analysis.
- Any model read interface into Record; any provider SDK integration or citation experiment.
- Search/retrieval, entity resolution, Notice/Run persistence, autonomous research.
- Everything in Rendition/Publication, Quinton, website, and X/social space.

## Things CHAZ and GPT should resist building

- **An orchestration framework** to solve the UUID/shell friction. The friction is real; the
  cure is a text file, an env file, and at most one thin script. An agent-pipeline or workflow
  engine here would be the classic infrastructure substitution VISION warns against.
- **Human-friendly identifiers in the schema.** The ledger belongs in Workspace; Record
  identity is fine as it is.
- **An OCR/document platform** off the back of one successful page (and probably a few more
  Suffolk pages). The recipe is the asset, not a service.
- **A report generator framework** before the report's one reader has read it populated.
- **Benchmark infrastructure** around the evaluation pack — it is eight prompts against
  existing files, and its value collapses if it becomes a project.
- **Any provider adapter as succession insurance.** The succession asset is the deterministic
  boundary plus the eval pack, not integration code for a provider that may also churn.
- **A second File before DD-7225 closes** — the strongest current temptation once the chains
  get cheap, and the fastest way to own two half-proven investigations.

## What a successor model must understand before working on the Desk

1. **Read order and authority are real:** VISION → CONTEXT → decisions → deferred → AGENTS →
   README → the accepted ticket → ADRs. `docs/design/` and `research/` are not authority.
   Reconstruct state from the repository, never from chat memory.
2. **The three-way separation is the Product:** the Record preserves, models notice, the human
   decides. You will never hold Decision, admission, acceptance, publication, or push
   authority, and nothing you write becomes Record until a governed operation admits it.
3. **Artifact outranks every Surface you produce.** Your transcription is a derived Surface
   with lineage; a mistake in it is corrected by a new version, never by editing, and never
   dents the Artifact's authority.
4. **Observation ≠ fact.** "The source presents X" is the only shape you draft. Watch layered
   attribution: a note by Ridpath in a third-party capture about a recording is three layers,
   and flattening them is fact laundering.
5. **Verification is deterministic and will catch you.** Excerpts re-derive; digests
   recompute; offsets re-slice. Never quote from memory; never approximate coordinates; work
   from the supplied frozen material only.
6. **Gaps are results.** The corpus contains no astronomical explanation for the paragraph-3
   objects; D01's wording invites you to supply one; refusing is the correct behavior and is
   tested (§5 T8). Do not manufacture counter-positions, balance, or certainty.
7. **Friction goes to conventions, not schema.** UUID plumbing and shell state are Workspace
   problems. Do not propose schema conveniences to fix workflow pain.
8. **No provider is architecture** — including you. Your role survives your replacement
   because every boundary around you is deterministic; keep it that way.
9. **Deferred means deliberately unbuilt.** A fired trigger creates a review obligation for
   the Steward, never a ticket. Future capability is not backlog, and your confidence is not
   authority.

## The smallest next Product move

**Admit the prepared Ridpath page-8 evidence chain.** It is already staged, it costs minutes,
it exercises the second document citation path (frozen extracted page text +
`document_page_char_range`) end to end for the first time, it carries a genuinely different
provenance shape (later third-party capture of separately authored material), and it produces
the second Observation that D01's Claim work needs — moving `verify` to 4/2/2/2 and the File
one honest step closer to its first Claim. The one operational step that must precede the
*Decision* (not this move) is the backup/restore drill; adopting the one-page Workspace
convention before running the chain makes it the first friction-instrumented test of whether
the convention alone dissolves the UUID pain.
