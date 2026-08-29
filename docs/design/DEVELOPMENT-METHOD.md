# Discrepancy Desk — Development Method

**Status:** NON-AUTHORITATIVE DESIGN DRAFT

**Purpose:** Adapt the current Matt Pocock engineering skills and the proven Observatory workflow into a Desk-specific development method before project authority and implementation are finalized.

This file is workshop/process material. It does not become project authority merely by being committed.

---

# 1. Method principle

The Desk should not copy another project's process wholesale and should not blindly subscribe to upstream skill behavior.

Use three inputs:

```text
current upstream Matt Pocock skills
              +
proven VedaOps/Observatory adaptations
              +
the actual needs and authority model of this project
              ↓
Discrepancy Desk development method
```

> **Upstream is an input to review, not an instruction to upgrade.**

Project-local skill copies are the executable development method for the Desk. Upstream provenance is retained separately so updates can be reviewed deliberately.

---

# 2. Current upstream observations

At Desk bootstrap, the current `mattpocock/skills` repository presents a composable engineering chain centered on:

```text
grill-with-docs
  → to-spec
  → to-tickets
  → implement
  → tdd
  → code-review
```

Important current upstream behavior:

- `grill-with-docs` relies on `grilling` and `domain-modeling`; install all three together.
- `domain-modeling` treats `CONTEXT.md` as the project's concise ubiquitous-language glossary and uses ADRs only for hard-to-reverse, surprising, real trade-offs.
- `to-spec` assumes alignment is already complete and synthesizes rather than reopening the interview.
- `to-tickets` favors tracer-bullet vertical slices with explicit blocking edges.
- `implement` expects pre-agreed seams, TDD where appropriate, regular static/test feedback, review, and a commit.
- current upstream also includes useful newer engineering helpers not present in the older Observatory installation, including `ask-matt`, `improve-codebase-architecture`, `resolving-merge-conflicts`, and `wizard`.

The upstream catalog evolves. Re-run an upstream review at project bootstrap and before any deliberate skill refresh.

---

# 3. Lessons carried from Observatory

Observatory proved several workflow adaptations worth retaining because they protect authority and reduce agent drift:

1. **Project-local skills override generic/plugin copies.**
2. **Skill output is working input, not project authority.**
3. **The Project Steward reconciles vocabulary, architecture, and decisions before they become authority.**
4. **Implementation starts from an exact clean commit.**
5. **One accepted ticket has one designated Writer.**
6. **A ticket receives read-only adversarial review before implementation.**
7. **Questions with Product consequences are resolved before the implementation prompt.**
8. **The handoff between lanes is a commit, not an uncommitted working tree.**
9. **Upstream installer lock/provenance data is not the place for local policy.** Local adaptations live in the checked-in skill files and Git history.
10. **Future skill updates must be reviewed; never blindly overwrite adapted project-local copies.**

Observatory-specific product doctrine is explicitly not inherited.

Do not import:

- DataForSEO/provider rules;
- Observatory's Evidence-store authority model;
- disposable-PostgreSQL assumptions;
- Observatory's prohibition on `CONTEXT.md`;
- Observatory-specific provider/network/spend gates;
- its exact vocabulary, ticket prefixes, commands, or API boundaries.

---

# 4. Desk-specific authority direction

The eventual authority hierarchy is still being finalized by Foundation Model v2. Current design direction is:

```text
VISION.md
CONTEXT.md
AGENTS.md
ADRs / accepted specs / accepted tickets
```

Until those files are accepted, `docs/design/` remains non-authoritative workshop material.

For the Desk specifically:

- `CONTEXT.md` is expected to become the concise canonical domain glossary once Foundation Model v2 terminology is reconciled.
- PostgreSQL 18 is intended to hold the authoritative structured Record; Vault/evidence payload authority is a distinct concern. Do not import Observatory's disposable-PostgreSQL doctrine.
- skills may propose glossary entries, ADRs, specs, tickets, and implementation changes; they cannot promote their own output to authority.
- CHAZ remains Product Owner/final human authority.
- GPT is Project Steward/reviewer unless explicitly changed.
- a designated Writer implements accepted tickets; no ticket means no implementation.
- no push without explicit CHAZ authorization.

