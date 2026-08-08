# 14 — Publication recording

**What to build:** After the operator manually posts a cleared rendition, the system records
what actually went out: each unit's ordinal, platform, external post identity, canonical URL,
published time, and verification state. Changing a recorded or scheduled publication time
never alters the cleared text.

**Blocked by:** 13 — Rendition approval

**Status:** ready-for-agent (amended before start)

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

- [ ] The operator can record, per unit: ordinal, platform, external post identity, canonical
      URL, published time, and verification state.
- [ ] **Recording publication requires the clearance to stand.** Not that a clearance exists
      — that the derived comparison between current content and the clearance snapshot shows
      no divergence. Ticket 13 makes standing derived precisely so this gate cannot be
      satisfied by a stale `status` column or a `current_approval_id` pointer.
- [ ] Editing the recorded or scheduled publication time does not alter the cleared text.
- [ ] The rendition's lifecycle reflects `published`, or `rejected` if the operator rejects
      it instead, as its end state.
- [ ] Human-only and API-only. Nothing on the MCP surface — check `wiring.py`.
- [ ] The governed operations are tested at the agreed seam, including recording refused
      against an invalidated clearance, and a cross-operation pair in
      `test_operation_interactions.py`.

## Recorded, not built — what the operator adds at publication time

Renditions carry no media (deferred at ticket 13). The publishable surface is the ordered
unit text, and links embedded in that text are bound by the text snapshot.

If the operator manually attaches an image when posting, **that is not the artifact ticket 13
cleared**, and the publication record must not imply it was. Nothing here builds media
handling; this is a note so the gap is visible rather than assumed away. When media becomes a
rendition concept it enters the clearance snapshot before a rendition can be cleared, per
VISION §14.

## Open question to settle before implementation

**F-62 — does the clearance snapshot bind claim citations, or only text?**

As built in ticket 13 the snapshot is ordered unit bodies. Changing a unit's `claim_ids`
without touching its text leaves the clearance standing, so a unit cleared citing one claim
can publish citing another. `_prepare_units` still enforces that the new citation is
confirmed and on the angle, so the exposure is narrow — the operator cleared one provenance
and published a different one.

This is the ticket where it bites, because publication is the moment the record becomes a
claim about what was published on what basis. Decide before implementing: bind claim ids into
the snapshot (cheap — the units table already holds them), or state explicitly that clearance
binds appearance only and record why.
