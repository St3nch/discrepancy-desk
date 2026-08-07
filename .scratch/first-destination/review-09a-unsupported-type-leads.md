# Review — Ticket 09a (unsupported-type lead parking)

**Date:** 2026-08-05
**Reviewers:** Claude (seam checks + steward) and GPT (spec), independently
**Verdict:** Accepted on both axes. No findings on either.

Small ticket, closing F-35 / S-03 / S-05 from ticket 09. Reviewed against the code at
`638fe1b`. The first ticket in the project to review clean on both axes with nothing to fix
— worth noting, since it was also the first ticket written from a decision record (D19) that
already named the rejected alternatives, so the scope guard did its work before any code
existed.

The spec axis independently reached the same reading of the downgrade: destructive on
rollback only, documented in the migration, no correction required.

---

## Standing checks

| Check | Result |
|---|---|
| Vocabulary reconciliation | **Clean.** `unsupported_type` added to `LEAD_MATERIAL_STATUSES`, to the migration's frozen `_MATERIAL`, and picked up by the existing `test_check_enums.py` tuple. The suite is bidirectional, so a one-sided addition would have failed — 133 green is itself the reconciliation evidence |
| Fail-open inventory | **Clean.** The new catch is narrowed to one refusal code and re-raises everything else |
| Destructive-write inventory | **Clean.** Insert only on the drop path |
| Dead-capability inventory | **Clean.** The status is produced by `add_lead` and rendered by the client |
| Write-once inventory | N/A |
| Projection completeness | **Clean.** Three visibly distinct states in the client, not two with a shared badge |

---

## What holds

**The catch is narrow, and that is the whole ticket.** The obvious way to write this is a
`try` around `retain_capture_from_bytes` catching `DeskRefusal` — which is exactly the F-17
defect, where a broad handler swallowed `CAPTURE_URL_BLOCKED` and told the executor to retry
a blocked target. What landed tests `refusal.code == _UNSUPPORTED_TYPE_CODE` and re-raises
otherwise, in the same shape as the auth-wall catch above it. A previously-found defect class
was not reintroduced at the one place it would naturally recur.

**`try/except/else` rather than initialising `capture_id` inside the `try`.** `capture_id` is
assigned only on the success branch, so a refusal cannot leave a stale id bound to a lead
whose bytes were never stored.

**The comment states why parking is safe:** `assert_content_type_supported` raises before any
Vault or Record write, so no orphan Vault object exists. That is the reasoning a later reader
would otherwise have to re-derive by reading `retain_capture_from_bytes`, and it is the fact
the whole approach depends on.

**The CHECK was rewritten, not extended.** The ticket warned against adding a third arm by
reflex to what was a binary constraint. What landed groups on the real invariant — `captured`
requires a capture row, and *both* non-capture statuses forbid one — so a future fourth
non-capture status joins an existing arm instead of adding a fourth clause. The rebuild keeps
`STRICT`, copies through `leads_new`, and carries the compound `inbox_status`/`case_id` CHECK
unchanged.

**The downgrade is honest about data loss.** It deletes `unsupported_type` rows with a
comment saying they cannot survive the reverse CHECK, rather than silently coercing them to
`identity_only` — which would have turned parked URLs into records claiming a login wall was
found. A destructive downgrade stated is better than a lossy one disguised.

**The client label is specific:** *"URL parked, not parsed (no Vault object)."* It says what
the state means rather than naming the enum value, which is the difference between a badge
and a status.

**`retain_capture_from_bytes` is untouched**, as required. The single shared capture path
still produces identical records through both doors.

**SSRF and hard fetch failures still refuse with no lead row.** The product state and the
fail-closed enforcement remain distinct, per D19.

---

## Process note

`638fe1b` was pushed before review. The standing convention from the foundation commit is one
commit only after review passes, and tickets 01–09 held to it.

The prompt is partly responsible — it said push everything, then start 09a, and the push
instruction was written before the ticket existed. Worth stating plainly rather than leaving
as an unremarked drift: **implementation commits are pushed after review, not with the
preceding batch.** No harm here — the ticket reviews clean — but the convention is worth
more than one clean instance.
