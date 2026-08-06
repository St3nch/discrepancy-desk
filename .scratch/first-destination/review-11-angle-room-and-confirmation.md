# Review — Ticket 11 (Angle Room and claim confirmation)

**Date:** 2026-08-06
**Reviewers:** Claude (seam checks + steward) and GPT (spec), independently
**Verdict:** Accepted on both axes after three rounds.

The heaviest ticket in the project. It closed F-24 — open since ticket 05 and the last
finding outstanding from the first eight tickets — and it took three rounds to do it,
because the same defect wore three different faces and each fix revealed the next.

Produced D21, two amendments to D20, and one acceptance-criterion clarification.

---

## Standing checks (final state)

| Check | Result |
|---|---|
| Vocabulary reconciliation | **Clean.** Angle statuses and the new enums carry CHECK constraints and are covered by the parameterised `test_check_enums.py` table |
| Fail-open inventory | **Clean** after F-48/S-04. The gate is on all seven Angle Room write paths, 1:1, reads correctly ungated |
| Destructive-write inventory | **S-05** — confirmation overwrote the model proposal; closed |
| Dead-capability inventory | **Clean** |
| Write-once inventory | **Clean.** `claim_confirmations` append-only; dismissed angles persist with reasoning |
| Projection completeness | **Clean.** `claims` is the current projection over a durable confirmation log |

Suite verified by the reviewer at each round rather than taken from the report: 165, 169,
173 passed.

---

## F-24, closed after ten tickets

The finding: an inference claim could carry a weaker publication risk than the claims it
reasons over, laundering the risk one level up in the one dimension VISION §13 says must fail
closed.

**It took three rounds because it was three defects, and only the third made it structural.**

**Round one — a ladder with the fail-closed default near the bottom.**
`PUBLICATION_RISK_RANK` ordered the seven values 0–6 and refused any inference ranked below
the maximum of its citations. `unknown` sat second-lowest, so an inference citing an
`unknown` claim could be recorded `institution`, `deceased`, `public_figure`, or
`public_official_official_capacity` — all higher, all accepted. §13 makes `unknown` one of two
*non-publishable* states. The guard treated the fail-closed default as nearly the least
restrictive value.

Both axes found this independently. Both concluded the ladder should be deleted rather than
reordered: publication risk is categorical, and there is no fact of the matter about whether
`institution` outranks `deceased`. D21 records the binary rule §13 actually states.

**Round two — the check bound to the proposed value.** Found on the spec axis by reproducing
it. `confirm_claim_for_use` branched on the proposed `source_basis` while writing
`dimensions.source_basis`, so correcting an ordinary claim *into* `desk_inference` at
confirmation skipped every D21 check. The result was a confirmed inference with zero cited
claims and a capture binding.

The seam reviewer had quoted that exact line in the same round and not followed it through.

**Round three — the structural boundary.** Fixing which field the check reads is not enough
if nothing constrains what the field may become. Crossing the inference / non-inference
boundary at confirmation is now refused in both directions, because the support structure is
built at proposal against captured bytes and confirmation corrects strength, not kind.

The implementer's generalisation is the durable lesson and is recorded in D21: *fixing which
value a check reads does not help unless something also constrains what that value may
become.*

---

## Other findings

### S-01 — Coverage left frozen in its pre-ticket-11 state

**Severity:** High. **Closed.** Ticket 11 built the measuring objects D20 was waiting for and
nothing connected them, so a recorded public question did not move `public_question` coverage
and angles did not move `editorial_development`. The cross-ticket seam class: one ticket
created what another was waiting for.

Closed with object-backed readings requiring a claim link — the load-bearing half, since
otherwise a stage reads worked because somebody typed a title. `story_intelligence` and
`composition` stay `unmeasurable` as a stated decision. D20 amended to record both.

### S-02 — Rendition eligibility was case-wide

**Severity:** High. **Closed.** `list_rendition_eligible_claims` took a `case_id` and returned
every confirmed claim on the case, so two candidate angles shared one pool and choosing
between them changed nothing. The `Case → Angle → Renditions` boundary existed only in the
diagram. Now angle-scoped through `angle_claims`, confirmed-only.

### S-03 — Angle Room objects did not have to rest on claims

