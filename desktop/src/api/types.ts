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


export interface VaultIntakeStart {
  api_version: string;
  status: "ready_for_upload" | "recorded" | "rejected";
  result_id: string;
  acquisition_id: string | null;
  upload_authorization_id: string | null;
  reason_code: string | null;
}

export interface VaultArtifactAdmission {
  api_version: string;
  acquisition_id: string;
  artifact_id: string;
  sha256: string;
  byte_size: number;
  storage_relative_path: string;
  reused_existing: boolean;
}

export interface VaultIntakeRecords {
  api_version: string;
  vault_id: string;
  acquisitions: Array<Record<string, unknown>>;
  artifacts: Array<Record<string, unknown>>;
  rejections: Array<Record<string, unknown>>;
}

export interface VaultBackupResult {
  api_version: string;
  vault_id: string;
  generation_id: string;
  manifest_sha256: string;
}

export interface VaultBackupVerification {
  api_version: string;
  vault_id: string;
  generation_id: string;
  status: "verified";
  manifest_sha256: string;
  artifact_count: number;
}
