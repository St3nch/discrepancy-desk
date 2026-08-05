# First Destination — One Complete Vertical Pass

Status: ready-for-agent

## Problem Statement

The operator (a single human, editor-in-chief and sole authority) wants to turn open-web
research into publishable editorial content about anomalies and disputed claims, with an
LLM doing all the production work — research, source capture, claim extraction,
classification, angle development, and drafting. He needs to retain absolute authority over
what counts as evidence, what gets published, and exactly what text goes out, because the
executor doing the research cannot be trusted not to fabricate a source or a quotation.

A previous build of this system failed to deliver this: it grew to 309 planning documents
across 131 planning packages and 99 audit records, and never published a single post from
the system it was documenting. Its one live research pass — the 1979 Vela Incident — ended
in five retired drafts, nine sources with zero source notes, and one draft stored as an
unstructured blob with no claim structure beneath it. Governance outran execution.

The operator needs a working system, not more planning: one real case, researched by a
connected LLM against the open web, with every citation traceable to byte-exact captured
material, developed into one angle, rendered as one platform-native rendition, cleared by
him, and published — proving the architecture on the exact material that broke the last one.

## Solution

Build the backend that owns the Vault (byte-exact captured material), the Record (cases,
claims, entities, evidence), the Angle Room (editorial development), and the run registry,
exposing an eight-call tool surface over MCP as the only path by which a research executor
can act. A browser client exposes the human-facing operations: dispatching runs, resolving
suspended runs, working run-close agendas, confirming claims, developing and choosing
angles, approving exact rendition content, and recording publication.

Prove the whole vertical slice on one case — the Vela Incident, using the nine sources
already identified from the prior build's failed pass — carried through to one X thread,
cleared and posted manually. Everything else (other platforms, other formats, metrics,
cross-case pattern detection, multi-account UI) is extension off this proven spine, not
part of this destination.

## User Stories

### Capture / Vault

1. As the operator, I want every URL the executor reads to be fetched and stored by the
   backend, so that nothing can be cited that was not first captured.
2. As the operator, I want each capture stored as immutable raw bytes with a SHA-256 hash,
   so that I can trust the material has not been altered after capture.
3. As the operator, I want each capture parsed into an addressable element structure
   (`document_versions → elements → regions`), so that claims can bind to an exact locator
   inside it.
4. As the operator, I want generated Markdown/HTML projections of a capture to be clearly
   read-only and non-authoritative, so that I never mistake a derived view for the original.
5. As the research executor, I want `capture_url` to return the capture ID and a locator map
   with element text, so that I can quote exact bytes back at `propose_claim` time.
6. As the research executor, I want a `read_capture(capture_id, range)` tool for material
   beyond the initial response's size cap, so that I can read deeper into a long document
   without `capture_url` flooding my context.
7. As the operator, I want every capture to count against its run's budget the moment it is
   made, so that a run cannot overspend regardless of what the executor intends.
8. As the operator, I want a capture's status shown as cited, examined, or unexamined, so
   that I can distinguish "read and found nothing" from "nobody has looked yet."
9. As the operator, I want the case view to foreground cited sources while keeping the full
   capture set available, less prominently, so that the case reads cleanly without losing the
   corpus denominator.

### Claims

10. As the research executor, I want `propose_claim` to verify, in order, that the capture
    exists and belongs to the run's case, the locator resolves, the quoted text appears
    byte-exact at that locator, all six dimensions are present and valid, and qualification
    is non-empty when posture is `allegation` or `participant_account` — and to fail closed
    on the first failing step — so that no fabricated claim can enter the Record.
11. As the operator, I want claims to enter the Record unconfirmed, carrying the executor's
    proposed evidence dimensions, so that the Record fills freely with research substrate
    without gating on my time.
12. As the operator, I want a claim to support multiple locator/quote pairs, so that
    propositions resting on more than one passage can be expressed.
13. As the operator, I want inference claims (posture `desk_inference`) to cite other claims
    rather than captures, so that reasoning over already-quote-bound claims is expressible
    without requiring a fabricated quotation.
14. As the operator, I want unconfirmed claims to be visually loud everywhere they appear, so
    that I never mistake model-proposed material for something I have reviewed.
15. As the operator, I want claim confirmation to happen only when an angle pulls a claim in
    for use, so that my review effort concentrates on the ten or fifteen claims a rendition
    actually needs rather than every claim in the case.
16. As the operator, I want a rendition unit to be able to cite only confirmed claims, so
    that nothing unconfirmed can reach published text.
17. As the operator, I want confirmation timestamps recorded and the confirmation rate
    surfaced, so that I can tell forty claims confirmed in eleven minutes apart from forty
    claims actually read.
