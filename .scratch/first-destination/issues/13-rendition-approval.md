# 13 — Rendition approval

**What to build:** Operator reviews and approves the exact content of a rendition — text,
links, media, labels. Any change to approved text or to bound media (by hash, size, or MIME
type) after approval invalidates that approval.

**Blocked by:** 12 — Rendition composition

**Status:** ready-for-agent

- [ ] Operator can review a rendition's units and approve the exact reviewed content.
- [ ] Approval binds text, links, media reference, and labels as reviewed.
- [ ] Any edit to approved text after approval invalidates the approval.
- [ ] Media binding covers SHA-256, byte size, MIME type, reference, alt text, and rights
      state; replacing the bytes invalidates the approval.
- [ ] The governed operation is tested at the agreed seam, including the invalidation cases
      for text and media changes.
