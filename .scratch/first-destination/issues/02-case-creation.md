# 02 — Case creation

**What to build:** Operator can create a Case — the durable investigation into one topic —
and see it listed and opened in the browser client. This is the first real domain object;
everything else in the destination attaches to a case.

**Blocked by:** 01 — Backend and MCP tool surface skeleton

**Status:** ready-for-agent

- [ ] Operator can create a case with a topic/title through the browser client.
- [ ] A created case persists and appears in a case list.
- [ ] Opening a case shows an empty case view (no captures, claims, angles, or renditions
      yet) ready to hold them.
- [ ] A case never "completes" — there is no complete/closed state exposed for it.
- [ ] The governed operation for case creation is tested at the agreed seam.
