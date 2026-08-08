# 13 — Rendition approval

**What to build:** The operator reviews a rendition and clears **exact content**. What is
cleared is the text as it will appear — not an intention to publish something like it. Any
later change to that content means the approval no longer stands.

**Blocked by:** 12 — Rendition composition

**Status:** accepted

---

## The constraint that shapes everything else

VISION §14: the human clears the text as it will appear, and may edit before approving — at
which point the edited text is what gets bound.

So approval is **not a status flag on a draft**. A boolean and a timestamp satisfy a careless
reading and break the first time someone edits after clearing: the flag still says approved
and the text underneath has moved. The projection lies.

- [x] Approval is an **append-only record** carrying the actor, the timestamp, and the
      **content as cleared**. Re-approval after an edit is a new record, never an overwrite.
      Same shape as `claim_confirmations` and run suspensions — fifth application of
      history-is-never-the-projection.
- [x] The rendition may carry status and a pointer to the current approval for list views and
      the publish gate. The **authoritative cleared content is the approval record**, not the
      draft.

## Invalidation must be derived, not flagged

- [x] Whether an approval still stands is determined by **comparing current content against
      the snapshot**, not by a boolean somebody has to remember to clear.

      This is D20's lesson. Coverage staleness works because it is derived from state rather
      than declared: nothing has to remember to un-complete an attestation. An
      `is_valid` column on an approval is the same trap the coverage gauge avoided — it
      will be correct until the one path that forgets to update it, and that path will be
      found in production.
- [x] An invalidated approval is **visible as invalidated**, stating what changed. The
      operator re-clears; nothing silently reverts to draft, and nothing silently stays
      approved.

## The snapshot must cover order, not only bodies

- [x] The snapshot binds the **ordered sequence of units**, not each unit independently.

      Reordering units changes the thread without editing a single unit's text. A per-unit
      snapshot would report every unit unchanged and the approval intact, while the artifact
      that would actually be published is different. Adding or removing a unit is the same
      failure.

## Criteria

- [x] The operator can review a rendition's units and clear the exact reviewed content.
- [x] The operator may edit unit text before clearing; the edited text is what gets bound.
- [x] Approval binds the text and the unit order as reviewed.
- [x] Any later change to text, order, or membership means the approval no longer stands,
      derived by comparison rather than by a flag.
- [x] Approval is human-only and API-only — nothing on the MCP surface. Check `wiring.py`.
- [x] `composition` coverage already reads object-backed from ticket 12; confirm approval does
      not need to move it, or move it deliberately and say why.
- [x] The governed operations are tested at the agreed seam, including edit-after-approval,
      reorder-after-approval, and re-approval producing a second record rather than mutating
      the first. Add a cross-operation pair to `test_operation_interactions.py`.
- [x] **Clearance revalidates at the moment of clearance** (not only on the last write to the
      rendition). Cited claims must still be confirmed and on the angle; every current
      required qualification must appear in the citing unit body. Fail closed; name claim and
      qualification. Seam test: re-confirm with stricter qualification between composition
      and clearance → approve refuses.

## Narrowed before start — media

The original draft required approval to bind media by SHA-256, byte size, MIME type,
reference, alt text, and rights state, with replaced bytes invalidating the approval.

**Renditions have no media.** Ticket 12 built units with a body and claim ids, and nothing
else. That criterion is unbuildable as written, and building media *and* approval in one
ticket would put an unreviewed new concept inside the ticket that binds publishable content.

Media binding is deferred to its own ticket, before Vela if renditions are to carry images.
The requirement is recorded here so it is not lost: when media exists, the approval snapshot
must cover the same fields, and replacing bytes must invalidate the approval by the same
derived comparison as text.

Narrowed rather than waived, and recorded before acceptance rather than after — the ticket 09
lesson.

---

## Comments

### Implementer report (ticket 13)

**Suite:** 222 passing. Not committed — waiting on both review axes.

#### What was built

- Migration `0016_rendition_approvals`: `rendition_approvals` + `rendition_approval_units`
  (ordered body snapshot); `renditions.current_approval_id` projection pointer (no FK —
  circular with approvals → renditions).
