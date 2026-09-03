# Discrepancy Desk Context

Canonical vocabulary for the current Discrepancy Desk rebuild. Keep this file concise: it names durable domain concepts, not implementation details or every possible future feature.

## Investigation and working material

**File**:
The durable investigation and scope of attention around one subject. The Foundation Model's term **Case** refers to this same object; File is the canonical operator/public product name and must not be implemented as a second object beside Case.
_Avoid_: Case as a separate domain object, dossier

**File ID**:
The durable public/tool-facing identifier for a File, using a domain-neutral form such as `DD-7225`. The filing number is non-semantic and non-sequential: it does not encode creation order, archive size, Domain, priority, truth, or another investigative judgment. Internal storage identity and honest creation/admission/revision metadata remain separate.
_Avoid_: domain-coded identity such as `QANON-0001`, sequential allocation presented as archive order, inferring archive size from a File ID

**Domain**:
A broad subject area used for classification and navigation, such as UFO/UAP or QAnon. A File may relate to more than one Domain without changing identity.
_Avoid_: category as truth, belief camp

**Workspace**:
Ordinary working material such as notes, leads, questions, todos, snippets, hypotheses, and story ideas. Workspace material is not investigative Record merely because it was written down.
_Avoid_: treating notes as Evidence or Observations

## Evidence and Record

**Vault**:
The authority for preserved evidence payloads and immutable acquired material. Structured Record state may refer to the Vault but does not replace payload authority.

**Evidence**:
Preserved source material whose exact version and acquisition provenance can be verified. Evidence can show what a source contains or presents; it does not automatically prove a world-fact Claim.
_Avoid_: model summary as evidence, citation without preserved material, source assertion as universal truth

**Capture**:
A governed acquisition act and receipt for external material. Recapturing later creates a new Capture/version; it never overwrites the earlier acquisition.

**Artifact**:
Immutable acquired bytes or material preserved by the Vault. An Artifact may be an access copy several generations from the originating object; it is authoritative relative to Desk-derived Surfaces, while Capture provenance must state rather than conceal its custody and generational limits.

**Surface**:
A frozen, versioned representation of an Artifact used for inspection and citation. It retains producing-method and payload-integrity provenance plus exact Artifact lineage. A better extractor creates a new Surface rather than mutating an old citation target.

**Locator**:
A durable address into one exact Artifact/Surface version.

**Excerpt**:
Exact bounded evidence selected through a Locator. An Excerpt proves what material is present, not whether the proposition is true.

**Observation**:
A source-local structured statement of what preserved evidence presents.
_Avoid_: fact, finding, conclusion

**Record**:
Durable institutional investigative state: captured evidence relationships, Observations, Claims, Decisions, provenance, governed Runs, and other admitted/versioned state. Workspace is outside the Record until a governed operation admits something into it.

**Claim**:
A durable Desk-level proposition. Evidence may support or contradict a Claim; an Observation does not silently make the Claim true.

**Decision**:
An explicit human-authority event acting on an exact durable target/version. A model may propose material for review but cannot create a human Decision.

**Notice**:
A durable candidate-attention envelope that says “look here,” not “believe this.” Notice disposition is not Claim posture.
_Avoid_: Analyst Finding as a truth conclusion

**Discrepancy**:
A File-scoped durable handle for something in the available Record that does not fit cleanly and therefore deserves investigation. It points to relevant Record material and carries minimal lifecycle/history; it is not a second truth-bearing Record object.
_Avoid_: proof of conspiracy, truth score, global discrepancy graph

**Discrepancy ID**:
A stable identifier scoped to one File, such as `D01` within `DD-7225`.

## Work, presentation, and publication

**Run**:
Bounded machine work with explicit mode, scope, provenance, and authority. A Run is not a persistent autonomous agent identity and cannot escalate its own authority.

**Rendition**:
A presentation artifact derived from a File and its governed Record for a particular audience/platform/format. A Rendition does not become a new investigation.

**Publication**:
An immutable historical event/snapshot of exact human-authorized public content. Later Record or File changes do not silently rewrite prior Publications.

**Living File report**:
The current canonical projection of what the Desk presently understands about a File. It may change through governed lineage while prior public revisions remain immutable.

**Material public change**:
A change to factual assertion, assessment, discrepancy status, meaningful context, or correction. Material changes require human re-authorization of the exact public content; uncertainty about materiality defaults to material.

**Non-material public change**:
A typo, punctuation, formatting, broken-link, or obvious copy edit that does not change meaning. It still leaves revision history but need not trigger clearance theater.

**Quinton Clearance**:
The fictional public-facing clerk/presenter. The Desk investigates; Quinton presents the files. “Filing” is presentation language and never grants Capture, Observation, Claim, Decision, or Notice-disposition authority.
