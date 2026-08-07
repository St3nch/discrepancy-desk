# 12a — Refusal invariant and quotation-surface lookup

**What to build:** Two pieces of executor reliability, both surfaced by the first live model
run. No product behaviour changes and no new governed decisions.

**Blocked by:** 12 — Rendition composition

**Status:** accepted

**Why before ticket 13:** both remove failure classes that Vela will hit harder than a seeded
case did. The live run survived one of them on luck and named the other as the item to fix
first.

---

## 1. The refusal contract becomes an invariant

The Desk's design claim is that it teaches its executor through refusals. A live run proved
both halves of that in one session: `QUOTE_MISMATCH` taught the quotation-surface model in
one shot and the executor recovered on the first retry, while `close_run` raised a bare
`'proposed_scope'` — a `KeyError` fragment with no envelope — which taught nothing and was
fixed by guessing.

An unstructured error escaping the tool layer is not a rough edge. It is the promise broken.

F-54 and F-58 patched two call sites. This makes it structural.

- [x] A wrapper at the MCP tool **dispatch** boundary catches anything that escapes
      (including framework argument validation) and returns a refusal envelope. Schemas
      stay intact — validation still runs; failures are converted on the way out.
- [x] **Three categories, not one.** (1) A `DeskRefusal` passes through unchanged —
      expected, actionable, remedy stated. (2) Framework argument validation failures
      become `TOOL_ARGUMENT_INVALID` — correctable, names the parameter and what was
      expected. (3) Anything genuinely unexpected becomes `TOOL_INTERNAL_ERROR` — not
      correctable by the caller, leaks no internals, loud in the logs.

      A blanket wrapper that dresses every failure as an actionable refusal is F-17 one
      level up. Treating a missing parameter as non-correctable is F-54 in a new costume —
      unlearnable feedback on a fixable mistake.
- [x] A test calls **every** tool through the **registered dispatch path** (not
      `tool.fn`) with malformed payloads — missing keys, wrong types, nulls, empty
      strings where an int is required — and asserts the envelope shape holds in every
      case. This is the test that would have caught F-54's description/schema drift as a
      class rather than an instance.
- [x] Tool descriptions and accepted schemas agree, asserted per tool. Two artifacts
      describing one contract with nothing checking them is now the third recurring defect
      shape in this project after F-51 and F-59.

## 2. `find_quote` — the vault becomes self-describing on quotation

A bare `e/{n}` locator means the quotation surface is the **entire element**, not text
findable within it. That is defensible design and it is learnable only by failing once. The
live executor then computed `e/1/r/0-473` by hand-counting characters in preformatted blocks,
and reported that it survived because RFC page headers happen to be exactly 72 columns wide,
which gave it a checksum.

That is luck. Vela's sources will not be so tidy.

- [x] An MCP read operation takes a capture id and a substring and returns the exact
      `e/{n}/r/{start}-{end}` locator, or a structured miss when the text is not present.
- [x] The miss is informative — not found at all, versus found in more than one element, are
      different situations and the executor can act on the difference.
- [x] Byte-exactness is unchanged. This is a lookup convenience; `propose_claim` still
      verifies independently, and nothing here weakens the quotation seam.
- [x] Read-only, no lease mutation, no budget cost.

**Scope guard:** this does not add fuzzy or approximate matching. Exact substring only. A
near-miss helper would put the system in the business of deciding what the executor meant,
which is the opposite of what the quotation seam is for.

---

**Origin:** F-54, F-55, F-58, and an outside review of the first live executor run. F-56
(classification vocabulary invisible to the executor) belongs to ticket 16 and is not in
scope here. F-57 (no vocabulary for cross-document corroboration) is deferred — see the
steward handoff.

---

## Comments

### Implementer report (ticket 12a)

**Suite:** 211 passing. Not committed — waiting on both review axes.

#### Round 2 — blocking fix (the layer the first pass missed)

Review correctly rejected body-only wrapping: `@server.tool` outside
`@mcp_tool_boundary` left MCP `FuncMetadata` validation outside the envelope,
and the suite called `tool.fn`, which bypasses exactly that layer.

- **`install_tool_dispatch_envelope`** patches `ToolManager.call_tool` after
  registration. Schema validation still runs inside `Tool.run`; failures convert
  on the way out. One place, all tools, schemas intact. (Did not loosen types.)
- **Three categories** (ticket correction accepted):
  1. Inner `ToolError` carrying our JSON envelope → re-raise clean (strips
     `Tool.run`'s `"Error executing tool…"` prefix). Domain codes and body-side
     `TOOL_INTERNAL_ERROR` both take this path.
  2. `__cause__` is pydantic `ValidationError` → **`TOOL_ARGUMENT_INVALID`** —
     actionable; names each `loc: msg (type=…)`; remedy says correct and retry.
  3. Anything else → **`TOOL_INTERNAL_ERROR`**, non-correctable, logged.
- Tests go through `await manager.call_tool(name, args, Context())` with
  missing required, wrong types, nulls, and empty-string-for-int across the
  tool surface; every case asserts five-field envelope and
  `TOOL_ARGUMENT_INVALID` (not internal). `claim_next_run` has no params —
  idle success + unexpected covered separately.
- Empty string for a `str` field remains a domain path (`FIND_QUOTE_EMPTY`) —
  schema accepts it; that is correct, not a hole in category 2.

#### Round 1 (still holds)

- Body `mcp_tool_boundary`; `parse_quote_binding`; description/schema agreement.
- `find_quote` as previously accepted: exact substring, unique region locator,
  informative misses (`not_found` / `multiple_elements` / `multiple_in_element`),
  `refresh_lease=False`, propose_claim still verifies independently, MCP-only.

#### Deliberate non-builds

- No fuzzy matching; no API for `find_quote`; no F-56/F-57.

#### Unease / notice

- **Live-executor smoke still not run.** Review asked to point a model at a
  deliberately wrong argument type once green. I have not done that in this
  session — only the automated dispatch suite. Worth doing before calling the
  ticket closed in production use.
- **`Tool.run` is not patched; `ToolManager.call_tool` is.** HTTP MCP goes
  through `MCPServer.call_tool` → manager, so the live path is covered. A test
  or future code that invokes `tool.run` directly still sees the double-wrapped
  framework message. The suite uses the manager path intentionally.
- Multi-in-element reason and shared read-authority helper unchanged from round 1.

#### Criteria

| Criterion | Delivered? |
|---|---|
| Dispatch intercept (schemas intact) | Yes |
| Three categories (domain / arg invalid / internal) | Yes |
| Envelope via real registered path | Yes |
| Description/schema agreement | Yes |
| find_quote (accepted as built) | Yes |
| Live wrong-type smoke with a model | **Not done** |
