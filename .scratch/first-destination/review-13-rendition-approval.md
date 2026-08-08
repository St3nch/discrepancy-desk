# Review — Ticket 13 (rendition approval)

**Date:** 2026-08-07
**Reviewers:** Claude (seam checks + steward) and GPT (spec), independently
**Verdict:** Accepted on both axes after two rounds.

The first ticket where both reviewers were briefed before implementation started. That
changed what the spec axis found: the blocking item was raised as a design concern *before*
any code existed, dismissed by the seam reviewer on incomplete verification, and then found
again in the implementation.

Suite verified by the reviewer each round: 222, then 223 passing.

---

## Standing checks

| Check | Result |
|---|---|
| Vocabulary reconciliation | **Clean.** New statuses carry CHECKs and are in the parameterised enum table |
| Fail-open inventory | **S-01** — the blocking one |
| Destructive-write inventory | **Clean.** Approvals append; `update_rendition` replaces units as a complete model, approval history untouched |
| Dead-capability inventory | **Clean** |
| Write-once inventory | **Clean.** `rendition_approvals` append-only; re-clear appends |
| Projection completeness | **Clean.** Standing, invalidation detail, and clearance history all render |

---

## Amended before start

The original draft required approval to bind media — SHA-256, byte size, MIME type, alt text,
rights state. **Renditions have no media**; ticket 12 built units with a body and claim ids
and nothing else. That criterion was unbuildable, and building media *and* clearance in one
ticket would put an unreviewed new concept inside the ticket that binds publishable content.

Deferred to its own ticket with the requirement recorded. Narrowed before acceptance rather
than after — the ticket 09 lesson.

---

## S-01 — Clearance did not revalidate against current claim state

**Severity:** High. **Closed.** **Raised before implementation, dismissed at first review,
found again in the code.**

`_prepare_units` validates on `propose_rendition` and `update_rendition`. `approve_rendition`
loaded the current units, checked status and non-emptiness, and snapshotted the bodies.

That looks complete, because both write paths to the rendition validate. It is not, because
**the third mutation is not a write to the rendition at all.**

Ticket 11 permits re-confirmation. So: a draft cites confirmed claim A and validates; claim A
is re-confirmed with stricter required qualification; nobody edits the rendition, so
`update_rendition` never runs; `approve_rendition` snapshots unchanged text, sets `cleared`,
and reports the clearance stands — while the text no longer contains the qualification claim A
now requires. The human has cleared content that fails VISION §14.

**The rule is not *validate every write to the object*. It is *validate at the moment the
assertion is made*.** A clearance asserts publishability, so a clearance revalidates. This is
D20's staleness lesson one level up: an attestation goes stale because material changed
underneath it, and a clearance can go stale because a *claim* changed underneath it.

The fix calls `_prepare_units` on current bodies and claim ids before any snapshot write, so
the refusal happens with nothing written. The docstring names the mechanism and the D20
parallel, which matters — without it, the next reader removes the call as redundant with
`update_rendition`.

The regression test composes, re-confirms with new qualification, deliberately skips
`update_rendition`, then asserts the refusal, that status stays `draft`, and that no approval
row exists.

---

## What held

**Append-only clearance with a readable snapshot.** `rendition_approvals` plus
`rendition_approval_units` carrying the ordered bodies; `current_approval_id` on the rendition
is a projection pointer only. Fifth application of history-is-never-the-projection.

**Standing is derived, not flagged.** Computed on every load by comparing ordered current
bodies to the snapshot. No `is_valid` column for a write path to forget.

**Three divergence tags — `text`, `order`, `membership`.** Order and membership are what a
per-unit snapshot misses: reordering changes the published artifact while every unit's text
reads unchanged. All three have seam tests.

**No silent status revert**, with the reasoning in the code: status stays `cleared`, the
derived comparison says it no longer stands, and `approval_invalidation.detail` says what
changed. Nothing silently reverts to draft and nothing silently stays approved.

**`update_rendition` reuses `_prepare_units`**, so the human edit path enforces the same
invariants as composition. Edits are not permissive.

**`RENDITION_UNITS_EMPTY` on clearance** was unprompted — closes the case where every unit is
removed and the artifact is empty.

**Both operations API-only.** Human authority held; nothing on MCP.

---

## F-62 — Citation drift does not invalidate a clearance

**Severity:** Medium. **Not a ticket 13 blocker. Dispositioned to ticket 14.**

The snapshot is ordered bodies, so changing a unit's `claim_ids` without touching its text
leaves the clearance standing. The implementer raised it himself.

The seam reviewer initially wanted claim ids bound into the snapshot. **The spec axis reasoned
it better:** VISION §14's exact-content list is text, links, media, labels — publishable
content, not internal claim ids. Binding ids would widen "exact content" past what the
doctrine says it means.

The stronger remedy is the same one S-01 produced, applied at the second gate: **ticket 14
verifies current claim and qualification eligibility at publication**, because authoritative
values can change after clearance too. Recorded in ticket 14's criteria.

## F-63 — Input models reconstructed to reuse the validator

**Severity:** Trivial. **No action.** `approve_rendition` rebuilds `RenditionUnitInput` from
loaded records to call `_prepare_units`, and discards the prepared tuples. It works and it is
the cheapest way to share the check. One or two refusal texts are written for a caller
supplying units rather than one clearing existing ones — the important one,
`QUALIFICATION_MISSING_FROM_UNIT`, reads correctly either way.

---

## Also amended — ticket 14

**The account field was removed** before ticket 14 starts. Its draft required recording an
"owned account" per unit; D17 cancelled multi-brand support — cancelled, not deferred — on the
grounds that one brand per deployment means no `account_id` anywhere. Recording an account
here would have rebuilt that model one column at a time, in the ticket furthest from where
anyone would look for it. Found by the spec axis while reading the ticket 13 brief.

**Two things recorded rather than built:** the publish gate must check *derived standing*, not
a `status` column or a `current_approval_id` pointer; and an operator attaching an image at
publication time is not the artifact ticket 13 cleared, so the publication record must not
imply it was.

---

## Process notes

**Briefing both axes before implementation changed what the spec axis could do.** It raised
the revalidation requirement as a pre-build amendment rather than as a review finding. Had the
implementer received that amendment before starting, the blocker would not have shipped at
all — the brief and the implementation ran concurrently, which is a timing gap worth closing.

**The seam reviewer dismissed the concern on incomplete verification.** The first pass
declared it "answered better than his remedy would have been" after reading two write paths
and confirming both validate — without reading `_prepare_units` itself, and without checking
whether re-confirmation can alter a claim's qualification. Both links were inferred.

The operator caught this and asked whether the finding had been verified or accepted. It had
not been verified. On checking, the chain held and the finding stood — but a blocking prompt
had already been written on an unwalked chain, one message after the same reviewer had been
too slow to block in ticket 12a.

Both errors have the same root: **reasoning from the shape of a familiar failure instead of
from the code.** The standing rule already says run things rather than only read them; the
omission here was reading a reviewer's summary and treating it as verification, which is the
same error as taking a test count from the implementer.
