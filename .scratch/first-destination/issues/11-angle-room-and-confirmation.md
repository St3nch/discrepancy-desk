# 11 — Angle Room and claim confirmation

**What to build:** Operator develops an angle inside a case by linking specific confirmed
claims to it; linking a not-yet-confirmed claim into an angle is exactly the moment that
claim's evidence dimensions get confirmed (accepted or corrected) by the operator. The
public question is recorded as a distinct first-class object, not a claim. Operator chooses
or dismisses candidate angles; dismissed angles are kept as immutable reasoned dismissals.

**Blocked by:** 05 — Claim proposal, 10 — Coverage gauge and official-foundation gate

**Status:** accepted

- [x] Operator can create an angle inside a case and link claims to it.
- [x] Linking an unconfirmed claim to an angle presents its proposed dimensions for the
      operator to accept or correct, and the claim becomes confirmed at that point — not
      before.
- [x] Confirmation records a timestamp; a confirmation-rate figure is derivable from
      recorded timestamps.
- [x] A rendition-eligible claim set only ever contains confirmed claims (verified
      structurally here, even though rendition itself is ticket 12).
- [x] Operator can record a public question (what's being asked, where, what version
      circulates, where it came from) as an Angle Room object distinct from a claim.
- [x] Operator can choose one angle or dismiss others; dismissed angles persist with their
      reasoning and are never deleted or silently overwritten.
- [x] **Every angle-start and claim-confirmation path calls
      `assert_official_foundation_complete`** (ticket 10 / D20). Ticket 10 proves the refusal
      is real at the seam; only this ticket can prove that an actual attempt to start angle
      work on an incomplete case is refused. Tested per path, not once.
- [x] **F-24 closes here.** Inference claims must inherit publication risk from the claims
      they cite — an inference reasoning over a `living_private` claim cannot be recorded
      `not_applicable`, laundering the risk one level up. Open since ticket 05 and noted in
      the `claims.py` docstring; it must close before confirmation and use paths exist.
- [x] The quotation shelf holds quotations the operator has **selected**, with speaker and
      attribution frame — not an automatic projection of every binding on every linked
      claim. It preserves region locators (`e/{n}/r/{start}-{end}`) when the selection is a
      passage within a block, so a quotation can be the sentence someone actually said
      rather than being stuck at block granularity.

      **Clarified at review:** region form is supported and preserved, not required. A hard
      requirement was considered and rejected — an element whose entire text is the
      quotation is correctly addressed as `e/{n}`, and forcing `e/{n}/r/0-57` would make the
      operator compute an offset conveying nothing. Revisit in ticket 12 if renditions
      consuming the shelf show that block-granularity entries produce bad output; that would
      be evidence rather than form.
- [x] The governed operations are tested at the agreed seam.
