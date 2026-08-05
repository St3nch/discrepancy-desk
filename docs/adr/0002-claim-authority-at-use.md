# 2. Claim authority attaches at use, not at storage

Date: 2026-08-03

## Status

Accepted

## Context

Only the human may set authoritative evidence dimensions — that rule is
non-negotiable. But a single research pass can extract 150 claims, each carrying
six proposed dimensions plus entity matches and conflict candidates. Requiring
human review of every one before storage produces a four-figure decision count for
one thread. That is data entry with an approval button, which is the failure this
project exists to correct.

## Decision

Claims enter the Record unconfirmed — model-proposed, carrying suggested
dimensions, bound to captured bytes, honestly labelled. No gate on entry.

Human confirmation attaches when a claim is used to support published text. An
angle pulls in roughly a dozen claims; those get confirmed. A rendition may only
cite a confirmed claim, and unconfirmed claims are invisible to the composer.

The alternative was confirming at storage in bulk, with claims grouped by model
confidence so obvious ones could be swept. Rejected: bulk-confirming a hundred
classifications not individually read is precisely the rubber-stamp behaviour the
architecture exists to prevent. Better honestly unconfirmed than dishonestly
cleared.

## Consequences

The Record holds a large body of material with model-generated, unaudited
classifications. `unconfirmed` must be visually loud everywhere it appears, and any
feature reading the Record must treat confirmed and unconfirmed as different
populations — a pattern candidate built on unconfirmed claims is a lead about a
lead.

Review surface for one piece drops to ten or fifteen real decisions. Confirmation
persists with the claim, so a claim confirmed for one rendition is already
confirmed when a later case pulls it in.

Output pressure will attack this step rather than the publishability gate, because
degradation here is silent. Confirmation timestamps are recorded and the rate is
surfaced: forty claims in eleven minutes is not forty confirmations.
