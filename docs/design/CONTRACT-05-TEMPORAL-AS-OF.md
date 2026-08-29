# Foundation Contract 05 — Temporal / As-of Record

**Status:** NON-AUTHORITATIVE DESIGN DRAFT

**Depends on:** `FOUNDATION-MODEL-V2.md`, `CONTRACT-01-EVIDENCE.md`, `CONTRACT-02-CLAIM-DECISION.md`, `CONTRACT-03-IDENTITY.md`, `CONTRACT-04-BASIS-PROVENANCE.md`

**Purpose:** Define temporal meaning and historical reconstruction before schema work chooses timestamps, ranges, version tables, event sourcing, or PostgreSQL temporal constraints.

> **The past can be revised. The history of the Desk's understanding cannot be erased.**

---

# 1. Time is plural

The Desk must not collapse distinct temporal meanings into one generic `timestamp`.

Depending on the object and evidence, relevant clocks may include:

- **world time** — when something happened or was true in the world;
- **source-presented time** — the time or interval a source itself states or implies;
- **capture time** — when the Desk acquired the material;
- **Record admission time/order** — when and in what immutable governed visibility order structured material entered the Record;
- **decision time** — when the human made the Decision; this does not by itself determine when that Decision became visible/operative in the Record;
- **publication time** — when a Publication was actually emitted.

Not every object needs every clock.

The invariant is semantic:

> **Different clocks must never become interchangeable merely because they can all be represented as dates or timestamps.**

---

# 2. World time and Record time are different dimensions

The Desk must distinguish:

1. when something may have been true/effective in the world; and
2. when the Desk knew, admitted, resolved, or decided it.

Example:

```text
2025-03-01  event occurs
2025-03-04  source reports it
2025-03-10  Desk captures source
2025-03-11  Observation enters Record
```

A current Record may legitimately say the event occurred on March 1.

An as-of-March-5 Record view must not contain the Observation admitted on March 11 merely because its world-time subject predates the query.

Conceptually:

```text
effective_at != recorded_at
```

Those names are illustrative, not final schema vocabulary.

---

# 3. Meaning of `as_of`

An `as_of` Record read means:

> **Show the governed Record state visible at the corresponding immutable Record-admission boundary.**

It does **not** mean:

> apply today's best reconstruction to an older calendar date.

Example:

```text
world event: 2005
Desk learns evidence: 2028
```

An as-of-2026 Record view cannot contain the 2028 knowledge.

Human-supplied or domain `decision time` metadata does not backdate Record visibility. A Decision made offline at T1 but admitted to the Record at T2 becomes part of Record history at its T2 admission boundary, while preserving T1 as decision-time metadata.

The final physical mechanism must provide a system-assigned, immutable, deterministic admission ordering consistent with committed governed visibility. A wall-clock timestamp column alone is insufficient. Ordinary sequence allocation alone is also insufficient because allocation order is not necessarily commit order.

The exact PostgreSQL mechanism remains open and must be proven with concurrent transactions before schema promotion.

This is foundational to honest institutional memory.

---

# 4. Current reconstruction and historical understanding are separate questions

The Desk must support both:

```text
What does the Desk currently believe happened when?
```

and:

```text
What did the Desk believe as of time T?
```

Those answers may differ without contradiction in the system.

Example:

```text
2026: operative Claim says event occurred in 2005
2028: new evidence supports 2004
2028: human Decision supersedes the old posture
```

Current reconstruction may show 2004.

An as-of-2026 view must still show the then-operative 2005 understanding.

Later knowledge may revise the current model of the past. It may not falsify the history of what the Desk knew or decided.

---

# 5. Historical Decisions remain historically operative

Suppose:

```text
2027 D1: Claim C1 confirmed
2029 D9: D1 superseded; C1 now disputed/rejected/superseded
```

Current reads derive posture from the latest applicable Decision lineage.

An as-of-2028 read must still show the posture produced by D1.

The Desk does not mutate D1 to pretend it was never operative.

This does not require universal event sourcing. It requires enough append/version/supersession lineage to reconstruct governed historical state.

---

# 6. Source-presented chronology remains source-local

Conflicting chronology must not be normalized away at ingestion.

Example:

```text
Source A → Observation OA: Program X began in 2005
Source B → Observation OB: Program X began in 2006
```

The Record preserves both Observations.

The Desk may later create competing Claims and a human Decision about posture.

It must not create one canonical `start_date` at capture/Observation time merely because downstream software wants a single sortable value.

> **PostgreSQL may validate chronology. PostgreSQL does not decide disputed history.**

