# 15 — Capture acquisition receipt

**What to build:** A capture currently records the requested URL, the raw bytes, their
SHA-256, the Content-Type header, and a timestamp. It does not record the response status,
the final URL after redirects, the redirect chain, or any other response header.
`safe_http_get` returns body bytes and Content-Type and discards the rest.

VISION §7 describes the Vault as holding immutable originals **and acquisition receipts**.
What exists is the original without the receipt.

**Why this is scheduled here and not earlier:** the missing fields cannot be backfilled —
every capture already taken is permanently without them. But no real research material passes
through the system until the Vela run, and captures made while building tickets 10–14 are
test material. Waiting therefore costs nothing real, and shipping the spine first is D1.
Waiting *past* Vela costs the provenance of the first genuine corpus, which is exactly the
run the whole architecture exists to compare against v1.

**Blocks:** the Vela end-to-end run. This is the gate — do not run Vela with a thin receipt.

**Blocked by:** 14 — Publication recording

**Status:** not started

**Origin:** steward note and S-04 (spec review), ticket 09.

- [ ] A capture records the final response status, the final URL after redirects, and the
      redirect chain (each hop's URL and status), alongside what it records today.
- [ ] The requested URL remains distinct from the final URL. `captures.url` today is what the
      caller asked for; that meaning does not change, and the final URL is a new field rather
      than an overwrite.
- [ ] The redirect chain is recorded for lead drops and run captures identically — same
      shared path, per D18's identical-capture-records rule.
- [ ] `safe_http_get`'s return shape changes deliberately and in one place. Every caller is
      checked; the SSRF re-validation on each hop is unchanged and its tests still pass.
- [ ] A capture that reached its bytes through a redirect is distinguishable from one that
      did not, in the operator projection.

**Explicitly out of scope:** storing arbitrary response headers wholesale. Decide the named
fields worth keeping; a header bag is a data clump that invites later code to switch on
whatever happens to be in it.

**Note for whoever picks this up:** this touches the foundational fetch path with fourteen
tickets on top of it, and the failure mode of this codebase is boundaries that hold on one
path and not the parallel one. The lead path and the run path must come out identical.
