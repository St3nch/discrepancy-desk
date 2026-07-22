export interface DesktopHealth {
  api_version: string;
  service: string;
  status: "healthy" | "unhealthy";
  sqlite_integrity: string;
  migration: string;
}

export interface BackendSession {
  baseUrl: string;
  launchToken: string;
  apiVersion: string;
}

export interface OwnedAccount {
  id: string;
  platform: string;
  external_account_id: string;
  username: string | null;
}

export interface CommandCenterResponse {
  api_version: string;
  account_id: string;
  data: Record<string, Array<Record<string, unknown>>>;
}

export interface ScheduleRow {
  id: string;
  work_item_id: string;
  title: string;
  scheduled_for: string | null;
  lane: string;
  status: string;
}

export interface SystemStatus {
  api_version: string;
  status: string;
  sqlite_integrity: string;
  migration: string;
  counts: Record<string, number>;
}

export interface SourceRow {
  id: string;
  work_item_id: string;
  source_kind: string;
  locator: string | null;
  note_text: string | null;
}

export interface MetricRow {
  id: string;
  publication_id: string;
  captured_at: string;
  observation_state: string;
  metrics: Record<string, unknown>;
}

export interface VaultSummary {
  vault_id: string;
  display_name: string;
  relative_root: string;
  registry_state: string;
}

export interface VaultHealth {
  api_version: string;
  vault_id: string;
  status: "healthy" | "blocked";
  sqlite_integrity?: string;
  migration?: string;
  identity_fingerprint?: string;
  audit_chain?: string;
  reason?: string;
}
