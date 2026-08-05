# 10. Two transports over one service layer

Date: 2026-08-03

## Status

Accepted

## Context

Two audiences reach the backend. A research executor works runs through the MCP
tool surface (ADR 5). The operator works the browser client — dispatching runs,
resolving suspended ones, working run-close agendas, confirming claims, developing
angles, approving renditions, recording publication.

Those could share one transport or use two.

## Decision

Two transports over one service layer. FastAPI serves `/mcp` for the tool surface
and `/api/*` for the operator client. Both call the same governed service
functions.

**A service function is wired to one transport or the other, never assumed safe on
both.** Human-only operations — confirming claims, setting authoritative evidence
dimensions, resolving entity identity, classifying publication risk, choosing an
angle, approving content, dispatching a run — are reachable from `/api` only.

A single shared surface was rejected on two grounds.

The audiences want different shapes. MCP tools are built for a model working
autonomously: `claim_next_run` hands over a whole work packet. The operator wants
views — a case with claims grouped by status, a run-close screen with the agenda on
top and detail folded away. Read-heavy, paginated, shaped for rendering. Forcing
both through one surface means either MCP bloats with operator views or the client
reassembles screens from tools designed for something else.

The security argument is stronger. The tool surface is deliberately minimal because
it is exposed to something untrusted. Every tool added to it is surface an untrusted
executor can reach. Separate transports make "the executor cannot confirm a claim"
a structural guarantee rather than a naming convention.

## Consequences

Adding a human-only operation to the MCP surface must be an obvious mistake rather
than a plausible convenience. The wiring should be explicit enough that it reads
wrong.

The service layer is the seam the specification already chose for testing, so this
costs nothing architecturally — tests call service functions in-process, and one
thin end-to-end test per transport proves the wiring.

The browser client holds no privileged logic. It calls governed operations and
renders what comes back, which is what makes it the cheapest layer in the system to
replace.
