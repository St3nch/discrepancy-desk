# Spec-axis pass — Ticket 12 (rendition composition)

**Date:** 2026-08-06  
**Axis:** Spec (independent of the implementer-notes file; not the steward merge)  
**Suite verified this pass:** 192 passed, exit 0  
**Verdict:** **Accept**

Read: amended issue `issues/12-rendition-composition.md`; implementer notes
`review-12-implementer-notes.md`; live-run findings F-51–F-58 as listed on the
ticket; `CONTEXT.md` (Rendition, Unit, Coverage, Angle Room); D2 / D4 / D7;
D20 composition object-backed. Code paths verified in
`service/renditions.py`, `coverage.py`, `transports/wiring.py`,
`transports/mcp_tools.py` (parsers), client dispatch + rendition panel, tests.

This pass does **not** re-author the seam axis. Closed findings listed below were
re-checked in code/tests so acceptance does not rest only on the implementer's
self-report.

**Labelling:** This is the second-axis product for the steward. The merged record
is `review-12-rendition-composition.md` (steward-authored after both axes).

---

## Criteria checklist

Against the amended ticket (Who composes, Criteria, shelf questions, F-51,
Done means).

| # | Criterion | Result |
|---|---|---|
| 1 | Executor composes via MCP; backend never calls a model; no casual dual-surface | **Met.** `propose_rendition` is in `MCP_ONLY` only (`wiring.py`). No HTTP compose route. Service stores executor-supplied units; no LLM client under `src/`. Same shape as `propose_claim` / ticket 09 decision on generated summaries. |
| 2 | Ordered units | **Met.** Ordinals from list order; projection orders by ordinal. |
| 3 | Confirmed-only + angle-scoped cites; both refusals | **Met.** Eligibility via `list_rendition_eligible_claims`. Distinct codes `CLAIM_UNCONFIRMED` and `CLAIM_NOT_ON_ANGLE` (refusal text names D2 / case-wide widen). Seam tests in `test_service_renditions.py`. |
| 4 | Required qualification present in citing unit | **Met.** Non-empty claim qualification must be exact substring of unit body → `QUALIFICATION_MISSING_FROM_UNIT`. Seam-tested. (Any non-empty qualification is gated, not only allegation postures — stricter than the minimum, acceptable.) |
| 5 | Independent artifacts (D2 / D7); no cut-from-long-form | **Met.** Free-standing insert bound to angle + run; no derive path. Destination only `x`/`thread`. |
| 6 | Rubric version recorded | **Met.** Taken from the composition run at propose time (`runs.rubric_version` → `renditions.rubric_version`). |
| 7 | `composition` object-backed; `story_intelligence` unmeasurable as decision | **Met.** Gauge: ≥1 rendition with ≥1 unit citing ≥1 claim. `story_intelligence` sole member of `_UNMEASURABLE_STAGES` with reason text that states decision, not neglect. CONTEXT + docs D20 agree. Interaction pair `propose_rendition → composition worked`. |
| 8 | Seam tests + interaction pair | **Met.** Both cite refusals + qualification; `test_operation_interactions.py` pair present. |
| 9–10 | Shelf scope + whole-element decided on evidence | **Met.** Case-scoped shelf retained; cite gate remains angle-scoped at `propose_rendition`. Whole-element allowed; unit body is free text. Recorded in CONTEXT Angle Room. Evidence is thin (throwaway seed) but the structural argument does not require Vela. |
| 11 | F-51 path test + investigate failing call | **Met.** `tests/test_client_api_paths.py` extracts client fetch templates and matches method+segments on the router. Root cause of operator JSON.parse was wrong process on :8000, not a missing path — investigation is honest; path guard still lands. Client non-JSON error improved. |
| 12 | Done means operator-readable thread on seeded throwaway | **Met structurally.** Real captures, confirmed claims, chosen angle, draft threads projectable in client Renditions panel. **F-52:** substance is hand-composed units, not model composition — recorded, not a hard criteria miss against ticket lines 72–81 (expect flat; rubrics are 16). |

Approval is correctly out of scope (ticket 13); status is `draft` only on write.

---

## Closed findings — verified this pass

