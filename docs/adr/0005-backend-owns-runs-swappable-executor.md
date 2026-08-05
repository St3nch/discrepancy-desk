# 5. The backend owns runs; the executor is swappable

Date: 2026-08-03

## Status

Accepted

## Context

The reasoning work — research, extraction, classification, drafting — has to happen
in an LLM. Doing that through a metered API imposes per-token cost before the
project has revenue. Doing it in a flat-rate desktop chat client is affordable, but
a chat window cannot reach the Vault, and capture-then-cite (ADR 1) requires the
fetch to land in backend storage.

An MCP tool surface resolves the tension: the chat client calls backend tools, so
the reasoning is theirs and the bytes are ours.

## Decision

The backend defines every run — question, scope, rubric version, capture budget —
and owns the run record. An executor claims a run through an MCP tool surface and
works through it: `claim_next_run`, `read_case_context`, `capture_url`,
`read_capture`, `propose_claim`, `suspend_run`, `close_run`, `add_lead`.

Every artifact is backend-created. The executor holds no run state and writes
nothing directly.

Letting the executor hold run state was rejected: it would put rubric binding,
lineage, and budget inside a conversation the backend does not control.

Using the chat client as a research environment with capture done afterwards was
rejected as cite-then-verify by another name (ADR 1).

Driving the agent directly by API from day one is correct eventually but forces
per-token cost before there is revenue.

## Consequences

The executor is interchangeable — a desktop chat client under a flat subscription
today, an API-driven agent later, using the same tools. A provider change is
configuration, not a rebuild.

This property must be actively defended. Every temptation to let the executor hold
state or make a judgment the backend should own spends it, and spends it quietly.

The discovery mechanism is deferred by this decision: the executor brings its own
search and the backend captures what it reads. A search-provider choice is only
needed when an API-driven agent replaces the chat client.

Suspend-and-ask becomes conversational under a chat executor, at the cost of run
state living in a conversation. Acceptable for a single operator present at the
machine; a reason to prefer a backend-driven executor once runs get long.

The executor is assumed untrusted. ADR 9 is what makes that assumption survivable.
