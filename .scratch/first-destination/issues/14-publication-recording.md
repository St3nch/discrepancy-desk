# 14 — Publication recording

**What to build:** After the operator manually posts an approved rendition, the system
records what actually went out: each unit's ordinal, platform, owned account, external post
identity, canonical URL, published time, and verification state. Changing a recorded or
scheduled publication time never alters the approved text.

**Blocked by:** 13 — Rendition approval

**Status:** ready-for-agent

- [ ] Operator can record, per unit, ordinal, platform, account, external post identity,
      canonical URL, published time, and verification state.
- [ ] Recording publication is only possible for a unit whose rendition/approval is intact
      (not invalidated).
- [ ] Editing the recorded or scheduled publication time does not alter the approved text.
- [ ] The rendition's lifecycle reflects `published` (or `rejected`, if the operator
      instead rejects it) as its end state.
- [ ] The governed operation is tested at the agreed seam.
