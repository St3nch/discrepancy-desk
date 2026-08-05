# 11 — Angle Room and claim confirmation

**What to build:** Operator develops an angle inside a case by linking specific confirmed
claims to it; linking a not-yet-confirmed claim into an angle is exactly the moment that
claim's evidence dimensions get confirmed (accepted or corrected) by the operator. The
public question is recorded as a distinct first-class object, not a claim. Operator chooses
or dismisses candidate angles; dismissed angles are kept as immutable reasoned dismissals.

**Blocked by:** 05 — Claim proposal, 10 — Coverage gauge and official-foundation gate

**Status:** ready-for-agent

- [ ] Operator can create an angle inside a case and link claims to it.
- [ ] Linking an unconfirmed claim to an angle presents its proposed dimensions for the
      operator to accept or correct, and the claim becomes confirmed at that point — not
      before.
- [ ] Confirmation records a timestamp; a confirmation-rate figure is derivable from
      recorded timestamps.
- [ ] A rendition-eligible claim set only ever contains confirmed claims (verified
      structurally here, even though rendition itself is ticket 12).
- [ ] Operator can record a public question (what's being asked, where, what version
      circulates, where it came from) as an Angle Room object distinct from a claim.
- [ ] Operator can choose one angle or dismiss others; dismissed angles persist with their
      reasoning and are never deleted or silently overwritten.
- [ ] The governed operations are tested at the agreed seam.