- `approve_rendition` (API_ONLY): appends clearance with actor/timestamp/ordered bodies;
  sets status `cleared` and pointer. Never overwrites history.
- `update_rendition` (API_ONLY): complete unit list replace (no partial update); re-validates
  claim eligibility. Does **not** clear the pointer or flip status back to draft.
- Standing is **derived** on every load: ordered current bodies vs latest snapshot.
  Invalidation carries `changes` tags (`text` / `order` / `membership`) and a human
  `detail` string. Pure helper `describe_content_divergence` unit-tested.
- Projection on `RenditionRecord`: `approval_stands`, `approval_invalidation`,
  `current_approval`, full `approvals` history.
- Client: edit textareas, save units, clear (auto-saves dirty editor first so bound text
  is what the operator sees), standing label, clearance history.
- MCP: neither op in `mcp_tool_names()`; tests assert that.
- `composition` coverage: left object-backed on draft-with-cites (ticket 12). Approval does
  not move it — composing is the measuring object; clearance is a later editorial gate.
  Test asserts reading unchanged across approve.

#### Tests

- Seam: approve, edit-invalidates, reorder-invalidates, membership-invalidates,
  re-approve appends second record (first immutable), edit-before-clear, not-found,
  composition coverage stable, not on MCP.
- Interaction: approve → edit → `get_case` reports standing false + invalidation.
- Transport registration + client path extraction pick up new routes.

#### Deliberate non-builds

- Media binding (deferred per ticket — recorded, not waived).
- Unit reorder UI (backend + invalidation tested; client only edits text in place —
  reorder would need up/down controls; not required for the seam).
- Refuse mutation while cleared (chose edit-allowed + derived invalidation, as ticket).
- Publish / reject (ticket 14).
- Claim-id changes without body change do not invalidate (snapshot is ordered **bodies** —
  what appears; citations are desk metadata). Flagged below.

#### Unease / notice

- **Citation-only drift.** Changing `claim_ids` without changing bodies leaves approval
  standing. Correct for “text as it will appear”; wrong if publish gate must also freeze
  the citation set. Ticket said text and order. If 14 needs claim freeze, extend the
  snapshot then.
- **Full unit replace regenerates unit_ids.** Snapshot stores ordinal+body only, so that is
  fine. Comparison is sequence of body strings.
- **Status stays `cleared` after invalidation.** Deliberate: nothing silently reverts to
  draft; standing is the truth for the publish gate. UI shows invalidated detail. A reader
  who only looks at `status` still lies — same class as coverage if you ignore derived
  readings. Documented in CONTEXT.
- **No populated-migration test for 0016.** Additive tables + nullable column; no rebuild.
  Did not add a populated upgrade test.
- **Client reorder** not built — reorder invalidation is service-tested only.
- Pre-existing pyright noise in `close.py` untouched.

#### Criteria self-check

| Criterion | Delivered? |
|---|---|
| Append-only snapshot with actor/time/content | Yes |
| Pointer + status projection; authority in approval | Yes |
| Derived invalidation (no is_valid) | Yes |
| Visible invalidation with what changed | Yes |
| Order in snapshot | Yes |
| Edit before clear binds edited text | Yes (update then approve; UI auto-saves) |
| API-only, not MCP | Yes |
| composition not moved | Yes (deliberate; test) |
| Seam + interaction tests | Yes |
| Media | Deferred as ticket |

#### Round 2 — clearance revalidates at assertion time

Blocking fix: `approve_rendition` now calls `_prepare_units` against current unit
bodies and claim_ids before writing a snapshot. Re-confirmation of a cited claim
with a new required qualification (ticket 11) no longer leaves a clearable draft
that fails VISION §14. Refusal is `QUALIFICATION_MISSING_FROM_UNIT` naming claim
and qualification text. Seam test
`test_clearance_revalidates_after_stricter_qualification` covers the path where
`update_rendition` never runs. F-62 (citation-id drift) left as ordered-bodies
snapshot per review; ticket 14 revalidates at publish.

