# 12 — Rendition composition

**What to build:** From a chosen angle and its confirmed claims, a rendition is composed for
one platform — an X thread of ordered units, each citing only confirmed claims, written
natively for the platform rather than cut down from something longer.

**Blocked by:** 11 — Angle Room and claim confirmation

**Status:** accepted — both axes (review-12-rendition-composition.md)

---

## Who composes

**The executor composes; the backend never calls a model.** A rendition is proposed through
MCP under a composition rubric, exactly as claims are proposed. The backend storing a
rendition an executor wrote is the same shape as storing a claim an executor proposed.

This was settled once already at ticket 09, where generated lead summaries were declined
because making the backend an LLM client forces a model-selection decision VISION §17 parks
deliberately. The same reasoning applies with more force here: composition is the operation
where model quality shows most.

Approval is ticket 13. This ticket ends with a rendition in `draft`.

---

## Criteria

- [ ] The executor composes a rendition for a chosen angle, targeting the X-thread format,
      through an MCP operation. Human-only surfaces stay API-only per `wiring.py`; adding a
      second dual-surface operation needs a reason as good as D18's.
- [ ] The rendition is composed of ordered units.
- [ ] Every unit's cited claims come only from that angle's confirmed set — citing an
      unconfirmed claim is refused, and citing a claim confirmed on a *different* angle is
      refused. Ticket 11 made eligibility angle-scoped; composition must not widen it back.
- [ ] Required qualification language attached to a cited claim is present in the unit that
      cites it.
- [ ] Renditions are independent artifacts, not derived from one another (D2). Nothing in
      this ticket assumes a canonical long draft that other formats are cut from.
- [ ] A rendition records the rubric version it was composed under, as claims do.
- [ ] `composition` coverage becomes object-backed now that renditions exist — it has been
      reading `unmeasurable` for exactly this reason (D20). `story_intelligence` stays
      `unmeasurable`; say so as a decision, not by omission.
- [ ] The governed operations are tested at the agreed seam, including both refusal cases,
      and a cross-operation pair added to `test_operation_interactions.py`.

## Two questions carried from ticket 11, to be decided here on evidence

- [ ] **Shelf scope.** The quotation shelf is case-scoped; rendition-eligible claims are
      angle-scoped. Composition is where that asymmetry either bites or does not. Decide it
      with evidence from a real rendition, and record the decision either way.
- [ ] **Whole-element shelf entries.** Region form was declined twice as ceremony, with the
      stated trigger being composition output that is actually worse for it. If a
      block-granularity quotation produces a bad unit, that is the evidence; if it does not,
      the question closes.

## F-51 — client paths are unverified against the router

- [ ] A test extracts literal `/api/…` paths from `client/src/api.ts` and asserts each
      resolves on the router. F-03 closed `wiring.py` ↔ router bidirectionally; this is the
      next leg, and it is unchecked.
- [ ] Find and fix the call currently failing. The operator loaded the client after ticket 11
      and got `JSON.parse: unexpected character at line 1` — the Vite proxy falling through
      to `index.html` — with all 173 tests green.

## Done means a thread the operator reads

**This ticket is not finished when a rendition validates.** It is finished when it produces
an X thread the operator has read.

- [ ] A seeded case exists with real captures, real confirmed claims, and a chosen angle —
      not fixture data, which cannot show whether the output is any good. A throwaway topic
      is fine; Vela is reserved for ticket 17.
- [ ] The rendition is readable in the browser.

**Expect flat.** Composition rubrics are ticket 16, and rubric text is tuned against real
output rather than written in advance (D9). Structurally sound and flat is the expected
result and is not a defect. Flat *and* vague would be — that would mean claims are thin or
qualification is swallowing the content, and it would be worth finding out here rather than
at Vela.

This is also a partial rehearsal of the run: the first time an executor drives a governed
operation for real. Record what it hits — refusals, whether it self-corrects or stalls, and
anywhere the MCP surface is hard to work with. That is ticket 17 information arriving five
tickets early.

## Comments

### Implementer report (awaiting review)

**Suite:** 184 passed. No implementation commit until review on both axes.

**Built**

- Migration `0015_renditions`: `renditions`, `rendition_units`, `rendition_unit_claims`.
  Status CHECK includes `draft|cleared|published|rejected` (only `draft` written here).
  Destination only: `x` / `thread`.
- `propose_rendition` (MCP_ONLY): requires claimed run + token; angle must be `chosen`;
  units ordered; every unit cites ≥1 claim; refuses `CLAIM_UNCONFIRMED`,
  `CLAIM_NOT_ON_ANGLE`, `QUALIFICATION_MISSING_FROM_UNIT`, `ANGLE_NOT_CHOSEN`, etc.
  Rubric version taken from the composition run (same pattern as claims).
- `composition` coverage is object-backed (≥1 rendition with ≥1 unit citing ≥1 claim).
  `story_intelligence` stays `unmeasurable` as an explicit D20 decision (reason text
  updated). CONTEXT + docs D20 amended.
- `get_case` / `read_case_context` project real angles, public questions, shelf, renditions
  (context no longer returns empty `list[str]` stubs for angles/renditions).
- Client: rendition thread panel; `parseJson` no longer dies with a bare JSON.parse error
  when the proxy returns HTML/plain text.
- F-51: `tests/test_client_api_paths.py` extracts fetch paths from `client/src/api.ts` and
  matches method+segments on the router. Interaction pair:
  `propose_rendition → composition coverage worked`.

**F-51 — what was actually failing**

