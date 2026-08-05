# 06 — Run lease and abandonment

**What to build:** A claimed run carries a lease that the executor's tool calls refresh. If
nothing touches the run within the lease period, it reverts to `approved` and becomes
claimable again. Captures and proposed claims already made are preserved, not rolled back.
Only one claimable run per case is allowed at a time.

**Blocked by:** 03 — Run dispatch and claim

**Status:** ready-for-agent

- [ ] Claiming a run starts a lease; any tool call against that run refreshes it.
- [ ] A run whose lease expires with no activity reverts automatically from `claimed` to
      `approved`.
- [ ] Attempting to approve or claim a second run on a case that already has a claimable or
      claimed run is refused.
- [ ] Governed operations are tested at the agreed seam for lease expiry/reversion and
      per-case serialization.
- [ ] Once 04 (Capture) and 05 (Claim proposal) exist, add a test confirming a reclaimed
      run's prior captures and proposed claims remain attached and visible to the new
      executor — this is a test-fixture dependency, not a reason to delay this ticket's
      build.