18. As the operator, I want every claim to record which rubric version produced it, so that
    I can answer "which claims came from the bad rubric" after a rubric amendment.

### Runs

19. As the operator, I want to dispatch a run with an explicit question and bounded scope, so
    that research stays answerable rather than a vague topic summary.
20. As the research executor, I want `claim_next_run()` to hand me the oldest approved run
    for a case I can work, along with its question, scope, and rubric version and text, so
    that I can start work without the backend needing to know who or what I am.
21. As the operator, I want runs serialized per case — one claimable run per case at a time —
    so that I never end up with two concurrent chat sessions working the same case.
22. As the operator, I want a claimed run's lease to expire and revert to `approved` if
    nothing touches it, so that an abandoned chat session doesn't permanently strand a run.
23. As the operator, I want captures and proposed claims made before a run is abandoned to
    persist and be picked up by the next executor that claims it, so that real captured
    material is never discarded because a session ended.
24. As the research executor, I want to call `suspend_run` with a stated question, what I'm
    uncertain between, and what I'd do by default, when I hit an ambiguity mid-flight, so
    that the run doesn't burn further work on a wrong assumption.
25. As the operator, I want a suspended run to surface as a state requiring my answer before
    the executor resumes, so that I can resolve genuine uncertainty rather than let the
    executor guess.
26. As the operator, when I close a run, I want to see the proposed agenda of new open
    questions first, then counts of what the run did, then the executor's self-reported
    low-confidence areas, then claims and captures behind a fold, so that the screen matches
    the one decision run close actually requires.
27. As the operator, I want run close to not make claim review feel one click away, so that
    I don't confirm claims without an angle in mind.
28. As the operator, I want every claim and open question to record which run introduced it
    and which question prompted that run, so that lineage is reconstructable later.

### Open questions

29. As the operator, I want a closed run's proposed open questions presented for me to
    approve, reject, edit the scope of, or replace with my own, so that the research agenda
    stays mine to set even though the executor proposes it.
30. As the operator, I want open questions to carry a disposition distinguishing
    unresolved-and-likely-permanent, unresolved-and-awaiting-external-development, and
    not-yet-worked, so that a permanently unanswered question isn't mistaken for an
    unfinished to-do.

### Leads

31. As the operator, I want a URL dropped into the lead inbox to be captured immediately,
    always, so that material likely to disappear (a deleted post, a pulled video) is
    preserved before I decide whether it matters.
32. As the operator, I want a lead to hold captured material only, never claims, until it's
    attached to a case, so that extraction happens with a real question in mind rather than
    in a vacuum.
33. As the operator, I want an optional, skippable summary generated for a lead, so that the
    inbox stays browsable without forcing a model call on every drop.
34. As the operator, I want an auth-walled or paywalled URL dropped as a lead to be recorded
    as identity-only and explicitly marked not captured, so that a login wall is never
    mistaken for a stored artifact.
35. As the operator, I want to attach a lead to an existing case, promote it to a new case,
    or dispose of it, so that leads have a clear resolution path.

### Coverage

36. As the operator, I want a coverage gauge reporting which of the six research stages
    (official foundation, public question, deep context, story intelligence, editorial
    development, composition) a case has genuinely worked, so that I can judge readiness
    without a rigid stage gate.
37. As the operator, I want angle work blocked until the official foundation stage reads
    complete, so that the counter-case always gets real effort before the story gets shaped.

### Angle Room

38. As the operator, I want to develop an angle inside a case, linking it to specific
    confirmed claims, so that the angle inherits each claim's source basis, corroboration,
    certainty, posture, and required qualification rather than laundering a weaker claim
    into a stronger-sounding story.
39. As the operator, I want the public question — what people are actually asking, where,
    and what version of the belief circulates — recorded as a first-class Angle Room object
    distinct from a claim about the world, so that discourse observations aren't forced into
    claim shape.
40. As the operator, I want to choose or dismiss a candidate angle myself, with dismissed
    angles kept as immutable reasoned dismissals, so that the editorial judgment of what
    story to tell stays mine and past reasoning isn't lost.

### Renditions and composition

41. As the operator, I want each rendition generated independently from the angle plus its
    confirmed claims, native to its platform, rather than cut down from a longer piece, so
    that qualification language survives instead of being shed by compression.
42. As the operator, I want a rendition composed of ordered units, each unit citing only
    confirmed claims, so that approval can bind at the unit level for platforms like a
    thread.
43. As the operator, I want to approve the exact reviewed content of a rendition — text,
    links, media, labels — with any post-approval change invalidating that approval, so that
    what gets published is guaranteed to be what I cleared.