No literal path in `api.ts` was missing from the router (all match). The operator symptom
reproduced on this machine as: **port 8000 held by `bootstrap-mcp` (unrelated project), not
the Desk.** Vite proxies `/api` → 8000 → plain-text 404 → `JSON.parse` blows up. Fixed
operationally by (1) clearer client error naming the proxy target, (2) the path test so a
real drift cannot hide again, (3) optional `VITE_API_PROXY_TARGET` in `vite.config.ts`.

**Seeded case (throwaway, not Vela)**

- Case #1: "Throwaway: example.com domain reservation notes (ticket 12 seed)"
- Real captures: `example.com`, `iana.org/domains/reserved`
- Chosen angle + two draft renditions (3 units each). Composition reads `worked`.
- Script: `.scratch/first-destination/seed-ticket-12-throwaway.py`
- Browser: Desk on `127.0.0.1:8001`, Vite on `5173` with
  `VITE_API_PROXY_TARGET=http://127.0.0.1:8001` (because 8000 is occupied). Open case #1.

**Shelf decisions (on evidence)**

1. **Case-scoped shelf is fine.** Composition eligibility is angle-scoped and enforced at
   `propose_rendition`. The shelf is a shared quotation pool for the case; it does not
   widen unit citation. Making the shelf angle-scoped would force re-selecting the same
   quotation for each candidate angle without changing what composition can cite. Recorded
   in CONTEXT.
2. **Whole-element locators did not hurt.** Seed shelf entry used `e/0` ("Example Domain").
   Units that cite the claim are not stuck pasting the whole element — the unit body is free
   text constrained by qualification and claim id, not by locator form. Region form remains
   available; not required. Question closes unless a later platform format forces
   quote-paste from the shelf itself (not built yet).

**Live executor (ticket 17 preview) — plain statement**

I did **not** drive `propose_rendition` through a live model over MCP. Composition was
exercised through the service seam and a seed script with hand-written units. So I have
not observed model self-correction against refusals on this surface. What the surface will
make awkward for a model (from reading the tool and the refuse codes):

- Eligible set is not a dedicated MCP read — executor must derive it from
  `read_case_context` angles + claim confirmation status, or discover via
  `CLAIM_NOT_ON_ANGLE` / `CLAIM_UNCONFIRMED` refusals (codes teach the rule).
- Composition still needs a claimed **run** (lease + token) even though coverage for
  composition is object-backed, not run-dimension-backed. Operator must dispatch and
  approve a composition run first. Capture budget minimum is 1 even when composition
  needs zero captures.
- Case serialisation: a held composition run blocks other approved work on the case
  (`RUN_CASE_BUSY`) until close/cancel — hit this while re-seeding.
- Qualification is exact substring match in the unit body — models that paraphrase the
  qualification will be refused (`QUALIFICATION_MISSING_FROM_UNIT`).

**Unease / not built**

- Claim bindings on the seed used short title elements (`e/0`, `e/4`); unit text elaborates
  beyond the bound quotation. Grounded enough for "flat", thin as evidence packaging —
  better locator selection belongs in research practice / ticket 16 rubrics, not a
  composition-layer rewrite.
- No API write path for renditions (correct — human does not compose). No approval (13).
- Did not add dual-surface for `list_rendition_eligible_claims` (still API-only); executor
  discovers via context + refusals. May want MCP-only list before Vela if models stall.
- `story_intelligence` left unmeasurable deliberately; do not "fix" by inferring from angles.

**Docs touched:** `CONTEXT.md` (code repo); `coverage-measurement.md` D20 (docs repo).

### Live executor run (operator) + findings F-54–F-57

First end-to-end live model loop: claim → context → capture → propose → close.
Two captures of twenty, three claims, two open questions; one item flagged for
operator scope ruling rather than guessed. Suspended judgement instead of
inventing — executor criterion from VISION, observed.

**Praise worth recording:** `QUOTE_MISMATCH` called the best refusal in the system —
what happened, what was preserved, how to fix; recovered on first retry. Refusal
doctrine working against a real model.

| ID | Severity | Status |
|---|---|---|
| **F-54** | Blocking | **Fixed in ticket 12** — `close_run` MCP adapter KeyError on `proposed_scope` when description said "scope"; leaked bare field name instead of structured refusal. Parser now accepts `proposed_scope` or `scope`, refuses missing keys with `OPEN_QUESTION_FIELD_MISSING`, description names the keys. |
| **F-58** | Medium | **Fixed in ticket 12** — same description/schema class on `propose_rendition` units; `parse_rendition_unit` + description names `body`/`claim_ids`. |
| **F-53** | Medium | **Fixed in ticket 12** — dispatch form posts capture budget (default 20 prefilled). Service already supported it; form did not (F-44 shape / D8). |
| **F-52** | Record | **Open as honesty, not a blocker for structural done** — the two readable threads were hand-composed, not model-driven. Live research loop (Fable) is not live composition. Ticket 16 is where model-driven composition gets tested properly. |
| **F-55** | Medium | Open — quotation surface conventions only in refusal text; region locators require hand-counting. Ticket 16 / capture UX: offsets or substring→range. |
| **F-56** | Medium | Open — classification vocabulary invisible to executor; pattern-matched prior claims. Ticket 16 (rubrics / D9). |
| **F-57** | Design | Open — no vocabulary for cross-document corroboration; `single_source` per claim is correct under D4 but nowhere for human independence judgement to land. Decision before Vela. |

**Defect class (F-51 / F-54 / F-58):** the tool description (or client paths) and the
accepted schema were two artifacts describing one contract with nothing checking they
agreed. Worth carrying into the independent review file.

**Review labelling:** implementer working notes live in
`../review-12-implementer-notes.md` (not dual-axis acceptance). Independent
`review-12-rendition-composition.md` is written by the steward after the spec pass.
**No implementation commit until that review is merged.**