---

# 7. Temporal precision and uncertainty are first-class semantics

The Desk must preserve the difference among temporal forms such as:

- exact instant;
- exact date;
- month;
- year;
- bounded interval;
- open interval;
- approximate period;
- before/after bound;
- unknown.

Examples such as:

```text
"around 2004"
"early 2004"
"before June 2005"
"between 2003 and 2006"
```

must not be coerced into false exact dates.

The evidence chain preserves the exact source wording.

A structured temporal interpretation may additionally encode queryable semantics, but that interpretation is distinct from the quoted/source-presented value.

Illustrative only:

```text
source wording = "around 2004"
precision      = year
lower bound    = 2004-01-01
upper bound    = 2004-12-31
qualifier      = approximate
```

The exact physical temporal type system remains open.

---

# 8. Structured temporal interpretation is an interpretation

Turning source wording into a structured interval is analytical work.

It must remain possible to trace:

```text
structured temporal value
        ↓
source-local Observation
        ↓
Excerpt / Locator / Surface / Artifact
```

A machine-readable range must not silently replace what the source actually said.

If interpretation is ambiguous or materially consequential, the system may need a Notice, Claim, Decision, or explicit review step rather than treating normalization as clerical parsing.

---

# 9. Temporal inference must remain explicit

The Desk may infer temporal bounds from multiple governed facts, but it must not rewrite the originating Observations.

Example:

```text
O1: Person P is employed by Acme in May 2005
O2: Person P is documented elsewhere by September 2005
```

The system may propose:

> employment likely ended sometime between May and September 2005.

That is a new analytical proposition or candidate, not a hidden completion of a missing `end_date`.

Conceptually:

```text
O1 + O2
  ↓ explicit Basis
Claim / Notice with inferred temporal bounds
```

Inference provenance follows Contract 04.

---

# 10. Open intervals are legal

Unknown or unproven interval endpoints must remain open.

Example:

```text
"served as director beginning in 2019"
```

may support:

```text
start known
end unknown/open
```

Do not synthesize a fake end such as `present`.

The Record must distinguish:

- no end is known;
- a source explicitly says the role is current;
- a source said `current` at some historical source/capture context;
- later evidence proves an end.

Those are different statements.

---

# 11. `Present` is contextual, never timeless

A historical source saying `currently`, `presently`, `now`, or equivalent is relative to that source's temporal context.

Example:

```text
2024 page: "Jane Doe currently serves as director."
2026 capture of that page
```

The Observation must not be interpreted as proof that Jane Doe is still director in 2026.

Preserve the source wording and the best available context for what `currently` referred to.

Historical present-tense language must never become an eternal open interval through convenience normalization.

---

# 12. Identity time follows the same dual-clock rule

Contract 03 requires identity Decisions to support historical reconstruction.

Example:

```text
2027: "R. Smith" unresolved
2028: Decision resolves occurrence/candidate to E17
```

Current Entity reads may expose the resolution.

An as-of-2027 read must still expose unresolved identity.

An identity relationship may also require world/effective temporal qualification where reality demands it, but that does not alter when the Desk made the resolution Decision.

---

# 13. Provenance targets historical state, not only current identity

Contract 04 requires durable governed dependencies to bind enough historical state to remain auditable.

For temporal reconstruction this means a later version or Decision cannot silently change what an earlier Publication depended on.

Conceptually:

```text
Publication P1
   ↓
Rendition Unit U6
   ↓
Claim C1 at operative historical state
   ↓
Basis operative at that time
```

Current Claim posture may later differ.

The Publication's historical provenance does not.

---

# 14. No universal versioning requirement

As-of reconstruction does **not** imply:

- event-source every table;
- add `version` columns indiscriminately;
- retain every cache state;
- use one temporal-table pattern for every noun;
- force every object through one generic history mechanism.

Different categories naturally support history differently:

- immutable Evidence already has historical identity;
- Claims may use explicit version/supersession lineage;
- Decisions are append-only/superseding authority acts;
- identity resolution is a Decision-derived projection;
- Publications are immutable historical snapshots;
- rebuildable projections may be recomputed from the applicable historical durable state;
- caches and transient rankings need no durable history unless they themselves become governed dependencies.

> **Historical reconstruction is a requirement. Universal temporal storage is not.**

---

# 15. PostgreSQL temporal capabilities are tools, not doctrine

PostgreSQL 18 ranges, constraints, indexes, generated values, and related features may help implement honest temporal queries.

They must not force the domain into fake certainty.