44. As the operator, I want media binding to cover SHA-256, byte size, MIME type, reference,
    alt text, and rights state, with replaced bytes invalidating approval, so that swapped
    media can't slip past a prior approval.
45. As the operator, I want to record a published unit's ordinal, platform, owned account,
    external post identity, canonical URL, published time, and verification state, so that
    what actually went out is captured accurately.
46. As the operator, I want changing a scheduled or recorded publication time to never alter
    the approved text, so that timing and content approval stay independent.

### Authority boundaries

47. As the operator, I want dispatching a run, setting authoritative evidence dimensions,
    resolving entity identity, confirming a conflict as editorially live, choosing an angle,
    classifying publication risk, and approving exact content to all require my explicit
    action, so that no automated process can exercise editorial or evidentiary judgment on
    my behalf.
48. As the operator, I want no LLM or executor to have direct database access, so that every
    write happens through a governed operation whose refusals are enforceable.
49. As the operator, I want retrieved page content to always be treated as quoted material,
    never as instruction, so that text inside a captured page cannot manipulate the
    executor.

### The first case

50. As the operator, I want to run the Vela Incident case — the same nine sources the
    previous system failed on — end to end through capture, claims, one angle, and one X
    thread, so that I have a controlled comparison proving the new architecture where the
    old one produced five retired drafts.

## Implementation Decisions

- **Two top-level owned entities.** Case (durable, never completes, goes dormant and wakes)
  and Rendition (belongs to exactly one case, carries a publication lifecycle, ends published
  or rejected). Angle is Angle Room content living inside a case, linking to claims, with no
  lifecycle of its own.
- **Capture-then-cite.** Reading external material is always a backend fetch (`capture_url`),
  which stores raw bytes, hashes them, and parses them into an element structure before any
  claim can bind to a locator inside it. Everything read is captured, regardless of whether
  it is later cited.
- **Authority at use, not at storage.** Claims enter the Record unconfirmed, carrying the
  executor's proposed evidence dimensions. No entry gate. Confirmation happens only when an
  angle pulls a claim into rendition use; confirmation sets authoritative dimensions and
  persists with the claim across cases. A rendition unit may only cite confirmed claims.
- **Question-scoped research runs.** Research is a loop, not a pipeline: run → findings + new
  open questions → executor proposes which questions are worth pursuing and why → operator
  approves, rejects, edits, or writes his own → approved questions become the next run. The
  six research stages (official foundation, public question, deep context, story
  intelligence, editorial development, composition) are a coverage gauge, not a sequential
  pipeline — a case can be on run seven and still filling official foundation. One hard gate:
  no angle work begins before official-foundation coverage reads complete.
- **Active/dormant cases.** A case goes dormant (no active runs, out of the working queue,
  fully intact and searchable) and wakes on a new dispatched run. New material against a
  dormant case either answers an open question, contradicts a confirmed already-published
  claim (triggering correction lineage — preserve the prior public record, never silently
  rewrite), or relates without answering or contradicting (stored; the human notices). Open
  question dispositions: unresolved-likely-permanent, unresolved-awaiting-external-
  development, not-yet-worked — only the last is a to-do.
- **Parallel rendition generation.** Renditions are generated independently and in parallel
  from an angle's confirmed claims, natively per platform, never derived by cutting down a
  longer piece. Divergent emphasis across renditions of the same angle is acceptable;
  contradiction on facts is not, since they share one claim set.
- **Backend owns runs; the executor is a swappable tool-surface client.** The backend owns
  every run (question, scope, rubric version, capture budget) and all recording; the
  executor is an LLM client that claims a run and works it through an MCP-exposed tool
  surface, holding no run state and creating no artifacts directly. Every artifact being
  backend-created is what keeps a provider swap a configuration change rather than a
  rebuild.
- **Per-operation versioned rubrics.** Standing question sets attach to operations — reading
  a source, extracting a claim, working the public question, proposing an angle, closing a
  run — not to research stages, since the same operation carries the same discipline on run
  one and run twelve. Each rubric set is a versioned repository artifact; every claim records
  the rubric version that produced it; a rubric change is never retroactive — correcting a
  class of error means amending the rubric and re-running, producing superseding claims with
  lineage.
  - Companion: runs can suspend and ask. States: `running` / `suspended-awaiting-human` /
    `complete`. Answering a suspended question resolves the instance; amending a rubric
    resolves the class — the interface must keep these visibly distinct.
  - Companion: drift visibility via aggregate views over already-recorded data —
    classification distributions per rubric version, operator correction rate,
    cross-version comparison, confirmation rate.
