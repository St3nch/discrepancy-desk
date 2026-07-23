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

export interface VaultArtifactRow {
  id: string;
  sha256: string;
  byte_size: number;
  storage_relative_path: string;
  media_type_observed: string | null;
  created_at: string;
  acquisition_artifact_link_id: string;
  acquisition_id: string;
}

export interface VaultIntakeRecords {
  api_version: string;
  vault_id: string;
  acquisitions: Array<Record<string, unknown>>;
  artifacts: VaultArtifactRow[];
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
  package_count: number;
}


export interface VaultParserStatus {
  parser_definition_id: string;
  parser_configuration_version_id?: string;
  parser_admission_version_id?: string;
  parser_id: string;
  display_name: string;
  format_id?: string;
  state: string;
  canonical_available: boolean;
  admission_ready: boolean;
  admission_manifest?: Record<string, string> | null;
  reason_code: string | null;
  package_schema_version: string;
  security_profile_id: string;
}

export interface VaultParsersResponse {
  api_version: string;
  vault_id: string;
  parsers: VaultParserStatus[];
  canonical_parser_available: boolean;
}

export interface VaultTextAdmissionResult {
  api_version: string;
  vault_id: string;
  parser_admission_version_id: string;
  parser_definition_id: string;
  parser_configuration_version_id: string;
  state: "owner_admitted";
  canonical_available: boolean;
  replayed: boolean;
}

export interface VaultTextParseResult {
  api_version: string;
  vault_id: string;
  parser_execution_id: string;
  normalized_package_id: string | null;
  document_version_id: string | null;
  package_sha256: string | null;
  state: string;
  terminal_outcome: string;
  reused_package: boolean;
  reused_document: boolean;
  replayed: boolean;
}

export interface VaultDocumentSummary {
  document_version_id: string;
  acquisition_artifact_link_id: string;
  normalized_package_id: string;
  package_sha256: string;
  source_artifact_sha256: string;
  version_ordinal: number;
  state: string;
  parser_execution_id: string;
  parser_admission_version_id: string;
  terminal_outcome: string;
  created_at: string;
  element_count: number;
  region_count: number;
}

export interface VaultDocumentsResponse {
  api_version: string;
  vault_id: string;
  documents: VaultDocumentSummary[];
}
