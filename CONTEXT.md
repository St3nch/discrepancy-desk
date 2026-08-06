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
One publishable artifact belonging to exactly one case, targeting one platform and
format. Carries the publication lifecycle.
_Avoid_: post, draft, content item, work item, piece

**Unit**
One ordered component of a rendition — a single post within a thread, a section
within an article. The thing approval binds to.
_Avoid_: tweet, segment, part

**Angle**
The developed answer to "what makes this story worth reading," living inside a case
and linking to claims. Produces renditions; has no lifecycle of its own.
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

_Avoid_: pointer, position, offset, anchor

**Confirmed**
State of a claim whose evidence dimensions have been set by the human. Prerequisite
for use in any rendition.
_Avoid_: verified, approved, accepted, cleared

**Cleared**
State of a rendition whose exact content the human has approved for publication.
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
There is no automatic wall detection and no content inspection that discards
bytes on a heuristic. A successful lead capture stays `unexamined` until a run
on the attached case reports it in `examined_capture_ids` at close (or cites
it). Operator may attach to an existing case, promote to a new case, dispose, or
summarise (skippable). `add_lead` is on both transports (D18); MCP requires a
live claim (lease) but does not charge capture_budget; attach/promote/dispose/
summarise are API-only.
_Avoid_: bookmark, saved link, tip, idea

**Coverage**
The gauge reporting which of the six research stages a case has genuinely worked.
Not a state machine; a readiness reading.
_Avoid_: progress, completeness, status

**Public question**
A first-class Angle Room object recording what people are actually asking about a
topic, what version of the belief circulates, and where it came from. An
observation about the discourse, not a claim about the world.
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
candidates. Answers "what makes this worth reading?"
_Avoid_: editorial, drafting, workspace
