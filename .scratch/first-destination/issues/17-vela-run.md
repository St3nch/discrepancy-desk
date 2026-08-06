# 17 — The Vela run

**This is not a build ticket.** It is the first destination (D1): one real topic, researched
by a connected LLM against the open web, captured into the Vault with verified locators,
claims extracted and classified, one angle developed, one X thread rendered, cleared by the
human, posted manually, recorded.

One case, one platform, one format, end to end.

**Blocked by:** 11 — Angle Room, 12 — Rendition composition, 13 — Rendition approval,
14 — Publication recording, 15 — Capture acquisition receipt, 16 — Rubric artifacts

**Status:** not started

---

## Why Vela

The 1979 Vela Incident. A double-flash detection over the South Atlantic, an official finding
disputed by the scientific panel that examined it, decades of unresolved argument.

It is also the only topic the previous build ever ran live, and it failed: five drafts, all
retired as failed editorial artifacts; nine sources carrying zero source notes; the longest
draft stored as a single flat blob with no claim structure beneath it. Nine real sources are
already identified from that pass.

Running Vela gives a controlled comparison on identical material — same topic, same sources,
different system. That comparison is the point, and it is why the run should not be quietly
swapped for an easier topic if it gets hard.

---

## Before the run

- [ ] A rehearsal run on a throwaway case, against two or three simple public pages. Not to
      produce anything — to shake out MCP error handling, locator resolution against live
      HTML, and whether a rejected `propose_claim` produces self-correction or a stalled run.
      Findings from the rehearsal are fixed before Vela starts.
- [ ] `alembic upgrade head` run once against a copy of a real populated database, not only
      the test path.
- [ ] **A dress rehearsal of the browser client by the operator.** Nobody has used it — it
      has been typechecked and read, never clicked through. Open the app, walk the whole
      loop on a throwaway case, and note every place the interface fights you. The operator
      loop is the product; a working backend behind an unusable screen fails D1's test.
- [ ] Executor selected and recorded, with the reason. VISION §17 leaves this deliberately
      open and names the criteria.

## The run

- [ ] A case is opened and runs are dispatched by the operator, question-scoped, each
      carrying a coverage dimension and a rubric version.
- [ ] Official-foundation coverage is worked and attested before any angle work — the gate
      is exercised for real, not in a test.
- [ ] Claims are proposed against captured material with byte-exact quotation, confirmed at
      use, and one angle is developed from confirmed claims.
- [ ] One X thread is composed natively, cleared as exact content, posted **manually**, and
      recorded with its external identity.

## What to record while it happens

This is the part that is impossible to reconstruct afterwards and easy to skip in the
excitement of a working system.

- [ ] Every refusal the executor hit, and whether it self-corrected or stalled. The refusal
      codes were designed for exactly this and have never faced a real model.
- [ ] Where the operator wanted something the interface did not offer.
- [ ] How long confirmation actually took, against the claim count. §12 says forty claims in
      eleven minutes is not forty confirmations — this is the first chance to see the real
      rate.
- [ ] Where the rubrics underserved the executor, as input to their second version.
- [ ] Anything captured that the parser handled badly.

## The test, stated bluntly

- [ ] The owner produces work he would voluntarily publish, publishes it, and comes back
      the next day.

If this produces something publishable where the previous build produced five retirements,
the architecture is doing its job. **If it does not, that is worth learning before anything
is built on top of it** — and the honest response is to say so plainly rather than to
continue building.

Nothing after this ticket is planned. Truth Social, Substack, video scripts, metrics,
Release Watch, and No Coincidences are all extension off a proven spine, and the spine is
not proven until this runs.
