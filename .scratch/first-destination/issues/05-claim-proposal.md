# 05 — Claim proposal

**What to build:** A claimed run's executor calls `propose_claim` to record a proposition
bound to captured, byte-verified material. The five-step verification runs in order and
fails closed on the first failing step. Claims enter the Record unconfirmed and are visually
loud wherever they appear.

**Blocked by:** 04 — Capture (Vault)

**Status:** ready-for-agent

- [ ] `propose_claim(run_id, proposition, capture_id, locator, quoted_text, dimensions,
      qualification)` is exposed on the tool surface.
- [ ] Verification runs in order and fails closed: `capture_id` exists and belongs to the
      run's case → `locator` resolves → `quoted_text` appears byte-exact at that locator →
      all six dimensions are present and valid enum values → `qualification` is non-empty
      when posture is `allegation` or `participant_account`.
- [ ] A claim can carry multiple locator/quote pairs.
- [ ] A `desk_inference` claim cites other claims, not a capture/locator/quote.
- [ ] Accepted claims are recorded unconfirmed, carrying the run's rubric version and the
      proposing run's lineage.
- [ ] The browser client renders unconfirmed claims with a visually loud, unmistakable
      marker.
- [ ] The governed operation is tested at the agreed seam, with a rejection case for each of
      the five verification steps.