---

# 5. Approved project-local skill set — initial Desk set

Install/adapt these project-local Grok skills under `.grok/skills/`:

## Alignment and domain

- `setup-matt-pocock-skills`
- `ask-matt`
- `grill-with-docs`
- `grilling`
- `domain-modeling`
- `wait-what`
- `writing-for-agents`

## Planning and decomposition

- `to-spec`
- `to-tickets`
- `wayfinder`
- `prototype`
- `research`

## Implementation and quality

- `implement`
- `tdd`
- `code-review`
- `diagnosing-bugs`
- `codebase-design`
- `improve-codebase-architecture`
- `resolving-merge-conflicts`

## Operator / continuity

- `handoff`
- `wizard`

This is intentionally a bounded set, not the entire upstream catalog.

### Deliberately not admitted yet

- `triage` — Desk tickets are currently expected to remain governed repository artifacts rather than a GitHub-label state machine.
- `teach` — useful generally, not part of the development control plane.
- `grill-me` — `grill-with-docs` plus its dependency skills covers the project-design path.
- `to-questionnaire` — may be added if asynchronous Product/reviewer questionnaires become a recurring need.
- other current/future upstream skills — evaluate when a concrete Desk need appears.

---

# 6. Desk skill adaptation rules

Every project-local Desk skill should preserve upstream intent while adding only the smallest project-specific rules needed for governance.

## Common preflight

Where practical, adapted skills should:

1. identify the exact project-local `SKILL.md` being used;
2. read current Desk authority relevant to the task;
3. distinguish accepted authority from `docs/design/` workshop material;
4. use canonical `CONTEXT.md` vocabulary once it exists;
5. surface conflicts rather than silently overriding authority;
6. remain inside the role/ticket/write boundary;
7. avoid provider/network/credential/spend or production actions unless separately authorized;
8. never push.

## `setup-matt-pocock-skills`

Desk mode should be validation/reconciliation oriented, not generic scaffolding.

It should confirm the approved local skill set and current project layout. It must not blindly create `docs/agents/`, a triage label system, or an issue tracker merely because upstream defaults to them.

If later Desk workflow deliberately adopts GitHub Issues or another tracker, change that decision explicitly and then reconcile the skill.

## `grill-with-docs` + `domain-modeling`

These are the primary Foundation Model v2 tools.

During the foundation phase they should:

- grill the design against the current foundation contracts and actual worked examples;
- propose precise canonical nouns and avoided synonyms;
- stress-test boundaries and edge cases;
- identify genuine ADR candidates;
- keep proposals in non-authoritative design material until Steward reconciliation.

Once `CONTEXT.md` is accepted, resolved vocabulary may be reconciled there by the Steward rather than the skill autonomously rewriting authority.

## `to-spec`

Do not publish directly to an external issue tracker by default.

Desk flow:

```text
accepted/reconciled design
      ↓
to-spec synthesis
      ↓
non-authoritative draft spec
      ↓
Steward review
      ↓
accepted normative spec only when needed
```

Do not re-interview settled Product choices.

## `to-tickets`

Produce tracer-bullet vertical slices with explicit dependencies and observable acceptance behavior.

The Steward files/accepts the durable ticket. Generated ticket text is a proposal until reconciled.

## `implement`

Desk implementation begins only from:

- a final accepted ticket;
- a named exact start commit;
- a clean worktree;
- one designated Writer.

The Writer does not alter Product authority merely to make implementation convenient and does not broaden scope because adjacent work is interesting.

Use TDD at pre-agreed seams when meaningful, run bounded feedback throughout, run the ticket-appropriate final checks, use code review, and return one reviewable implementation commit.

