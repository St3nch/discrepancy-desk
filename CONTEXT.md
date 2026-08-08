# Context

The vocabulary of The Discrepancy Desk. Every term below has one meaning in this
codebase, and the `Avoid` list names the words that must not be used for it.

This file is a glossary and nothing else. Decisions go in `docs/adr/`. Product
doctrine lives in the `discrepancy-desk-docs` repository. If this file starts
holding implementation detail or design rationale, that is the failure the
previous project made, and the correct fix is to move the content out.

Update it in the moment a term is challenged, sharpened, or resolved — never in a
batch afterwards. A stale glossary is worse than none, because it is trusted.

---

## Core objects

**Case**
The durable investigation into one topic. Owns sources, claims, entities,
conflicts, timeline, open questions, and angles. Never completes; goes dormant and
wakes.
_Avoid_: dossier, topic, work item, story, investigation

**Rendition**
One publishable artifact belonging to exactly one case and one angle, targeting
one platform and format. Generated independently (D7), never cut from another
rendition. Proposed by the executor through MCP (`propose_rendition`) under a
composition rubric — the backend never calls a model. Records the rubric version
it was composed under. Lifecycle includes `draft` (ticket 12), then cleared /
published / rejected in later tickets. A unit may only cite claims from that
angle's confirmed set.
_Avoid_: post, draft, content item, work item, piece

**Unit**
One ordered component of a rendition — a single post within an X thread, a section
within an article. The thing approval binds to. Required qualification language
on a cited claim must appear in the unit body that cites it.
_Avoid_: tweet, segment, part

**Angle**
The developed answer to "what makes this story worth reading," living inside a case
and linking to claims. Status is `active`, `chosen`, or `dismissed`. Dismissed
angles keep their reasoned dismissal forever (never deleted or overwritten).
Produces renditions; has no separate lifecycle object beyond those statuses.
_Avoid_: hook, take, framing, pitch

---

## Evidence

**Claim**
A proposition recorded in the Record, bound to captured bytes by byte-exact
quotation (against `elements.text` at a locator), or a `desk_inference` citing
other claims. Carries six independent evidence dimensions. Either `unconfirmed`
(model-proposed) or confirmed (human-set). Unconfirmed must be visually loud
everywhere it appears.
_Avoid_: fact, assertion, finding, statement

**Evidence dimensions (six, no score)**
Independent classifications on a claim (VISION §11). Never compressed into one
score. Proposed by the executor at `propose_claim`; authoritative values set only
by the human at confirmation (ticket 11).

| Dimension | Values |
|---|---|
| Source basis | `contemporaneous_record`, `contemporaneous_report`, `direct_participant_recollection`, `later_retrospective_claim`, `scholarly_interpretation`, `technical_inference`, `desk_inference`, `other` |
| Corroboration | `unassessed`, `single_source`, `multi_source_dependent`, `independently_corroborated`, `contradicted` |
| Certainty | `unassessed`, `established`, `probable`, `contested`, `speculative`, `unknown` |
| Posture | `factual_assertion`, `interpretation`, `participant_account`, `allegation`, `disputed_assertion`, `research_lead`, `pattern_candidate` |
| Required qualification | free text — exact language that must accompany any use; required non-empty when posture is `allegation` or `participant_account` |
| Publication risk | `unknown`, `living_private`, `public_official_official_capacity`, `public_figure`, `deceased`, `institution`, `not_applicable` |

_Avoid_: confidence (for certainty), score, rating, risk score

**Source**
An artifact and its intrinsic provenance, stored once and reusable across cases.
Case-specific relevance and notes live on the case-source relationship, not the
source.
_Avoid_: reference, citation, link, document

**Capture**
The stored, hashed, byte-exact result of one read of external material, whether or
not it ends up supporting a claim. Two reads of the same URL are two captures.
Owned by a run (counted against that run's capture budget) or by a lead (no run,
no budget). `run_id` and `case_id` are null for an unattached lead capture; attach
or promote sets `case_id`. Lead drops and run captures use the same Vault path —
same store, hash, parse, and element structure.
_Avoid_: fetch, scrape, download, snapshot

**Cited / examined / unexamined**
The three states of a capture. Cited — a claim binds to it (`propose_claim` sets
this). Examined — the executor explicitly reported at `close_run` that it looked
and found nothing worth claiming (`examined_capture_ids`; F-32). Unexamined —
nobody confirmed looking. Uncited is not examined; a truncated locator map alone
is not examination. Cancel does not change capture status.
_Avoid_: promoted, relevant, used, processed

**Locator**
An address into a capture's parsed element structure (`document_versions` →
`elements` → `regions`). Must resolve, and the quoted text must match the
quotation surface exactly (F-13: against derived `elements.text`, not raw Vault
bytes). Forms:

| Form | Surface |
|---|---|
| `e/{ordinal}` | Full element text |
| `e/{ordinal}/r/{start}-{end}` | Character slice of element text (`start` inclusive, `end` exclusive) |

