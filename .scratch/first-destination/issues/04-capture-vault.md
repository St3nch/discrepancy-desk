# 04 — Capture (Vault)

**What to build:** A claimed run's executor calls `capture_url` to fetch, hash, and parse a
URL into the Vault's element structure, receiving a locator map back; `read_capture` goes
deeper into an already-made capture beyond the initial size cap. Captures count against the
run's budget and `capture_url` refuses once the budget is exhausted.

**Blocked by:** 03 — Run dispatch and claim

**Status:** ready-for-agent

- [ ] `capture_url(url)` stores raw response bytes immutably, records a SHA-256 hash, and
      parses content into an addressable element structure
      (`document_versions → elements → regions`).
- [ ] `capture_url` response includes the capture ID and a locator map with each element's
      text, up to a size cap.
- [ ] `read_capture(capture_id, range)` returns further content from an already-made capture
      beyond the cap.
- [ ] Each capture is bound to the run (and thus the case) that made it.
- [ ] `capture_url` counts against the run's declared capture budget and refuses once
      exhausted.
- [ ] Any generated Markdown/HTML projection is clearly marked read-only/non-authoritative.
- [ ] The governed operations are tested at the agreed seam, including the
      budget-exhaustion refusal.
