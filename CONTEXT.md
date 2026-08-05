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
quotation, carrying six independent evidence dimensions. Either `unconfirmed`
(model-proposed) or confirmed (human-set).
_Avoid_: fact, assertion, finding, statement

**Source**
An artifact and its intrinsic provenance, stored once and reusable across cases.
Case-specific relevance and notes live on the case-source relationship, not the
source.
_Avoid_: reference, citation, link, document

**Capture**
The stored, hashed, byte-exact result of one read of external material, whether or
not it ends up supporting a claim. Two reads of the same URL are two captures.
_Avoid_: fetch, scrape, download, snapshot

**Cited / examined / unexamined**
The three states of a capture. Cited — a claim binds to it. Examined — a run looked
and found nothing worth claiming. Unexamined — nobody has looked.
_Avoid_: promoted, relevant, used, processed

**Locator**
An address into a capture's parsed element structure. Must resolve, and the quoted
text must match byte-exact at that position, for a claim to be accepted.
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
its lineage back to the question that prompted it.
_Avoid_: session, task, job, pass

**Rubric**
A versioned set of standing questions attached to one operation — reading a source,
extracting a claim, proposing an angle. Every claim records the rubric version that
produced it. Changes never apply retroactively.
_Avoid_: prompt, template, guidelines, instructions

**Open question**
A first-class worked object recording something the case does not know, carrying a
disposition that distinguishes permanently unresolved from not yet worked.
_Avoid_: todo, gap, unknown, issue

**Lead**
A URL dropped into the inbox unattached to any case, captured on drop, holding
material and an optional summary but never claims.
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
