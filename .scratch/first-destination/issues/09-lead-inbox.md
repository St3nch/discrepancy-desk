# 09 — Lead inbox

**What to build:** Operator drops a URL into a lead inbox, unattached to any case. It is
captured immediately on drop using the same Vault capture path as a dispatched run (ticket
04) — no separate fetch implementation. An optional, skippable summary may be generated.
Auth-walled/paywalled URLs are recorded as identity-only, explicitly marked not captured.
Operator can later attach a lead to an existing case, promote it to a new case, or dispose
of it.

**Blocked by:** 01 — Backend and MCP tool surface skeleton, 02 — Case creation, 04 — Capture
(Vault)

**Status:** ready-for-agent

- [ ] `add_lead(url, note)` captures the URL immediately, always, using the same capture
      mechanism as `capture_url` (04) — same storage, hashing, and parsing path, no
      duplicate implementation.
- [ ] A lead holds captured material only; no claim is created from a lead before it is
      attached to a case.
- [ ] An optional summary can be generated for a lead and is skippable without blocking the
      drop.
- [ ] An auth-walled or paywalled URL is recorded as an identity-only lead, explicitly
      marked not captured, and is distinguishable in the browser client from a real capture.
- [ ] Operator can attach a lead to an existing case, promote it to a new case, or dispose
      of it.
- [ ] The governed operations are tested at the agreed seam, including an assertion that
      leads and runs produce identical capture records for the same URL.
