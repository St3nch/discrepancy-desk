# 09a — Unsupported-type drops park the URL

**What to build:** A lead drop whose content type the parser cannot handle currently refuses
with no lead row at all — the URL is lost. Catch that refusal and record the lead with the
URL and no capture, the same way an auth-walled URL is already recorded.

**Why now:** VISION names podcasts and videos as the inbox's central case, and D10's
justification for capturing on drop is that the material most worth having is the material
most likely to disappear. Today a login wall preserves the URL and a podcast does not. That
asymmetry runs against the inbox's stated purpose.

**Blocked by:** 09 — Lead inbox

**Status:** complete — accepted on both axes (`../review-09a-unsupported-type-leads.md`)

**Origin:** F-35 (seam review), S-03/S-05 (spec review), ticket 09. Deliberately not folded
into 09 after implementation and review. See D19 consequences.

**CHECK decision:** `unsupported_type` **forbids** `capture_id` (must be NULL), same as
`identity_only`. `captured` requires a non-null `capture_id`. Stated in migration 0012
and `add_lead` docstring — not a reflex third arm of the old binary.

- [x] A drop whose content type is unsupported records a lead with the URL, a distinct
      `material_status`, and `capture_id` NULL. No Vault object is written.
- [x] The new status is distinguishable in the browser client from both a real capture and
      an identity-only lead — three visibly different states, not two.
- [x] `retain_capture_from_bytes` is unchanged. Unsupported types raise before any Vault or
      Record write; parking is an `add_lead` catch plus a lead insert, exactly as
      identity-only already does.
- [x] The `leads` CHECK is rewritten deliberately rather than extended by reflex. It is
      currently binary (`captured` ↔ `capture_id` set, `identity_only` ↔ NULL). Decide and
      state whether the new status requires, forbids, or permits a `capture_id`.
- [x] The new value is added to `LEAD_MATERIAL_STATUSES` and picked up by
      `tests/test_check_enums.py` as a tuple, not a new test pattern.
- [x] SSRF and other hard fetch failures still refuse with no lead row. Parking applies only
      to material that was fetched and could not be parsed.

**Scope guard:** this ticket does **not** add an operator "not usable" mark, and does not
touch soft `200 OK` walls. D19 rejected both, and the reasoning there is what keeps this
ticket small.
