# Implementer notes — Ticket 12 (rendition composition)

**Date:** 2026-08-06  
**Author:** implementer (not a dual-axis review record)  
**Status:** Working notes for the steward and for the independent reviewers.  
**Not:** `review-12-rendition-composition.md` — that file is written after the
spec pass by a reader who did not write the code.

These notes were briefly misfiled as `review-12-standards-axis.md` and
`review-12-spec-axis.md` after a prompt to "send the live-run report to both
axes" was read as writing both review passes. Renamed and merged so they are
labelled as what they are.

---

## Defect class (keep)

**The tool description and the accepted schema were two artifacts describing one
contract with nothing checking they agreed.** Same shape as F-51 (client path vs
router). Three instances in this project:

| Instance | Two artifacts | Failure mode |
|---|---|---|
| F-51 | `client/src/api.ts` paths ↔ API router | Vite HTML → bare JSON.parse |
| F-54 | `close_run` description "scope" ↔ dict key `proposed_scope` | Bare KeyError string at end of live run |
| F-58 | `propose_rendition` description ↔ unit keys `body` / `claim_ids` | Latent AttributeError/ValueError |

Enforcement that works: extract/assert agreement (paths on router; description
contains required keys; parse helpers refuse missing fields with structured
`DeskRefusal`).

---

## What was built (ticket 12)

- Migration `0015`: renditions / units / unit_claims; status includes draft
  (only draft written); destination `x`/`thread`.
- `propose_rendition` **MCP_ONLY**: ordered units; angle must be `chosen`; cites
  only angle-linked confirmed claims (`CLAIM_UNCONFIRMED`, `CLAIM_NOT_ON_ANGLE`);
  qualification exact substring in unit body; rubric_version from composition run.
- `composition` coverage object-backed (≥1 rendition with ≥1 unit citing ≥1 claim).
  `story_intelligence` stays unmeasurable as a stated decision (D20).
- F-51 path test; clearer non-JSON client errors; optional `VITE_API_PROXY_TARGET`.
- F-54 / F-58: structured parsers on nested MCP dicts; description names keys;
  alias `scope` → `proposed_scope`; missing fields accumulate into one refusal.
- F-53 (steward): dispatch form exposes `capture_budget` prefilled at 20.
- Seed throwaway case (not Vela); hand-composed draft threads for browser read.
- Suite at implementer last green: **192** (re-verify after F-53).

---

## Seam checklist (implementer self-pass — not acceptance)

| Check | Notes |
|---|---|
| Vocabulary | Rendition status/platform/format in CHECK + evidence + test_check_enums |
| Fail-open | Empty eligible set, empty unit claims, not chosen, unconfirmed, wrong angle all refuse |
| Destructive-write | Insert-only draft |
| Dead-capability | compose is MCP; get_case projects threads; eligible-list API-only by design |
| Projection | Ordered units + claim_ids in get_case / client panel |
| Transport | propose_rendition MCP_ONLY only |

---

## Criteria self-check (implementer — not acceptance)

| Criterion | Self-read |
|---|---|
| Executor composes via MCP; no backend model | Yes |
| Ordered units; both cite refusals | Yes + tests |
| Qualification in unit | Yes + tests |
| D7 independent artifacts; rubric_version | Yes |
| composition object-backed; story_intelligence unmeasurable as decision | Yes |
| Seam + interaction pair | Yes |
| F-51 path test + failing-call investigation | Yes (wrong process on :8000) |
| Shelf scope + whole-element on evidence | Case-scoped shelf kept; e/{n} allowed — in CONTEXT |
| Done means operator-readable thread | Structurally yes (seed + UI); **composition not model-driven** — F-52 |

---

## Live run (operator) — findings disposition

First live model research loop: claim → context → capture → propose_claim → close.
Suspended for scope ruling rather than inventing. QUOTE_MISMATCH doctrine worked
(first-retry recovery).

| ID | Status | Notes |
|---|---|---|
| **F-54** | Closed | parse_proposed_open_question; description agreement |
| **F-58** | Closed | parse_rendition_unit; same class, found at self-review |
| **F-53** | Closed | capture budget on dispatch form (default 20) |
| **F-52** | Open as record | Composition still not model-driven end-to-end; ticket 16 |
| **F-55** | Open | Locator conventions only in refusals → ticket 16 / capture UX |
| **F-56** | Open | Classification vocab invisible → ticket 16 / D9 |
| **F-57** | Design | Cross-doc corroboration / independence landing → before Vela |

### F-52 — done-means was structural

The two readable threads were hand-composed through the service seam, not by a
model over MCP. "Done means a thread the operator reads" was met as projection
+ real captures + chosen angle, and empty as evidence that the executor can
compose under refusals. The Fable/live research run partly answers the *research*
loop; **composition itself has still not been model-driven end to end.** Ticket
16 rubric work is where that gets tested properly. Do not treat seed units as
composition-rubric evidence.

### F-57 — design (not a ticket-12 bug)

Per-claim `single_source` under D4 is correct. Gap: nowhere for the human
independence judgement (VISION §12) to land across documents. Decide before
Vela; do not invent under composition.

---

## Unease carried forward

1. Eligible-set discovery is indirect (API-only list; executor intersects context
   or learns via refusals). MCP-only list may be needed if models stall — D18-sized
   reason required.
2. Composition still needs a claimed run (budget ≥ 1, case serialisation).
3. `rubric_version` is whatever run proposes; service does not require
   `coverage_dimension=composition`.
4. Qualification is exact substring — rubrics should say paste verbatim.
5. Draft status alone moves composition to `worked` — tickets 13–14 may refine.

---

## Commit policy

**Nothing commits until independent dual-axis review is in and the steward merges.**
This file is not that review.