- **Lead inbox holds material, never claims.** A lead is a URL dropped unattached to any
  case. It is captured immediately on drop, always — no toggle, no conditional fetch. It
  holds material only, never claims, until attached to a case, since claims need a run's
  question, rubric, and lineage to mean anything. An optional summary (description, not
  extraction) is the only part of lead-drop that costs money and is deferrable/skippable.
  Auth-walled/paywalled URLs are recorded as identity-only leads, explicitly marked not
  captured.
- **Promotion by use.** A capture becomes cited the moment a claim binds to it — no separate
  operator action, no relevance score. Captures with no claims are examined (a run looked,
  found nothing) or unexamined (nobody has looked); runs record what they examined at close
  time.
- **Run registry mechanics.** Runs sit at status `approved` and are claimed via
  `claim_next_run()`, which hands the oldest approved run to whichever executor calls it —
  the backend never pushes to a named executor. Run states: `draft`, `approved`, `claimed`,
  `suspended`, `complete`, `abandoned`, `cancelled`. A claim carries a lease refreshed by the
  executor's tool calls; an unrefreshed lease reverts the run to `approved`. Partial work
  (captures, proposed claims already made) is preserved across abandonment, not rolled back —
  a run may be worked by more than one executor across its life. Concurrency is serialized by
  default: one claimable run per case at a time.
- **Run close screen order.** (1) the proposed agenda of new open questions, with rationale
  and proposed scope, for the operator to approve/reject/edit/replace — the only decision run
  close actually requires; (2) counts of what the run did (captures made, claims proposed);
  (3) the executor's self-reported low-confidence areas and where the rubric underserved it;
  (4) full claims and captures, behind a fold. Claim review must not be one click away from
  run close, so confirmation doesn't happen without an angle in mind.
- **`propose_claim` contract.** Inputs: `run_id`, `proposition`, `capture_id`, `locator`,
  `quoted_text`, `dimensions` (the six, as proposals), `qualification`. Verification runs in
  order and fails closed at the first failing step: `capture_id` exists and belongs to the
  run's case; `locator` resolves inside that capture's element structure; `quoted_text`
  appears byte-exact at that locator; `dimensions` are all present and valid enum values;
  `qualification` is non-empty when posture is `allegation` or `participant_account`. A claim
  may carry multiple locator/quote pairs. `desk_inference` claims cite other claims, not
  captures.
- **`capture_url` contract.** Response: capture ID, parsed elements with locators, and each
  element's text, up to a size cap — the executor quotes from this response, never from its
  own independent reading of the page, so quotes match the stored bytes by construction. A
  separate `read_capture(capture_id, range)` tool goes deeper into an already-made capture;
  kept separate from `capture_url` (rather than automatic pagination) so `capture_url` stays
  cheap and "read further" is a visible, recorded act.
- **The complete tool surface.** Eight MCP-exposed calls, the only path into the Vault or the
  Record: `claim_next_run()`, `read_case_context(case_id)`, `capture_url(url)`,
  `read_capture(capture_id, range)`, `propose_claim(...)`, `suspend_run(run_id, question,
  ...)`, `close_run(run_id, questions, ...)`, `add_lead(url, note)`. Budget enforcement lives
  at `capture_url`, which counts against the run's cap and refuses once exhausted.
- **Evidence model.** Six independent dimensions per claim — source basis, corroboration,
  certainty, posture, required qualification, publication risk (publication risk is a
  separate control, not evidence strength). Never compressed into a single score, sum, or
  ladder. The UI may render dimensions as chips but must always surface a contradictory
  combination for correction, never hide it.
- **Publication-risk classes.** `unknown`, `living_private`, `public_official_official_capacity`,
  `public_figure`, `deceased`, `institution`, `not_applicable`. Person entities default to
  `unknown`; moving off it requires a human actor, basis, and timestamp. `unknown` and
  `living_private` people are non-publishable as cross-case connections; public status alone
  is insufficient. No LLM, detector, query, or relationship path may set publishability.
- **Data roles.** The database is the source of truth for identity, workflow, claims,
  entities, approvals, and audit. A governed filesystem holds immutable captured originals
  and normalized element packages. Generated projections (Markdown/HTML) are read-only and
  never authoritative.
- **Multi-account scope.** `account_id` is carried in the schema from the start; the
  interface stays single-account for this destination.
- **Scope of this destination.** One case (the 1979 Vela Incident, using the nine sources
  already identified from the prior build), one platform (X), one format (thread),
  researched, captured, claimed, developed into one angle, rendered as one X thread, cleared
  by the operator, and posted manually. Truth Social, Substack/Medium, video scripts, Release
  Watch, metrics, No Coincidences, and multi-account UI are extension work, not part of this
  destination.

