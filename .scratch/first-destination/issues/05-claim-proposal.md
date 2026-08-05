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

---

## Notes from ticket 04 (binding for this ticket)

### Quotation surface (F-13) — do not re-derive

ADR 9 says `quoted_text` must appear **byte-exact at the locator**. That means:

- **Compare `quoted_text` to `elements.text`** for the resolved locator in the capture's
  document_version (exact string equality on the stored element text).
- **Do not** compare against a raw byte slice of the Vault object.

Raw Vault bytes remain the archival / SHA-256 integrity anchor. The HTML parser *derives*
element text (whitespace strip, buffer join, `convert_charrefs=True`). Executors quote from
the locator map returned by `capture_url` / `read_capture`, which is that derived text. Step
3 fails closed with `QUOTE_MISMATCH` when the strings differ; `LOCATOR_UNRESOLVED` when the
locator is missing.

Recorded in `codingstandards.md` as well.

### Locator grammar (F-22 — implemented)

| Form | Quotation surface |
|---|---|
| `e/{ordinal}` | Full `elements.text` |
| `e/{ordinal}/r/{start}-{end}` | Character slice of that text (`end` exclusive) |

`quoted_text` must equal that surface exactly.
