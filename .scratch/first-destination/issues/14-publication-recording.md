# 14 — Publication recording

**What to build:** After the operator manually posts a cleared rendition, the system records
what actually went out: each unit's ordinal, platform, external post identity, canonical URL,
published time, and verification state. Changing a recorded or scheduled publication time
never alters the cleared text.

**Blocked by:** 13 — Rendition approval

**Status:** accepted

---

## Amended before start

**The account field is removed.** The original draft required recording an "owned account"
per unit. D17 cancelled multi-brand support — cancelled, not deferred — and the reasoning was
that one brand per deployment means no `account_id` column and no account scoping anywhere.
A second brand is a second deployment.

Recording an account here would reintroduce the model D17 removed, one column at a time, in
the ticket furthest from where anyone would look for it. Platform stays; account goes.

**Narrowed rather than waived**, and recorded before acceptance rather than after.

## Criteria

- [x] The operator can record, per unit: ordinal, platform, external post identity, canonical
      URL, published time, and verification state.
- [x] **Recording publication requires the clearance to stand.** Not that a clearance exists
      — that the derived comparison between current content and the clearance snapshot shows
      no divergence. Ticket 13 makes standing derived precisely so this gate cannot be
      satisfied by a stale `status` column or a `current_approval_id` pointer.
- [x] **Recording publication also revalidates current claim state**, using the same
      mechanical gate clearance uses: every cited claim still confirmed, still on the angle,
      and its current required qualification present in that unit's body.

      This is S-01 one hop later. Clear a unit citing a claim with no required qualification;
      re-confirm that claim as an allegation with required language; the bodies are unchanged
      so standing still holds; publication would otherwise succeed while VISION §14's
      requirement that every required qualification survives is false.
- [x] **One shared helper serves both gates.** If publication reimplements the check, the two
      drift and the drift is silent — the parallel-path failure this project has had six
      times. Extract one function; the publish side carries a comment saying it exists for
      the same reason as the clearance revalidation.
- [x] **The publication record binds the `approval_id` that authorized it.** VISION §14: one
      approval authorizes one publication set. `current_approval_id` on the rendition is a
      projection pointer only, so without a durable link the Record knows a rendition was
      published but not which append-only human clearance authorized it — unanswerable on a
      rendition cleared more than once. Per-unit rows belong to that publication set.
- [x] **Rejection stays asymmetric.** Rejecting a rendition asserts nothing about
      publishability, so it needs no claim revalidation. Requiring it would refuse the
      operator's ability to reject something *because* its basis no longer holds.
- [x] Editing the recorded or scheduled publication time does not alter the cleared text.
- [x] The rendition's lifecycle reflects `published`, or `rejected` if the operator rejects
      it instead, as its end state.
- [x] Human-only and API-only. Nothing on the MCP surface — check `wiring.py`.
- [x] The governed operations are tested at the agreed seam, including:
      - clear → re-confirm a cited claim with stricter qualification → no rendition edit →
        `approval_stands` still true → publication refuses on current qualification;
      - **F-62 lock:** change a unit's citation to another still-eligible confirmed claim
        without changing the body — re-clearance is not required and publication may proceed,
        provided current qualification rules pass;
      - publication refused against an invalidated clearance;
      - a cross-operation pair in `test_operation_interactions.py`.

## F-62 — closed as a disposition, not a build

**Clearance binds appearance, not internal claim ids.** The ordered bodies remain the
clearance snapshot. Do not expand ticket 13's snapshot to carry claim ids.

VISION §14's exact-content list is text, links, media, and labels — publishable content.
Internal claim ids are not part of it, and binding them would widen "exact content" past what
the doctrine says it means.

Citation-only drift is therefore **allowed** when the resulting citations are still valid
under the current Record, and **refused** when they are not — caught by the live revalidation
above rather than by freezing ids. Drift that breaks confirmation, angle membership, or
qualification fails closed at the publish gate.

The two gates end up with different jobs and no contradiction: **clearance freezes what the
human saw; publication verifies that the frozen appearance still stands and that its current
evidentiary basis is still usable.**

## What this gate can and cannot do

