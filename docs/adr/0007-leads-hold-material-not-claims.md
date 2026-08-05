# 7. Leads hold material, never claims

Date: 2026-08-03

## Status

Accepted

## Context

Not all material arrives through a dispatched run. A podcast encountered by chance,
a video surfaced by a recommendation engine, a link from a conversation — ambient
discovery is how a great deal of real journalism starts, and it needs somewhere to
land that is not "open a whole case."

## Decision

A lead is a URL dropped into an inbox, unattached to any case.

It is captured immediately on drop, always. The material most worth having is the
material most likely to disappear — the deleted post, the pulled video, the article
quietly edited after publication. Fetching is cheap; decay is not recoverable.

It holds no claims until attached to a case. The same source yields different
propositions depending on what is being investigated, so extraction in a vacuum
produces claims that serve no case. Claims come from runs, which carry questions,
rubric versions, and lineage; a claim born outside a run would have none.

An optional summary — description, not extraction — keeps the inbox browsable. It
is the only part that costs money, so it is deferrable and skippable.

Extraction on drop was rejected: it fills the Record with generic claims from
material that mostly never becomes anything, costs money per stray link, and
creates a claim provenance path that skips the run model entirely.

Making fetch an operator-toggleable option was rejected because it conflates two
different costs. Fetch is bandwidth and CPU on the operator's own machine; the
summary is the model call. Splitting them gets the cost control without trading
away the thing that cannot be recovered.

## Consequences

A lead is dumber than it could be — captured bytes and a note until attached. The
optional summary mitigates this.

Auth-walled and paywalled URLs are recorded as identity-only leads, explicitly
marked as not captured. Storing a login wall as though it were an artifact is worse
than storing nothing, because it masquerades as evidence.

A lead is later attached to an existing case, promoted to a new one, or disposed of.