A bare `e/{n}` means the quotation surface is the **entire element**, not text findable
within it. `find_quote` (MCP, read-only) takes a capture id and an exact substring and
returns the region locator, or a structured miss (`not_found` vs multiple matches). Exact
substring only — no fuzzy matching. `propose_claim` still verifies independently.

_Avoid_: pointer, position, offset, anchor

**Confirmed**
State of a claim whose evidence dimensions have been set by the human. Confirmation
attaches at the moment of use — when the claim is linked into Angle Room work
(angle, public question, or quotation shelf) — not at storage (ADR 2).
`confirmed_at` on the claim is the time of the **last** confirming act; it is not
a first-confirmation timestamp. `claim_confirmations` is the append-only correction
log (prior values vs confirmed values, actor, timestamp — VISION §18). Same
projection-versus-history pattern as suspensions and open questions. Re-confirmation
is allowed so correction-rate is measurable across decisions; re-confirming a cited
claim to non-publishable risk is refused while a confirmed inference still cites it
(D21). Crossing the inference / non-inference source_basis boundary at confirmation
is refused — support structure is fixed at proposal. Prerequisite for use in any
rendition; the rendition-eligible set is angle-scoped confirmed claims linked through
`angle_claims` (D2), not case-wide.
_Avoid_: verified, approved, accepted, cleared

**Cleared**
State of a rendition whose exact content the human has approved for publication.
Clearance is an **append-only approval record** carrying the ordered unit bodies as
reviewed (actor, timestamp, snapshot). The rendition holds status and a pointer for
projection; whether that clearance still stands is **derived** by comparing current
content to the snapshot — not an `is_valid` flag. Reorder, edit, add, or remove units
invalidates the standing approval without silently reverting status to draft. Re-clear
after edit is a new record. Media binding is deferred until renditions carry media.
_Avoid_: approved, signed off, confirmed, ready

---

## Research

**Run**
One dispatched research job with an explicit question, a bounded scope, a rubric
version, and a capture budget. Produces claims and new open questions, and records
its lineage back to the question that prompted it. Claimed by an executor via
pull (`claim_next_run`), never pushed to a named executor.
_Avoid_: session, task, job, pass

**Run status**
The lifecycle state of a run. Full vocabulary (do not invent local subsets):

| Status | Meaning |
|---|---|
| `draft` | Question written, not yet approved |
| `approved` | Claimable |
| `claimed` | An executor holds it and is working |
| `suspended` | The executor asked a question; waiting on the human |
| `complete` | Closed normally, findings recorded |
| `abandoned` | Claimed but never closed; reclaimable (lease mechanics later) |
| `cancelled` | The human killed it |

`claimed` carries a lease refreshed by executor tool calls; if the lease expires,
the run reverts to `approved` (evaluated on claim/list/approve — no sweeper) and
prior captures/claims remain attached. Ticket 03+ implement transitions
incrementally; the full set stays in schema CHECK constraints.

`suspended` is mid-flight suspend-and-ask (not an error path): the executor
records a question, what it is uncertain between, and a default action; the
operator answers; the run returns to `claimed` with the same claim_token and a
fresh lease. While suspended there is no lease (waiting is not abandonment). A
suspended run still serialises the case (counts as active alongside approved
and claimed). Each suspension is a durable ordered instance (`run_suspensions`);
the run holds only a projection of the latest for list rendering. Answering
resolves *this instance*; amending a rubric resolves *the class* — the operator
UI must distinguish those remedies. If a suspension (or any open run) must die
without an answer, the human cancels it (`cancel_run`); there is no executor
self-cancel. The executor learns answers and run state via `read_case_context`
(claim_token proves authority, not knowledge of decisions).
_Avoid_: state (alone), phase, stage (for run lifecycle)

**Rubric**
A versioned set of standing questions attached to one operation — reading a source,
extracting a claim, proposing an angle. Every claim records the rubric version that
produced it. Changes never apply retroactively.
_Avoid_: prompt, template, guidelines, instructions

**Open question**
A first-class worked object recording something the case does not know, carrying a
disposition that distinguishes permanently unresolved from not yet worked.
Proposed by the executor at `close_run`; the operator approves, rejects, edits, or
replaces each item. Lineage records which run introduced it and which research
question prompted that run.

Dispositions (set on approve/replace only):

| Disposition | Meaning |
|---|---|
| `not-yet-worked` | A to-do — may become a later run |
| `unresolved-awaiting-external-development` | Parked; waiting on the world |
| `unresolved-likely-permanent` | Honestly labelled; may stay open |

A case can be publication-ready with many open questions if they are not all
`not-yet-worked`. Rejected proposals are not open questions.
_Avoid_: todo, gap, unknown, issue

**Run close (D13)**
When a run completes, the operator screen leads with the agenda (new open
questions), then counts of captures/claims, then self-reported low confidence,
then claim/capture detail *behind a fold*. Claim confirmation must not feel
available at close — confirmation needs an angle purpose (ticket 11). The
operator may approve/reject/edit/replace proposals *or write their own* open
question (D5 / F-31), including when the executor proposed none. At close, only
captures listed in `examined_capture_ids` become `examined`; other uncited
captures stay `unexamined`.
_Avoid_: run summary, debrief (alone)

