# 6. Rubrics attach to operations and are versioned

Date: 2026-08-03

## Status

Accepted

## Context

The executor needs standing discipline — the questions it asks of every source it
reads, every claim it extracts, every angle it proposes. That guidance will be
tuned constantly during the first year, and claims produced under different
guidance are not comparable.

## Decision

Standing question sets attach to operations — reading a source, extracting a claim,
working the public question, proposing an angle, closing a run — not to research
stages. Operations are the stable unit: the discipline of reading a source is
identical on run one and run twelve.

Each set is a versioned repository artifact. Every claim records the rubric version
that produced it, and a rubric change never applies retroactively. Correcting a
class of error means amending the rubric and re-running the affected work,
producing superseding claims with lineage.

A single document was rejected: adequate if tuning were rare, and it is not. Every
tweak would bump the whole thing, destroying the ability to say which claims came
from which guidance.

Per-stage sets were rejected because stages are a coverage gauge, not a pipeline
(ADR 3). A run working the public question still reads sources and extracts claims,
so per-stage sets would either duplicate the source-reading questions six times or
leave the executor without them.

## Consequences

More files and more indirection, with a risk of sets drifting apart in tone.
Mitigated by keeping them short and few.

"Which claims came from the bad rubric" becomes an answerable question, and the
affected work can be re-run selectively.

Two companion mechanisms follow. A run that becomes uncertain mid-flight suspends
and surfaces the question rather than building forty minutes of work on a wrong
assumption. And the interface must distinguish answering a suspended question
(which resolves one instance) from amending a rubric (which resolves the class) —
the cheap habit is answering the instance forty times instead of fixing the rubric
once.

Class-level drift is structurally invisible from inside any single review, so
aggregate views are required: classification distributions per rubric version,
operator correction rate, cross-version comparison. All are counts over data
already recorded.
