# Review — Ticket 10 (coverage gauge and official-foundation gate)

**Date:** 2026-08-06
**Reviewers:** Claude (seam checks + steward) and GPT (spec), independently
**Verdict:** Accepted on both axes after three rounds. Shipped as `a93cdc8`; D20 as `272634d`
in the docs repo.

The longest ticket in the project. The first implementation was correct against its
acceptance criteria and measured the wrong thing; the criteria were rewritten mid-ticket and
D20 was written to settle the question the original ticket had left open.

---

## Standing checks (final state)

| Check | Result |
|---|---|
| Vocabulary reconciliation | **Clean.** `coverage_dimension` uses the nullable CHECK form and is covered bidirectionally by `test_check_enums.py`; readings validated in the models rather than listed in a comment |
| Fail-open inventory | **Clean** after F-41 and F-45 |
| Destructive-write inventory | **Clean.** Attestations insert; examined marking is guarded and rolls back with the transaction |
| Dead-capability inventory | **Clean** after F-44; the gate's deferred call site is an acceptance criterion on ticket 11 |
| Write-once inventory | **Clean.** `coverage_attestations` append-only, read latest-by-id |
| Projection completeness | **Clean** after F-44 |

Suite verified by the reviewer, not taken from the report: 145 passed at acceptance.

---

## Round one — the measurement was on the wrong axis

### F-37 / S-01 — `complete` was satisfiable by one capture and one claim

**Severity:** High. **Closed by redesign (D20).**

The first implementation derived `official_foundation` from case-wide activity: ≥1 capture,
≥1 claim, 0 unexamined. Capture one URL, propose one claim, and the gate opened permanently.
The system's one absolute rule fired only on near-empty cases.

Both axes found this independently and framed it differently, and the difference mattered.
The seam read was "the bar is too low." The spec read was sharper — **nothing bound the
activity to the dimension it claimed to evidence**, so a run working the public question
satisfied the official foundation. The ticket's own allowing test proved it: the claim's
`source_basis` was `contemporaneous_report`, ordinary research material.

A higher threshold would not have fixed it. The axis was wrong, not the magnitude.

**Resolution — D20.** The operator sets a coverage dimension on a run at dispatch; coverage
derives from real activity with correct attribution; `complete` is a human attestation with
actor and timestamp, because "the spine is complete" means "I have seen enough" and no count
expresses that. Four rejected alternatives are recorded there, including the two that look
most reasonable once implementation starts.

### F-38 — Attaching a lead silently closed the gate

**Severity:** Medium. **Closed as designed behaviour.**

`attach_lead` sets `captures.case_id`, and lead captures are `unexamined` by design (D18).
So attaching a lead to a case with a complete foundation dropped it to `worked` and
hard-blocked angle work, discoverable only at the worst moment.

Under D20 the same regression is visible, states its reason, and clears in one action.
Neither ticket was wrong alone; the interaction was nobody's decision until it was made one.

### F-39 — The coverage vocabulary was a comment, not a constraint

**Severity:** Medium. **Closed.** `COVERAGE_READINGS` and `COVERAGE_STAGE_IDS` had zero call
sites; `reading` was a bare `str` with the values in a trailing comment; the client carried
its own CSS classes. Three definitions, nothing reconciling them — the check F-10, F-21, and
F-30 each closed for a different enum, recurring where no CHECK constraint anchored it.

### S-02 — `unworked` claimed more than the Record could support

**Severity:** Medium. **Closed.** Found only on the spec axis. `public_question`,
`story_intelligence`, `editorial_development`, and `composition` all read `unworked` because
their tables did not exist. `unworked` asserts nobody worked the stage; the truth was that
nothing could record it — the F-32 distinction, absence of a record is not absence of
activity. The first implementation applied this correctly to `deep_context` and inconsistently
everywhere else.

---

## Round two — the rebuild

### F-41 / S-01 — The migration invented operator authority and left a live default

**Severity:** Blocking. **Closed.** `coverage_dimension TEXT NOT NULL DEFAULT
'official_foundation'` — two defects. `DEFAULT` is permanent, not a backfill, so any future
insert omitting the column silently receives the one dimension that opens the gate. And every
pre-existing run was classified as official-foundation work, letting old unrelated activity
satisfy the new gate.

Resolved as a nullable column with no default. `NULL` means "dispatched before D20; no
dimension was judged" and matches no stage filter. An `unclassified` sentinel was considered
and rejected — it would either pollute the six-stage vocabulary or add a seventh value that is
not a stage.

### F-42 — Attestation wrote a born-stale record instead of refusing

**Severity:** Medium-high. **Closed.** The docstring stated it plainly: attesting with
unexamined material present succeeded and left the reading at `worked`. The only governed
write in the codebase that succeeded while having no effect.