## Testing Decisions

- **What makes a good test here:** assert on the external behavior of a governed operation —
  its inputs and its recorded or returned outputs — never on internal representation. In
  particular, `propose_claim`'s five-step fail-closed verification should be tested by
  asserting acceptance/rejection outcomes for each step's failure case, not by asserting how
  the check is implemented internally.
- **Seam:** the primary seam is the backend's governed operations layer — the domain/service
  functions underlying both the MCP tool surface and the human-facing operations — invoked
  directly, in-process, in tests. This covers `claim_next_run`, `capture_url`,
  `read_capture`, `propose_claim`, `suspend_run`, `close_run`, `add_lead`,
  `read_case_context`, and the human-facing operations (confirm claim, resolve open question,
  choose/dismiss angle, approve rendition unit, record publication, attach/promote/dispose
  lead). One thin end-to-end test exercises the real MCP transport — a tool call dispatched
  over the actual protocol reaches the backend and returns the expected shape — to catch
  wiring regressions; it is not where behavioral coverage lives.
- **Modules to test:**
  - The run registry state machine — claim, lease refresh, lease expiry/reversion,
    abandonment with partial-work preservation, per-case serialization (D12).
  - The `propose_claim` verification chain, each of its five ordered checks (D14).
  - `capture_url` / `read_capture` — locator map correctness and run-budget enforcement
    (D3, D15).
  - Claim confirmation — the "unconfirmed invisible to composer" rule and confirmation
    timestamp/rate recording (D4).
  - Lead capture-on-drop and the material-only-until-attached rule, including the
    auth-walled/paywalled identity-only path (D10).
  - The coverage gauge and the official-foundation gate blocking angle work (D5).
  - Rendition approval — exact-content binding and invalidation on any post-approval change
    to text or media (§14 of the vision).
- **Prior art:** none yet in this repo — this is the first spec since `/setup-matt-pocock-skills`
  ran. There is no existing test suite to follow; the seam choice above is the precedent this
  codebase should follow going forward.

## Out of Scope

- Truth Social, Substack/Medium, and any other rendition platform or format beyond one X
  thread.
- Video scripts (rendition type reserved in shape only, per the locator model's need to
  address a time range — not built).
- Release Watch.
- Metrics and performance analysis.
- No Coincidences / any automatic cross-case pattern detection, recurrence flagging, or hub
  detection. The system stores; the human notices.
- Multi-account UI. `account_id` exists in the schema; only single-account interface is
  built.
- The dismissal ledger (public record of investigated-and-found-nothing claims) — reserved
  shape, not part of this destination.
- A second-model auditor.
- Semantic retrieval, Qdrant, or graph-based retrieval structures.
- A desktop shell or packaged client — web, localhost, Linux-first only. The backend/client
  boundary stays strict enough that a desktop wrapper remains possible later, without being
  built now.
- Executor model selection — a standing, recurring research question, not decided by this
  spec.
- Exact rubric question text — the mechanism (versioned artifacts, per-operation attachment,
  claim-level version recording) is specified here; the actual questions are drafted after
  the first run, tuned against real output.
- The precise signals that make the coverage gauge read "complete" for a stage — left to be
  tuned against the first case.
- Web UX / interaction design (e.g., tiled vs. form-based case view) — undecided, a
  candidate for `/prototype`, not specified by this spec.
- Entity-resolution ergonomics and cross-case connection workflows beyond what the single
  Vela case requires.

## Further Notes

- This spec is written once, for the destination, per `discrepancy-desk-docs/reference/skills-adoption-plan.md`
  — it is not meant to be re-run per feature. `/to-tickets` should break it into tracer-bullet
  tickets next, each cutting thinly through every layer rather than completing one layer
  fully.
- `docs/adr/0001`–`0009` are already the binding form of D3, D4, D5, D7, D8, D9, D10, D12, and
  D14 respectively. Where this spec and an ADR could be read as disagreeing, the ADR
  controls.
- The companion repository `discrepancy-desk-docs` holds `VISION.md` and the full decision
  records (`decisions/architecture-decisions.md`, D1–D11; `decisions/run-registry-and-tool-surface.md`,
  D12–D15) this spec derives from — referenced here, not duplicated.
- The Vela Incident case gives a controlled comparison: same topic, same nine sources,
  different system, against a prior build that produced five retired drafts and nine sources
  with zero source notes. If this produces something publishable, the architecture is doing
  its job.
- Executor model selection, rubric text, coverage-signal specifics, and web UX shape are
  intentionally left as fog to be resolved while working the first run, not guessed at here.
