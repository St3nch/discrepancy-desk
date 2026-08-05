# 9. Claims require byte-exact quotation

Date: 2026-08-03

## Status

Accepted

## Context

The executor is assumed untrusted (ADR 5). Capture-then-cite (ADR 1) guarantees the
supporting material exists in the Vault, but existence alone is a weak check: a
model satisfies "does this capture exist" by citing anything it fetched. Something
has to make the *connection* between claim and source verifiable, not just the
source's presence.

## Decision

`propose_claim` takes the run, the proposition, a capture id, a locator, the exact
quoted text, the six proposed dimensions, and the required qualification.
Verification runs in order and every step fails closed:

1. the capture exists and belongs to this run's case
2. the locator resolves inside that capture's element structure
3. the quoted text appears byte-exact at that locator
4. all six dimensions are present and are valid enum values
5. qualification is non-empty when posture is `allegation` or
   `participant_account`

Step 3 is load-bearing. With it, verification asks "do these exact words appear at
this position," which a model cannot satisfy by confabulating. That is the
difference between a check and a formality, and it is the single mechanism that
makes an untrusted executor safe.

This is stricter than the previous project, where a claim linked to a source and the
link was the whole verification.

Two escape valves are allowed, because without them summarising and reasoning
claims would be inexpressible and the rule would be routed around rather than
followed: multiple locator-and-quote pairs per claim, and inference claims
(`desk_inference` posture) citing other claims rather than captures — each of those
claims being itself quote-bound.

## Consequences

`capture_url` must return the parsed element structure with locators and text, not
just a capture id. The executor quotes from that response, never from its own
reading of the page — otherwise it would be citing bytes different from the ones
stored, and the mismatch would stay invisible until verification failed. Quotes
match by construction because the executor is quoting the stored bytes.

The response is capped, with a separate `read_capture(capture_id, range)` tool for
going deeper into a capture already made. The separate tool is preferred over
automatic pagination because it makes "the executor chose to read further into this
document" a visible, recorded act.
