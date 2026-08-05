# 4. Renditions are generated in parallel, never cut down

Date: 2026-08-03

## Status

Accepted

## Context

One angle produces output for several platforms — X post, X thread, Truth Social,
Substack article, later a video script. Either each is written independently from
the angle, or a long form is written first and compressed into the shorter ones.

## Decision

Each rendition is generated independently, from the angle plus its confirmed
claims, written natively for its platform.

Deriving by cutting was rejected on three counts.

Qualification survival: every rendition must preserve the required qualification
attached to the claims it rests on. Compression is lossy and aimed at length, and
qualification language is exactly what it sheds first — "according to a statement
prepared for a 2019 oral-history conference" is nineteen words a thread-cut will
happily drop. Generated in parallel, qualification is a generation constraint
rather than something defended against the compressor.

Platform capacity genuinely differs: a thread can carry qualification inline in the
unit; a single post may not have room, which means the claim may simply not be
usable in that format. That is a correct outcome, which cutting would paper over by
compressing until it fits.

Order of work: cutting forces the long form to be written first, which is backwards
when the destination is a single X thread.

## Consequences

Consistency across renditions is not guaranteed. Two independently generated
renditions of one angle may emphasise different things. Acceptable — different
platforms, different audiences, one shared claim set, so they cannot contradict on
facts. Divergent emphasis is ordinary editorial practice.

Structurally: `case -> angle -> N renditions`, each separately approved, separately
bound, separately recorded. No new machinery required.
