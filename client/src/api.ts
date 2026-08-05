/** Thin fetch wrappers for governed `/api` operations only. */

export type DeskRefusalBody = {
  refusal: {
    code: string;
    what_happened: string;
    what_was_preserved: string;
    what_was_not_changed: string;
    what_you_can_do: string;
  };
};

async function parseJson<T>(response: Response): Promise<T> {
  const data: unknown = await response.json();
  if (!response.ok) {
    const refusal = data as DeskRefusalBody;
    if (refusal && typeof refusal === "object" && "refusal" in refusal) {
      throw new Error(
        `${refusal.refusal.code}: ${refusal.refusal.what_happened} — ${refusal.refusal.what_you_can_do}`,
      );
    }
    throw new Error(`HTTP ${response.status}`);
  }
  return data as T;
}

// --- Case ---

export type CaseRecord = {
  case_id: number;
  title: string;
  created_at: string;
};

export type SuspensionRecord = {
  suspension_id: number;
  run_id: number;
  ordinal: number;
  question: string;
  uncertainty: string;
  default_action: string;
  suspended_at: string;
  human_answer?: string | null;
  answered_at?: string | null;
};

export type RunRecord = {
  run_id: number;
  case_id: number;
  status: string;
  question: string;
  scope: string;
  rubric_version: string;
  rubric_text: string;
  capture_budget?: number;
  captures_used?: number;
  created_at: string;
  updated_at: string;
  lease_expires_at?: string | null;
  suspension_question?: string | null;
  suspension_uncertainty?: string | null;
  suspension_default_action?: string | null;
  suspended_at?: string | null;
  human_answer?: string | null;
  answered_at?: string | null;
  suspensions?: SuspensionRecord[];
  instance_vs_class_notice?: string | null;
};

export type ClaimRecord = {
  claim_id: number;
  case_id: number;
  run_id: number;
  source_run_question: string;
  proposition: string;
  confirmation_status: string;
  source_basis: string;
  corroboration: string;
  certainty: string;
  posture: string;
  qualification: string;
  publication_risk: string;
  rubric_version: string;
  quote_bindings: Array<{
    capture_id: number;
    locator: string;
    quoted_text: string;
    ordinal: number;
  }>;
  cited_claim_ids: number[];
  created_at: string;
};

export type OpenQuestionRecord = {
  open_question_id: number;
  case_id: number;
  introduced_by_run_id: number;
  source_run_question: string;
  ordinal: number;
  proposed_text: string;
  rationale: string;
  proposed_scope: string;
  agenda_decision: string;
  disposition?: string | null;
  settled_text?: string | null;
  settled_scope?: string | null;
  created_at: string;
  decided_at?: string | null;
};

export type CaptureCloseRecord = {
  capture_id: number;
  run_id: number;
  url: string;
  status: string;
  created_at: string;
};

export type GetRunCloseResult = {
  run: RunRecord;
  agenda: OpenQuestionRecord[];
  captures_count: number;
  claims_count: number;
  low_confidence_areas: string[];
  claims: ClaimRecord[];
  captures: CaptureCloseRecord[];
};

export type GetCaseResult = {
  case: CaseRecord;
  runs: RunRecord[];
  captures: string[];
  claims: ClaimRecord[];
  open_questions: OpenQuestionRecord[];
  angles: string[];
  renditions: string[];
};

export async function createCase(title: string): Promise<CaseRecord> {
  const response = await fetch("/api/cases", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  return parseJson<CaseRecord>(response);
}

export async function listCases(): Promise<{ cases: CaseRecord[] }> {
  const response = await fetch("/api/cases");
  return parseJson<{ cases: CaseRecord[] }>(response);
}

export async function getCase(caseId: number): Promise<GetCaseResult> {
  const response = await fetch(`/api/cases/${caseId}`);
  return parseJson<GetCaseResult>(response);
}

// --- Run ---

export async function createRun(
  caseId: number,
  question: string,
  scope: string,
): Promise<RunRecord> {
  const response = await fetch("/api/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ case_id: caseId, question, scope }),
  });
  return parseJson<RunRecord>(response);
}

export async function approveRun(runId: number): Promise<RunRecord> {
  const response = await fetch(`/api/runs/${runId}/approve`, { method: "POST" });
  return parseJson<RunRecord>(response);
}

export async function listRuns(
  caseId: number,
): Promise<{ case_id: number; runs: RunRecord[] }> {
  const response = await fetch(`/api/cases/${caseId}/runs`);
  return parseJson<{ case_id: number; runs: RunRecord[] }>(response);
}

export async function answerSuspendedRun(
  runId: number,
  answer: string,
): Promise<RunRecord> {
  const response = await fetch(`/api/runs/${runId}/answer-suspension`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ answer }),
  });
  return parseJson<RunRecord>(response);
}

export async function cancelRun(runId: number): Promise<RunRecord> {
  const response = await fetch(`/api/runs/${runId}/cancel`, { method: "POST" });
  return parseJson<RunRecord>(response);
}

export async function getRunClose(runId: number): Promise<GetRunCloseResult> {
  const response = await fetch(`/api/runs/${runId}/close`);
  return parseJson<GetRunCloseResult>(response);
}

export async function decideOpenQuestion(
  openQuestionId: number,
  decision: string,
  options: {
    disposition?: string;
    text?: string;
    scope?: string;
  } = {},
): Promise<OpenQuestionRecord> {
  const response = await fetch(`/api/open-questions/${openQuestionId}/decide`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      decision,
      disposition: options.disposition ?? null,
      text: options.text ?? null,
      scope: options.scope ?? null,
    }),
  });
  return parseJson<OpenQuestionRecord>(response);
}

export async function createOperatorOpenQuestion(
  runId: number,
  text: string,
  scope: string,
  disposition: string,
): Promise<OpenQuestionRecord> {
  const response = await fetch(`/api/runs/${runId}/open-questions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, scope, disposition }),
  });
  return parseJson<OpenQuestionRecord>(response);
}
