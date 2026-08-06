# Review — Ticket 06 (run lease and abandonment)

**Date:** 2026-08-05
**Reviewers:** Claude (seam checks) and GPT (spec), independently
**Verdict:** Accepted after F-25a and F-25b were fixed.

*Backfilled from the review conversation. This was the first ticket reviewed on two
axes; the two findings below came from different reviewers and neither found the
other's.*

---

## Standing checks

| Check | Result |
|---|---|
| Vocabulary reconciliation | **Clean.** No new enum values; `abandoned` remains in the CHECK but reclaim uses `approved` |
| Fail-open inventory | **F-25a** |
| Destructive-write inventory | **Clean.** Reclaim writes status, lease, and token; all three are the point |
| Dead-capability inventory | **Clean.** |
| Write-once inventory | N/A |
| Projection completeness | **Clean.** `is_resume` and counts in the claimed-run packet |

---

## Findings

### F-25a — An executor operation could revive an already-expired lease

**Severity:** Blocking. **Closed.**

`capture_url`, `read_capture`, and `propose_claim` checked only that run status was
`claimed`, then `touch_run_lease` extended `lease_expires_at`. Because expiry is
evaluated lazily, a run sits in `claimed` with a dead lease until something looks at
it — and any tool call in that window renewed it. An executor could call a tool after
its deadline and regain authority without re-claiming, which defeats the central
behaviour of the ticket.

**Resolution:** `validate_and_refresh_claim` refreshes only a currently valid,
unexpired claimed lease. Absent or expired fails closed with `RUN_LEASE_EXPIRED`, which
does not extend. The run stays eligible for normal reclaim through `claim_next_run`.

### F-25b — A valid lease could be used by the wrong executor

**Severity:** Medium-high. **Closed.**

Requiring an unexpired lease closes stale revival. It does not close this:

```
executor A's lease expires
→ claim_next_run reclaims; executor B claims it, fresh lease issued
→ executor A wakes and calls capture_url
→ status is "claimed" and the lease IS valid — it is B's lease
→ A's call succeeds and refreshes B's lease
```

Both executors then write captures and claims to the same run, neither knows, and A
extends B's lease on every call. With a chat-client executor and a human stepping away
mid-run, this is not exotic.

**Resolution:** an opaque **claim token**, not executor identity. `claim_next_run` mints
it when transitioning to `claimed`, stores it on the run, and returns it in the packet.
Every run-touching tool presents it and it is validated in the same function that
validates lease expiry. Wrong or missing fails with `RUN_CLAIM_STALE`, whose
`what_you_can_do` says to call `claim_next_run` again rather than retry. Reclaim clears
the token so an old one can never match.

**This preserves ADR 8.** The token identifies *the claim, not the executor* — claim 47
and claim 48 of the same run are different tokens regardless of who holds them. There
is still no executor registry, no assignment, and no push.

---

## What held after the fix

The claim is atomic: status, lease, and token are set in one conditional update. The
refresh path re-checks status and token in its own `UPDATE ... WHERE`, closing the
select-to-update window on both paths.

Corrupt lease timestamps are treated as expired rather than skipped — fail-closed on a
path nobody would have written a test for.

The `list_runs` side-effect note in the module docstring says *do not clean this up
without moving expiry evaluation elsewhere*, which tells the next reader what would
break rather than merely that something is odd.

---

## Design decisions recorded

| Topic | Decision |
|---|---|
| Lease refresh | Shared choke point, so tools added in later tickets inherit the rule rather than copy it |
| Expiry | Evaluated, not scheduled. No background sweeper to supervise |
| On expiry | `claimed` → `approved`, lease and token cleared; captures and claims kept |
| TTL | 15 minutes |

Partial work is preserved rather than rolled back. A single run may be worked by more
than one executor across its life — accepted deliberately, because the alternative is
discarding real captured material because a chat session ended.

---

## Process note

Ticket 06 was reviewed on two independent axes for the first time. Timing meant the
seam reviewer saw the spec reviewer's findings before writing — the anchoring the split
exists to prevent. Corrected sequence: implementer reports to both reviewers
simultaneously; each responds; only then are findings merged.