Publication recording happens *after* the operator has manually posted. The gate cannot
prevent anything appearing on a platform — it prevents the Desk from recording that
publication as properly cleared.

So a state exists that this ticket does not resolve: **something posted externally that the
Desk refuses to record.** Do not weaken the gate to accommodate it, and do not invent a
bypass here. Later correction-lineage work will need to preserve the fact of an external
publication even when its basis has since changed, and that is where the state belongs.

Recorded so it is found deliberately rather than discovered during the Vela run.

## Recorded, not built — what the operator adds at publication time

Renditions carry no media (deferred at ticket 13). The publishable surface is the ordered
unit text, and links embedded in that text are bound by the text snapshot.

If the operator manually attaches an image when posting, **that is not the artifact ticket 13
cleared**, and the publication record must not imply it was. Nothing here builds media
handling; this is a note so the gap is visible rather than assumed away. When media becomes a
rendition concept it enters the clearance snapshot before a rendition can be cleared, per
VISION §14.

## Open question to settle before implementation

None. F-62 is dispositioned above and the publish gate is specified. Implement as written.

---



## F-64 — one publication set per rendition (stated decision)

``UNIQUE(rendition_id)`` on the publication set is intentional for ticket 14.

It means these ordinary situations require a **new rendition** (and re-clearance of
text nobody necessarily edited), not a second publication row on the same draft:

1. A thread that posts three of four units (partial set).
2. A unit deleted and reposted with a new external id while cleared text is unchanged.

Vela can tell us whether that holds. Do not build a correction-lineage model here.

## Comments

### Implementer report (ticket 14)

**Suite:** 233+ passing (re-verify after client polish). Not committed — waiting on both axes.

#### What was built

- Migration `0017_rendition_publications`: publication set + per-unit rows; **approval_id**
  durable FK (VISION §14 one approval → one publication set). No account_id (D17).
- `assert_units_eligible_for_clearance_or_publication` — shared helper for clearance and
  publication. Publish path comments why it exists (parallel-path drift).
- `record_publication`: requires **derived standing** (not status / not bare pointer) +
  shared eligibility revalidation; writes publication bound to authorizing approval_id;
  sets status `published`.
- `reject_rendition`: asymmetric — **no** claim revalidation.
- `update_publication_times`: edits `published_at` only; asserts clearance bodies unchanged.
- API-only: `record_publication`, `reject_rendition`, `update_publication_times`.
- Client: record publication (placeholder external ids when standing), reject, show
  publication lineage.

#### Tests

- Standing gate refuses invalidated clearance while status still `cleared`.
- S-01 hop: clear → re-confirm stricter qualification → standing true → publication refuses
  with claim + qualification named.
- F-62 lock: citation-only swap to another eligible claim → standing true → publication
  proceeds without re-clear.
- Rejection succeeds after re-confirm that would block publication.
- Time edit does not alter unit or clearance bodies.
- Interaction: publish → get_case shows publication.approval_id.
- Not on MCP; enum CHECK for verification_state.

#### Deliberate non-builds / recorded gaps

- External post that Desk refuses to record — not weakened, no bypass (ticket text).
- Media still deferred.
- Client publish form uses provisional external ids; operator can patch times via API.

#### Unease

- One publication per rendition (UNIQUE rendition_id). Re-publish after correction is a
  new rendition, not a second publication set on the same row — matches end-state
  published. If Vela needs correction lineage on the same thread, later work.
- Shared helper wraps `_prepare_units`; propose/update also call the shared entry so all
  write paths share one name.

#### Round 2 — paste-back form (no fabricated metadata)

Client no longer invents external_post_id / canonical_url. Operator pastes real
platform values; published_at defaults to now but is editable; verification_state
is operator-set. Empty id/URL refused client-side and already service-side.

**Partial sets:** refuse until complete for this publication set (matches
PUBLICATION_UNITS_MISMATCH and F-64). An id not yet captured means wait, not invent.

**published_at before clearance:** now refused (`PUBLICATION_BEFORE_CLEARANCE`) on
record and on time update — cannot claim a post went out before it was cleared.

