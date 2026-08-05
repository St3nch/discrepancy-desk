# 1. Capture before cite

Date: 2026-08-03

## Status

Accepted

## Context

The research executor is an LLM reading arbitrary web pages. It can fabricate a
source and a quotation in the same sentence without knowing it has done so. Some
mechanism has to make a claim's supporting material real rather than asserted.

## Decision

The executor cannot cite anything it has not first captured. Reading a page means
fetching it through the backend, which stores the raw bytes, hashes them, parses
them into an element structure, and only then permits a claim to bind to a region
inside it. The executor's web-read tool *is* the ingestion tool, and everything
read is captured whether or not it ends up supporting a claim.

The alternative was cite-then-verify: let the executor research freely and check
its cited URLs afterwards. Rejected because its failure mode is "claim exists,
verification failed, now what?" — a queue of orphaned claims to adjudicate.
Capture-then-cite fails closed at write time instead of triaging at review time.

A hybrid — free browsing for orientation, capture only what gets cited — was
rejected as the worst of the three. Orientation browsing is where the model forms
its picture of a topic; uncaptured, the Vault holds the footnotes but not the
reasoning substrate, and no honest corpus denominator can ever be stated.

## Consequences

Storage grows fast and junk is captured alongside signal. Every read is also a
write, so research is slower. A cheap captured-versus-promoted distinction is
required so raw capture does not clutter the case view (see ADR 6).

In exchange, fabrication becomes structurally impossible rather than something the
operator must catch, and the corpus denominator is honest — "6 of 74 eligible
documents" is sayable because all 74 exist.