**Lead**
A URL dropped into the inbox unattached to any case. Capture is always attempted
on drop (same Vault path as a run capture). Holds material and an optional
operator-authored summary but never claims. Auth-walled or paywalled URLs are
recorded as `identity_only` — explicitly not captured; that product state is
distinct from an SSRF refusal (fail-closed, no lead written). `identity_only` is
triggered by HTTP response status alone (401/402/403); soft walls that return
200 OK with login or subscription HTML are captured like any other material.
There is no automatic wall detection, no content inspection that discards bytes
on a heuristic, and no operator "not usable" mark (D19). An unsupported content
type after a successful fetch (PDF, audio, etc.) records `unsupported_type` —
URL parked, `capture_id` NULL, no Vault object (ticket 09a); same insert pattern
as `identity_only`, not a change to the retain path. SSRF and hard fetch
failures still refuse with no lead. A successful lead capture stays `unexamined`
until a run on the attached case reports it in `examined_capture_ids` at close
(or cites it). Operator may attach to an existing case, promote to a new case,
dispose, or summarise (skippable). `add_lead` is on both transports (D18); MCP
requires a live claim (lease) but does not charge capture_budget;
attach/promote/dispose/summarise are API-only.
_Avoid_: bookmark, saved link, tip, idea

**Coverage**
The gauge reporting which of the six research stages a case has genuinely worked.
Not a state machine; a readiness reading (D20). A run carries one
`coverage_dimension` set by the operator at dispatch — not executor-writable,
not touched at `close_run`. Pre-D20 runs have `NULL` dimension and never count
toward a stage. Readings: `unworked` (no completed run targeting the dimension
produced claims), `worked` (such a run exists), `complete` (operator attestation
still stands), `unmeasurable` (no first-class measuring object exists yet).
`complete` is human attestation with actor and timestamp, not a count; the write
refuses while unexamined captures remain (`COVERAGE_UNEXAMINED_REMAIN`), and may
carry `examined_capture_ids` (same F-32 report as close). Later unexamined
captures make an attestation stale (reading returns to `worked`). Angle work is
hard-blocked until `official_foundation` reads complete
(`assert_official_foundation_complete` — call site ticket 11).
_Avoid_: progress, completeness, status, stage label (as an executor-declared field)

**Coverage stages (six, fixed order for display only)**
`official_foundation`, `public_question`, `deep_context`, `story_intelligence`,
`editorial_development`, `composition`. Display order is not a pipeline.
Measurable: `official_foundation` and `deep_context` via runs; `public_question`
and `editorial_development` via Angle Room objects with claim links (ticket 11);
`composition` via renditions with ≥1 unit that cites ≥1 claim (ticket 12).
Still unmeasurable as a stated decision (no distinct measuring object — not
neglect): `story_intelligence` (entities/conflicts/timeline not built; do not
infer from angle existence — the proxy D20 rejects).
_Avoid_: phase, pipeline step, level

**Public question**
A first-class Angle Room object recording what people are actually asking about a
topic, what version of the belief circulates, and where it came from. An
observation about the discourse, not a claim about the world — but every Angle
Room item must link to at least one claim (VISION §7); links use confirmation-at-use.
_Avoid_: the theory, popular belief, the narrative

---

## Runtime

**Executor**
The LLM client that claims a run and works it through the tool surface.
Interchangeable by design; holds no run state and creates no artifacts directly.
Assumed untrusted.
_Avoid_: agent, model, worker, assistant

**Tool surface**
The MCP-exposed set of backend operations through which every executor acts. The
only path by which anything enters the Vault or the Record; its refusals are the
enforcement.
_Avoid_: API, endpoints, integration, interface

---

## Storage layers

**Vault**
Byte-exact capture of external material — immutable originals, acquisition
receipts, versioned normalized element packages with addressable locators. Answers
"what exactly do we have?"
_Avoid_: storage, archive, files, blob store

**Record**
The editorial database — cases, claims, entities, conflicts, timeline, open
questions, publication-risk classifications, audit lineage. Answers "what can we
prove?"
_Avoid_: database, DB, store, index

**Angle Room**
Where a story's editorial value is worked — central discrepancy, public question,
human conflict, quotation shelf, missing records, narrative turns, competing angle
candidates. Answers "what makes this worth reading?" Every write path requires
`official_foundation` complete (D20). Every item links to ≥1 claim (VISION §7);
empty angles are drafts, and choosing one requires linked confirmed claims. The
quotation shelf holds operator-selected bindings with speaker and attribution
frame — not an automatic dump of every quote on linked claims. Region locators
are preserved when supplied (`e/{n}/r/{start}-{end}`). Shelf remains **case-scoped**
(ticket 12 evidence: composition eligibility is angle-scoped; the shelf is a
shared pool of strongest quotations for the case, not a second eligibility
boundary). Whole-element locators (`e/{n}`) are allowed when the element *is* the
quotation.
_Avoid_: editorial, drafting, workspace