## `code-review`

Preserve Pocock's independent Standards and Spec axes, augmented by Desk seam checks when applicable:

1. vocabulary reconciliation;
2. fail-open inventory;
3. destructive-write inventory;
4. dead-capability inventory;
5. write-once/lineage inventory;
6. projection / read-path completeness.

The implementer's report is evidence, not the only review source.

## `research`

Development research should prefer high-trust primary sources and preserve citations in working material when findings affect design.

Research does not authorize paid providers, credential use, production changes, or external publishing.

## `wizard`

Use when a human must perform infrastructure, credential, provisioning, backup/restore, dashboard, or one-off cutover steps that cannot be safely executed through governed tools.

Generated operator steps should be bounded, auditable, and explicit about irreversible actions.

## `improve-codebase-architecture`

Use only after enough implementation exists to make a codebase survey meaningful. It proposes deepening/refactoring candidates; it does not create standing permission to refactor outside a ticket.

---

# 7. Main Desk development chain

Current proposed chain:

```text
grill-with-docs
      ↓
Steward reconciliation
      ↓
to-spec, when an implementation contract is needed
      ↓
Steward acceptance
      ↓
to-tickets
      ↓
Steward drafts bounded ticket
      ↓
designated Writer performs read-only adversarial pre-implementation review
      ↓
Steward reconciliation + final ticket acceptance
      ↓
exact clean start commit
      ↓
implement → tdd → code-review
      ↓
Writer implementation commit / report
      ↓
Steward independent review
      ↓
CHAZ final validation / release / push gate
```

Not every change needs every ceremony. Use the smallest chain that protects the consequence of the change.

---

# 8. Question-resolution gate

Before a major implementation prompt when material uncertainty exists:

1. the designated Writer inspects the actual authority/code and returns bounded technical questions without mutation;
2. the Steward independently verifies premises and separates technical questions from Product decisions;
3. CHAZ resolves Product choices;
4. the Writer may explain technical consequences when useful without reopening settled Product direction;
5. the Steward reconciles the answer into authority/work boundary before issuing the implementation prompt.

Do not repeatedly regenerate large prompts while unresolved decisions remain embedded inside them.

---

# 9. Update policy for Pocock skills

The project must expect upstream evolution.

At minimum, check current upstream:

- when starting a new VedaOps project;
- before the first skill installation in an existing project;
- before a deliberate skills refresh;
- when a workflow problem suggests upstream may already have addressed it;
- occasionally at major project milestones, not continuously for novelty.

Update process:

```text
inspect current upstream
      ↓
compare with checked-in Desk adaptation
      ↓
identify behavioral changes/new dependencies/new skills
      ↓
decide whether they help this project
      ↓
port useful changes deliberately
      ↓
review diff
      ↓
commit adaptation
```

Never run an update that blindly replaces adapted skill files.

`skills-lock.json`, if produced by the installer, remains installer/upstream provenance only. Do not invent private fields in its schema to store Desk policy.

Git history is the record of local adaptation.

---

# 10. Future reusable VedaOps project starter

After the Desk workflow is proven, extract the common method shared by Observatory and the Desk into a reusable project-start document.

That future document should explicitly require:

- live VedaOps capability inspection rather than assumptions from an older project;
- current upstream Pocock skill review;
- comparison with prior VedaOps adaptations;
- project-specific authority/storage/security decisions;
- deliberate skill selection and dependency checks;
- local adaptation review rather than blind copying;
- explicit update policy.

Do not write that generic starter yet. Finish proving the Desk method first.

---

# 11. Immediate next proof

After the project-local skills are installed and adapted, use the resulting Desk `grill-with-docs` + `domain-modeling` workflow against **Foundation Contract 03 — Identity**.

The workflow passes its first calibration only if it materially improves the reversible-identity model without creating noun sprawl or silently promoting proposals to authority.
