# 09 — Lead inbox

**What to build:** Operator drops a URL into a lead inbox, unattached to any case. It is
captured immediately on drop using the same Vault capture path as a dispatched run (ticket
04) — no separate fetch implementation. An optional, skippable summary may be attached.
Auth-walled/paywalled URLs are recorded as identity-only, explicitly marked not captured.
Operator can later attach a lead to an existing case, promote it to a new case, or dispose
of it.

**Two criteria were narrowed at review, before acceptance.** Both are recorded below in
their binding form; the reasoning and rejected alternatives are in D19
(`../discrepancy-desk-docs/decisions/lead-material-admission.md`) and in
`review-09-lead-inbox.md`. Narrowed, not waived — the ticket now states what was built.

**Blocked by:** 01 — Backend and MCP tool surface skeleton, 02 — Case creation, 04 — Capture
(Vault)

**Status:** complete

- [x] `add_lead(url, note)` captures the URL immediately, always, using the same capture
      mechanism as `capture_url` (04) — same storage, hashing, and parsing path, no
      duplicate implementation.
- [x] A lead holds captured material only; no claim is created from a lead before it is
      attached to a case.
- [x] An optional **operator-authored** summary can be stored on a lead and is skippable
      without blocking the drop. **Narrowed at review:** generated summarisation is
      deferred. Generating a description would make the backend an LLM client, and VISION
      §17 parks model selection deliberately — that choice is not one this ticket should
      force. The summary is a description, never extraction, either way.
- [x] An auth-walled or paywalled URL is recorded as an identity-only lead, explicitly
      marked not captured, and is distinguishable in the browser client from a real capture.
      **Narrowed at review (D19):** `identity_only` is triggered by HTTP response status
      alone — `401`, `402`, `403`. A soft wall returning `200 OK` with login or
      subscription HTML is captured as ordinary material. Automatic detection and an
      operator "not usable" mark were both considered and rejected; see D19.
- [x] Operator can attach a lead to an existing case, promote it to a new case, or dispose
      of it.
- [x] The governed operations are tested at the agreed seam, including an assertion that
      leads and runs produce identical capture records for the same URL.