In particular:

- a range can represent a queryable interval but does not prove that its endpoints are known exactly;
- `WITHOUT OVERLAPS`, `PERIOD`, exclusion-style constraints, or similar mechanisms should be used only where the domain truly requires non-overlap;
- disputed or uncertain history must not be rejected merely because two intervals overlap;
- database constraints may validate internally asserted chronology, not decide which competing source is historically correct.

The project will select PostgreSQL temporal mechanisms only after the semantic contract is stable.

---

# 16. LLM temporal reads must name the time axis

LLM-native reads must not expose an ambiguous `date` field when multiple temporal meanings exist.

The read surface should make the query axis clear, for example conceptually:

```text
record_as_of = 2028-01-01
world_time_filter = 2004..2006
```

Those names are illustrative.

The model must be able to distinguish:

- filter the current Record by world/effective chronology;
- reconstruct the Record as it existed at a past time;
- combine both intentionally.

Temporal warnings and uncertainty should survive projection rather than disappearing into display formatting.

---

# 17. Worked proof

1. Capture A contains a source statement: Program X began in 2005.
2. Observation `O1` preserves that source-local chronology.
3. Capture B contains a different source statement: Program X began in 2006.
4. Observation `O2` preserves the conflict; neither Observation is normalized away.
5. Claim `C1` proposes 2005 with `O1` as Basis.
6. Claim `C2` proposes 2006 with `O2` as Basis.
7. Human Decision `D1` makes one posture operative in 2027 while preserving both Claims and counterevidence.
8. A Publication in 2027 binds the exact then-operative Claim/Rendition state.
9. In 2028, new evidence supports 2004.
10. A new Claim and human Decision `D9` supersede the prior operative posture.
11. Current world-time reconstruction may now show 2004.
12. An as-of-2027 Record read still reconstructs the earlier operative understanding.
13. The 2027 Publication still resolves to its exact historical provenance.
14. Reverse provenance can identify that Publication as potentially affected by the later correction.
15. No historical Observation, Decision, Claim version, or Publication is destructively rewritten.

If the physical design cannot perform this proof, the temporal/as-of contract has failed.

---

# 18. Open before ADR/schema promotion

1. Physical field/type representation for the frozen semantic clocks: world time, source-presented time, capture time, Record admission time/order, decision time, and publication time.
2. Exact `as_of` admission-order mechanism, time-to-admission-boundary mapping, inclusion convention, and concurrency proof.
3. Temporal precision/qualifier type system.
4. Physical representation of exact dates, partial dates, approximate periods, bounded ranges, and open ranges.
5. Whether structured temporal interpretations are stored directly on Observations, in typed supporting structures, or through another narrow mechanism.
6. Exact Claim version/supersession representation needed for historical reconstruction.
7. Historical identity cluster projection algorithm.
8. Current vs as-of LLM read envelope and query grammar.
9. Indexing strategy for combined Record-time and world-time traversal.
10. PostgreSQL 18 range/constraint features worth adopting after worked schema examples.
11. Rules for relative temporal words such as `current`, `today`, `recently`, `last year`, and source-relative dates.
12. How correction/takedown lineage interacts with public historical snapshots and public-safe projections.

---

# 19. Rejected shortcuts

- one generic timestamp for all temporal meanings;
- `as_of` driven solely by a mutable/backdatable wall-clock column;
- ordinary sequence allocation treated as proof of commit-ordered Record visibility;
- back-projecting later knowledge into earlier as-of Record state;
- overwriting old Decisions to make current history look clean;
- forcing one canonical chronology when sources disagree;
- coercing uncertain periods into exact dates;
- replacing exact source wording with normalized temporal interpretation;
- inferring missing end dates silently;
- treating historical `currently` as timeless present;
- treating world-time filtering and Record-as-of reconstruction as the same query;
- universal event sourcing merely because historical reads exist;
- universal temporal tables merely because PostgreSQL supports temporal helpers;
- database non-overlap constraints that erase legitimately disputed or uncertain history.

---

# 20. Contract test

The Temporal / As-of foundation is good enough only if all five are mechanically supportable:

> **The Desk can distinguish when something may have happened from when the Desk learned or decided it.**

> **Uncertain or conflicting chronology can remain uncertain or conflicting without forced normalization.**

> **A current reconstruction of the past may change while an earlier as-of Record view remains historically faithful.**

> **Publications and Decisions remain auditable against the exact temporal state that was operative when they were made.**

> **Historical reconstruction does not require turning the entire system into one universal event-sourced temporal database.**