| ID | Claimed | Spec re-check |
|---|---|---|
| **F-51** | Path test; root cause port conflict | **Holds.** Test exists and fails closed if route discovery empty. Root-cause reading accepted. |
| **F-54** | `parse_proposed_open_question`; structured refusal; `scope` alias; description names keys | **Holds.** Accumulates missing fields; canonical wins if both present; `tests/test_mcp_close_parse.py` covers. Description/schema agreement asserted via live tool list. |
| **F-58** | Same class on unit parse | **Holds.** `parse_rendition_unit`; description names `body` / `claim_ids`; tests present. |
| **F-53** | Dispatch form capture budget default 20 | **Holds.** `DEFAULT_CAPTURE_BUDGET = 20` in client; form field prefilled; posted as `capture_budget`; run meta shows used/budget. F-44 shape closed for this field. |

---

## Dispositions challenged or confirmed

### F-52 — recorded, not fixed — **Confirm**

Ticket "done means" requires a thread the operator can read on a seeded case with
real captures, not proof that a model can compose. The implementer met the
structural criterion and recorded the emptiness of model-driven composition
honestly. Live research loop (Fable) does **not** substitute for live
`propose_rendition`. Correct home for model-driven composition quality is ticket
**16** (rubrics tuned against real output). Do not treat seed units as composition
rubric evidence. Not a reject on ticket 12.

### F-55 — quotation conventions only in refusal text → ticket 16 / capture UX — **Confirm**

Found on the research loop (`propose_claim` locators), not on composition write.
Composition does not introduce a new locator surface. Teaching `e/{n}` vs region
form, or offering offsets / substring→range, is capture-UX and rubric work.
Not a ticket-12 composition defect; not a blocker for Accept.

### F-56 — classification vocabulary invisible → ticket 16 / D9 — **Confirm**

Exactly what D9 says standing questions are for. Pattern-matching peer claims is
expected failure mode on a fresh case. Composition does not own the six-dimension
vocabulary surface. Ticket 16.

### F-57 — no landing for human cross-document independence → design before Vela — **Confirm**

Per-claim `single_source` (or similar) when each claim binds one capture is
**correct under D4** — confirmation-at-use and claim shape are not the place to
launder multi-source. VISION §12 reserves "whether sources are genuinely
independent" to the human; the gap is that **nowhere records that judgement**
across documents. That is a product object / attestation design question, not a
missing composition refusal. **Do not invent it under ticket 12.** Decide before
Vela (nine sources on a contested topic will hit it constantly). Spec axis will
treat inventing multi-source at propose time as a *defect*, not a fix.

---

## What held (product)

- **Who composes is unambiguous in code.** Backend verifies and stores; MCP is the
  only write; no second dual-surface.
- **Ticket 11 eligibility is not widened.** `CLAIM_NOT_ON_ANGLE` is explicit.
- **D20 S-01 class from ticket 11 did not recur.** Composition measuring object
  and gauge wiring landed together; interaction test locks the seam.
- **`story_intelligence` not "fixed" by proxy.** Explicit unmeasurable remains.
- **Live research loop validates refusal doctrine** (`QUOTE_MISMATCH` first-retry
  recovery). That is architecture working; it is not composition acceptance.

---

## Observations (not Accept blockers)

1. **Eligible-set discovery is indirect** for the executor (`list_rendition_eligible_claims`
   is API-only). Correct under D18 caution. If live composition stalls, MCP-only
   list needs a D18-sized reason — product call, not a silent dual-surface.
2. **Composition requires a claimed run** (lease, token, budget ≥ 1, case
   serialisation) even though coverage is object-backed. Correct for claim_token
   authority; awkward operationally.
3. **Service does not require `coverage_dimension=composition`.** Rubric_version
   is whatever run proposes. Operator discipline + ticket 16.
4. **Draft alone moves composition to `worked`.** Right for ticket 12; tickets
   13–14 may refine whether rejected drafts still count.
5. **Client duplicates default budget constant (20).** Same number as
   `DEFAULT_CAPTURE_BUDGET` in `runs.py` — mild F-51-class drift risk, not a
   criteria miss. Optional later single source of truth.
6. **This axis did not re-click the browser** against the seeded case; projection
   code + seed script + suite support readability. Operator "has read" remains
   an operator fact.

---

## Verdict

All hard acceptance criteria in the amended ticket are met in the uncommitted
implementation. Closed findings F-51, F-53, F-54, F-58 re-check clean. Dispositions
F-52 (record), F-55/F-56 → 16, F-57 design before Vela are **confirmed**, not
challenged. No Accept-with-fixes items on this axis.

**Accept on Spec.**

Suite: **192 passed** (this pass). Commit remains steward-gated after merge of
both axes into `review-12-rendition-composition.md`.