**This fix is what keeps the staleness rule simple**, and the reasoning is worth preserving.
The spec axis proposed binding attestations to a corpus revision so staleness could be
computed by comparison, with an attachment timestamp for leads. Refusing while unexamined
captures remain makes that unnecessary: the count is zero at the moment of attestation, so
*"any unexamined capture exists now"* and *"material arrived after the attestation"* become
the same statement. All four of the spec axis's proposed test cases pass on the simpler
invariant — including the lead captured before but attached after, which was the case said to
require the new timestamp.

**The wedge neither review caught until the fix was designed:** a strict refusal would make a
case with cancelled-run leftovers permanently unattestable, since `cancel_run` deliberately
leaves capture status alone — F-26's shape. Resolved by `examined_capture_ids` on attest, the
same vocabulary and the same act as `close_run`. F-32 requires `examined` to be reported
rather than inferred; a human reporting it is more authoritative than an executor, not less.

---

## Round three — the migration could not run

### F-45 / S-01 — `0013` could not upgrade a populated database

**Severity:** Blocking. **Closed.** Found on the spec axis by **building a populated `0012`
database and running the upgrade**, which failed at `DROP TABLE runs` with `FOREIGN KEY
constraint failed`. The seam reviewer read the same migration, confirmed its shape was
correct, and missed it entirely.

The finding is bigger than the migration. **Migration tests run against empty databases, so
foreign key enforcement never fires.** `0011` and `0012` also rebuild a table and were safe
only because nothing references `leads` — luck, not design. Every rebuild in this project had
been verified on the one path where the constraint is inert.

Resolved as an additive `ALTER TABLE ... ADD COLUMN` with a nullable CHECK, no rebuild on the
upgrade path, plus `tests/test_migration_0013_populated.py` seeding a case, run, capture,
claim, suspension, open question, and low-confidence row. `codingstandards.md` now carries the
rule.

### F-44 / S-02 — The browser could not clear what blocked attestation

**Severity:** Medium. **Closed.** Both attest buttons posted an empty
`examined_capture_ids`, so an operator with an attached lead or cancelled-run leftover hit
`COVERAGE_UNEXAMINED_REMAIN` with no route to the remedy D20 specifies. The API supported it;
the UI did not. Projection completeness failing exactly as the check describes — the form that
renders the decision could not make it.

**The implementer reported this against himself**, in the first report written under the new
observations convention: *"say that plainly rather than claim the loop is closed in the
browser."* The report could have said "acceptance met at the service seam" and been literally
true.

### F-46 — The pragma was set and never verified

**Severity:** Medium. **Closed.** `_sqlite_rebuild_drop_column` issued `PRAGMA
foreign_keys=OFF` without reading it back. SQLite ignores that pragma inside a transaction and
Alembic runs migrations in one, so the code could not tell whether enforcement was actually
off — `foreign_key_check` detects violations, not a pragma that never took. F-02's rule, in the
one place the codebase already had a written standard for it.

### F-47 — A name and a return type that no longer said what they meant

**Severity:** Low. **Closed.** `list_capture_summaries_for_case` returned structured records
rather than summaries, with a bare `-> list`. Noted at the time: that function feeds both
`get_case` and `read_case_context`, so a change made for a browser checkbox also changed the
executor-facing MCP payload. An improvement — the executor now receives capture ids directly
instead of parsing them from a formatted string — but a side effect rather than a decision, on
an external contract.

---

## What held

**`unmeasurable` as a first-class reading.** The easy move in round one was mapping
`source_basis` or run-scope text onto `deep_context` and calling it measured. The
implementation refused a proxy and said why. That refusal became the principle the entire
redesign rested on, and it is now doctrine in D20.

**One derivation shared by the gauge and the gate**, from the first implementation onward.
They cannot disagree, which is the drift class this project keeps finding.

**Attestations append-only, read latest-by-id.** Nobody asked for it. Third time the
history-is-never-the-projection pattern has held unprompted.

**The refusal text depends on a ticket 01 convention and gets it right** — stating that capture
statuses are unchanged *because the whole unit of work rolls back*, which is only true given
one transaction per service call.

**Checkboxes only on unexamined captures, no mark-all.** F-32's explicit-report rule preserved
at the UI layer, where a convenience button would have quietly re-created inference.

---

## Process notes

**Three rounds, and the ticket was rewritten mid-flight.** The original acceptance criteria
were satisfiable by an implementation that measured the wrong thing. That is a specification
failure, not an implementation one — the criteria said "based on real activity" without saying
activity *attributed to what*.

**The two axes found different blockers at every round**, and neither found the other's. Round
three is the clearest case: one reviewer executed and one read.

**The observations convention paid on first use.** Added to `AGENTS.md` before round three at
the operator's suggestion; the implementer's self-reported gap — that he had not run the
migration against a real populated database — named the exact hole the spec axis then proved.

**Steward practice changed as a result.** `workbench_run_command` executes `uv run pytest`;
ten tickets of review had been conducted by reading alone. Recorded in the steward handoff:
run things, do not only read them, and never report a test count that came from the
implementer.
