# 8. Runs are claimed, not assigned

Date: 2026-08-03

## Status

Accepted

## Context

The backend owns runs and the executor is swappable (ADR 5). That leaves open how a
run reaches an executor: the backend pushes it to a named one, or an executor pulls
the next available.

## Decision

Runs sit in the registry with status `approved`. An executor calls
`claim_next_run()` and receives the oldest approved run; the status moves to
`claimed`. The backend never reaches out.

Push was rejected because the backend would need to know what executors exist, how
to reach them, and what to do when one is not listening. Pull keeps the executor
anonymous, which is what makes it swappable — a desktop chat client, an API-driven
agent, or anything else is identical from the registry's side.

Run states:

```
draft        question written, not yet approved
approved     claimable
claimed      an executor holds it and is working
suspended    the executor asked a question; waiting on the human
complete     closed normally, findings recorded
abandoned    claimed but never closed; reclaimable
cancelled    the human killed it
```

A claim carries a lease. The executor's tool calls refresh it; if nothing touches
the run for the lease period it reverts to `approved` and becomes claimable again.
Partial work is preserved rather than rolled back — captures already made are real
material bound to the run, and proposed claims stay for the same reason.

## Consequences

A run cannot be targeted at a particular executor. If bulk extraction should go to a
cheaper model and angle work to a stronger one, pull cannot express that. Fixable
later with an optional capability tag on the run and a filter on the claim;
deliberately left out for now.

A single run may be worked by more than one executor across its life. Accepted
deliberately — the alternative is discarding real captured material because a chat
session ended.

Concurrency is serialised by default: one claimable run per case at a time. The
arguments for allowing it are real but do not apply at this scale, and the executor
is a chat client, so concurrency would mean two chat sessions against one case.
Serialise because it is simpler; relax it if it chafes.
