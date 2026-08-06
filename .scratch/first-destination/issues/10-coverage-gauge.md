# 10 — Coverage gauge and official-foundation gate

**What to build:** A case shows a coverage gauge reporting which of the six research stages
(official foundation, public question, deep context, story intelligence, editorial
development, composition) it has genuinely worked, based on real activity attributed to the
dimension it evidences. Angle work is hard-blocked until official-foundation coverage reads
complete.

**Blocked by:** 04 — Capture (Vault), 05 — Claim proposal, 08 — Run close: agenda and open
questions

**Status:** implemented — awaiting review (not committed); revised scope (D20)

**Revised at review.** The first implementation derived `official_foundation` from case-wide
activity (≥1 capture, ≥1 claim, 0 unexamined). Both review axes found independently that
nothing bound that activity to the dimension it claimed to evidence — a run working the
public question satisfied the official-foundation gate. D20
(`../discrepancy-desk-docs/decisions/coverage-measurement.md`) settles the measurement
question and closes the corresponding architecture fog item. Criteria below supersede the
original four.

- [x] A run carries a **coverage dimension set by the operator at dispatch** — one run, one
      dimension. Not settable by the executor, and not touched by anything reported at
      `close_run`.
- [x] The case view shows a reading for each of the six stages, derived from completed runs
      targeting that dimension and the captures and claims beneath them.
- [x] `unworked` means no completed run targets the dimension. `worked` means at least one
      has, producing claims. **`unmeasurable` is used wherever no first-class object exists
      that could record the stage** — "no record could show this" is not "this was not
      worked."
- [x] `complete` is set only by an **operator attestation**, recorded with actor and
      timestamp. No count produces it.
- [x] An attestation is superseded when unexamined captures arrive on the case afterwards:
      the reading returns to `worked`, states why, and the operator may re-attest. A stale
      `complete` is never held silently.
- [x] The gauge is explicitly not a state machine — stages can be worked out of order and
      revisited.
- [x] Any attempt to start angle work (ticket 11) on a case whose official-foundation stage
      does not read complete is refused, evaluated against the derived-plus-attested gauge.
- [x] Stage ids and readings are a **validated** vocabulary — constrained in the models, not
      listed in a comment beside a bare `str`.
- [x] The governed operations are tested at the agreed seam, including the refusal case for
      the official-foundation gate, an attestation going stale, and a completed run on one
      dimension leaving the other five unchanged.

**Kept from the first implementation:** coverage is derived, never declared; one derivation
shared by the gauge and the gate; no stage field the executor can write; the gate as a
service function with no transport surface; and `unmeasurable` as a first-class reading
rather than a proxy.
