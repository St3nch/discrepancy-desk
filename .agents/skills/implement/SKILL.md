---
name: implement
description: "Implement a piece of work based on a spec or set of tickets."
disable-model-invocation: true
---

## Discrepancy Desk mode

Implementation starts only when all are true:

- there is one final accepted Desk ticket;
- the Project Steward supplied an exact implementation start commit;
- the worktree/branch is clean at that commit;
- exactly one capable available model is designated as Writer for the ticket.

The Writer may read the whole repository but must keep mutation inside the accepted ticket and project role boundaries. Do not edit Product authority merely to make implementation easier. Report adjacent work instead of silently broadening scope.

Use the shared canonical project skill under `.agents/skills/`; every supported coding client follows the same implementation method. Writer selection does not grant Project Steward authority.

### Implementation loop

1. Re-read the accepted ticket, relevant authority, accepted spec/ADR, and coding standards.
2. Reconcile the ticket against the exact start commit. If a material premise is false, stop and report rather than coding around it.
3. Use `/tdd` where meaningful at pre-agreed seams.
4. Run bounded static/test feedback regularly during implementation.
5. Preserve fail-closed authority, provenance, lineage, and refusal behavior required by the ticket; do not create caller-controlled escape hatches.
6. Run the ticket-appropriate final checks.
7. Use `/code-review` against the exact start commit and accepted ticket/spec.
8. Remediate material findings within scope.
9. Return one reviewable implementation commit and a candid implementation report.

The implementation report must name the strongest and weakest parts, possible false greens, authority/caller influence, architecture coupling, deferred findings, and anything the Steward should independently verify.

No Writer may push, authorize Product choices, use credentials, call paid/network providers, mutate production state, or expand into a new ticket unless separately authorized.

---

## Upstream core

Implement the work described by the user in the accepted spec or ticket under the Desk rules above.

Use /tdd where possible, at pre-agreed seams.

Run typechecking regularly, single test files regularly, and the full ticket-appropriate suite/checks at the end.

Once done, use /code-review to review the work.

Commit the bounded implementation to the assigned branch/worktree; never push autonomously.
