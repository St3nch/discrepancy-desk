# 10a — Registration guard and interaction tests

**What to build:** Two pieces of enforcement that were assumed to exist and do not. No
product behaviour changes.

**Blocked by:** 10 — Coverage gauge and official-foundation gate

**Status:** implemented — awaiting review (not committed)

**Why before ticket 11:** the Angle Room adds the densest set of seams in the project —
angles link to claims, claims bind to captures, captures belong to runs or leads, and
confirmation touches all of it. Testing the pairs that exist now is cheaper than testing
them after that lands, and the guard should be real before more operations are registered.

---

## Close F-03 — open since ticket 01

`api_operation_names()` has no call site. `mcp_tools.py` verifies registered tools against
`mcp_tool_names()` at startup and raises on mismatch; the API transport has no equivalent.

The safety-critical direction holds — a human-authority operation appearing on MCP fails the
app at startup. What is unenforced is the other side: nothing detects an API route added for
an operation absent from `wiring.py`, or an `API_ONLY` entry with no route. `API_ONLY` is now
sixteen entries of registry that constrains nothing.

- [x] Either a test asserting every registered API route maps to a name in
      `api_operation_names()` **and** every name has a route, or `api_operation_names()` is
      deleted. An unused registry that looks enforced is worse than none — the next reader
      assumes it fires.
- [x] If kept, the check names the offending operation, not just that counts differ.

## Cross-operation interaction tests

Every defect that has broken this project has been *operation A changes what operation B
reports*, and not one was caught by a test:

| Finding | Shape |
|---|---|
| F-07 | `list_cases` scoped, `get_case` not |
| F-25b | Two executors holding one run |
| F-34 | `close_run` could not see attached lead captures |
| F-38 | Attaching a lead silently closed the coverage gate |

Each layer's tests were green in every case. That is the sentence in `codingstandards.md`
describing how the previous build failed.

- [x] A deliberate handful of tests that run two governed operations in sequence and assert
      what the **second** reports. Not a sweep — pairs where one operation writes state
      another reads.
- [x] Cover at least: attach a lead then close a run reporting that capture examined; attest
      coverage then attach a lead then read the gauge; cancel a run then read its captures'
      status; propose a claim against an attached lead capture then read the case; suspend
      and resume a run then read case context.
- [x] They live where a reader will find them as a class — one file, named for what they
      are — with a docstring saying why they exist and that adding a governed operation
      means adding a pair here.

**Scope guard:** this is not a coverage-percentage exercise. Ten to fifteen tests that cross
real seams are worth more than a hundred that re-test single functions with different
fixtures. If a pair has no state interaction, do not write it.