**Severity:** High. **Closed.** An angle with no claims could be *chosen*, producing renditions
resting on nothing, and public questions had no claim linkage at all. VISION §7: the Angle
Room may make a story vivid; it may not launder a weak claim. Empty angles remain drafts;
choosing requires at least one linked confirmed claim; public questions gained governed claim
links with confirmation-at-use.

### S-05 — Confirmation destroyed the model's proposal

**Severity:** Medium. **Closed.** Dimensions were overwritten in place, so after a correction
the Record could not say what the executor proposed or what the operator changed. §18 states
that claim records *already carry* original proposal and human correction — the stated reason
the reserved second-model auditor needs no retrofit. `claim_confirmations` now holds prior and
newly confirmed values, actor, and timestamp.

This was the seam reviewer's own destructive-write check firing on the spec axis instead.

### F-49 — Confirmation was one-shot

**Severity:** Medium-high. **Closed.** Raised by the implementer as unease and escalated at
review. A claim confirmed with a wrong dimension had no correction path short of editing the
database — F-26's shape in the authority layer. It also silently discarded corrected
dimensions for an already-confirmed claim (F-42's pattern), and made the correction-rate view
unmeasurable.

Resolved as append-only re-confirmation, with the D21 durability guarantee preserved by a
targeted refusal: re-confirming a claim to non-publishable while a confirmed inference cites
it is refused, naming the blocker. No invalidation machinery.

### S-06 — The quotation shelf

**Severity:** Medium. **Partly upheld, partly declined.**

Upheld: the shelf was an automatic projection of every binding on every linked claim. VISION
lists it among Angle Room items the operator *works* — the strongest quotation, selected. Now
an operator selection carrying speaker and attribution frame.

Declined: the spec axis asked twice that shelf entries require region-form locators. An
element whose entire text is the quotation is correctly `e/{n}`, and forcing `e/{n}/r/0-57`
makes the operator compute an offset conveying nothing. **The acceptance criterion was
ambiguous and was amended to say what was built and why the stricter form was rejected** —
the ticket 09 lesson: criteria are narrowed or clarified before acceptance, never after.
Revisit in ticket 12 if renditions consuming the shelf produce bad output; that would be
evidence rather than form.

### S-07 and S-08 — The decision documents lagged the code

**Severity:** Medium. **Closed.** Both were steward defects, not implementation ones.

D20 still defined coverage purely in terms of runs after object-backed readings shipped. D21
still said *no dependency can change underneath a confirmed inference*, which was true when
written and stopped being true when re-confirmation was ordered in the next round — the
decision file contradicting the code is the precise failure a decision file exists to
prevent. D21 also held nothing about the kind boundary, which had been decided in a prompt
and a report and lived only in conversation.

Both amended before acceptance.

---

## What held

**The gate ratio held at 1:1 while the write surface grew from five paths to seven.** Every
Angle Room write calls `assert_official_foundation_complete`; every read correctly does not.
This is the parallel-path failure that has broken this project six times and it did not
happen once here, across three rounds of new operations.

**Equal-value re-confirmation is a no-op rather than a fabricated correction event**, and
qualification is normalised the same way on both paths, so a whitespace difference cannot
masquerade as a correction and inflate the rate.

**Refusals teach the rule.** `SOURCE_BASIS_KIND_MISMATCH` explains that D14's escape valve is
for inferences only and that correcting strength is allowed while reclassifying kind is not.
An operator learns the boundary instead of being blocked by it.

**Bottom-up confirmation ordering is right in the code**: the unconfirmed-citations check runs
before the inheritance check, so inheritance can only ever evaluate authoritative values.

---

## Process notes

**Three rounds, and the routing held.** Grok reported to both reviewers, each responded
independently, findings merged afterwards. The seam reviewer broke the sequence once earlier
in the project by writing a prompt before the spec pass arrived; corrected and held from
there.

**Each axis found what the other missed, every round.** Round two is the clearest: the spec
reviewer reproduced the source-basis bypass; the seam reviewer had read the same line and
passed over it.

**Two of the six findings were steward defects** — decision documents lagging the code they
bind. Worth recording, because the reviewer holding the decisions is the least likely party
to notice when they go stale.
