# 16 — Rubric artifacts

**What to build:** Rubrics as versioned files in the repository, selected by version at
dispatch, instead of free text typed into `create_run`.

The plumbing already exists — `runs.rubric_version`, `runs.rubric_text`, `claims.rubric_version`,
and both fields returned by `claim_next_run` and `read_case_context`. What is missing is the
artifact. Today an operator pastes rubric text per run, so "which claims came from which
guidance" is only answerable if he happened to paste consistently.

**Why now:** D9 makes rubrics versioned repository artifacts and says a rubric change never
applies retroactively. That is unenforceable while the text is per-run free entry. The Vela
run is the first time claims will be produced at volume, and rebinding them afterwards is
not possible — a claim records the version that made it, or the record is wrong forever.

**Blocked by:** 03 — Run dispatch and claim

**Status:** not started

- [ ] Rubrics live as files in the code repository, one per operation — reading a source,
      extracting a claim, working the public question, proposing an angle, closing a run
      (D9). Per operation, never per stage.
- [ ] Each carries an explicit version. A change means a new version; existing claims stay
      bound to the version that produced them.
- [ ] `create_run` selects a rubric version rather than accepting arbitrary text. The text
      stored on the run is read from the artifact, so the run records exactly what the
      executor was given.
- [ ] The stored `rubric_text` remains a snapshot on the run — editing a rubric file must
      not change what a past run is recorded as having used.
- [ ] A first draft exists for each operation, seeded from the indicative questions in
      VISION §10. Short. These are tuned against real output, not written to completeness
      in advance.
- [ ] **The classification vocabulary ships inside the work packet.** The `source_basis`,
      `certainty`, `posture`, `publication_risk`, and `corroboration` enums, each with a
      one-line meaning, live in the rubric text that `claim_next_run` already returns.

      Origin is F-56: the first live executor classified claims by pattern-matching two
      previously confirmed claims on the same case, and recorded in its low-confidence areas
      that its classifications were pattern-matched rather than rubric-driven. That means
      classifications propagate from case history rather than from the contract, and a fresh
      case has no history to pattern-match against — the executor would be probing blind
      against fail-closed validation.
- [ ] **One canonical worked example claim** ships with the extraction rubric, so cold-start
      behaviour does not depend on what any operator happened to confirm earlier.
- [ ] The operator can see which rubric version a claim came from.

**Explicitly out of scope:** a rubric editor in the browser, cross-version comparison views,
and classification-distribution reporting. Those are the drift-visibility features (D9) and
they want real claim volume to be worth building. Note them; do not build them.

**Scope guard:** VISION says rubric text is tuned against output rather than written in
advance — *first draft after the first run, not before*. This ticket builds the mechanism and
seeds a thin v1. Resist writing polished rubrics here; that work belongs after Vela, when
there is output to tune against.
