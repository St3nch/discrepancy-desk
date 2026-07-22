import { invoke } from "@tauri-apps/api/core";
import type {
  BackendSession,
  CommandCenterResponse,
  DesktopHealth,
  MetricRow,
  OwnedAccount,
  ScheduleRow,
  SourceRow,
  SystemStatus,
  VaultArtifactAdmission,
  VaultBackupResult,
  VaultBackupVerification,
  VaultHealth,
  VaultIntakeRecords,
  VaultIntakeStart,
  VaultSummary,
} from "./types";

let session: BackendSession | null = null;

async function getSession(): Promise<BackendSession> {
  if (session === null) session = await invoke<BackendSession>("backend_session");
  return session;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const current = await getSession();
  const headers = new Headers(init?.headers ?? {});
  headers.set("x-discrepancy-desk-token", current.launchToken);
  if (!(init?.body instanceof FormData) && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }
  const response = await fetch(`${current.baseUrl}${path}`, {
    ...init,
    headers,
  });
  const payload = await response
    .json()
    .catch(() => ({ message: "Backend request refused" }));
  if (!response.ok) throw new Error(payload.message ?? "Backend request refused");
  return payload as T;
}

export const operationKey = (name: string) =>
  `desktop:${name}:${crypto.randomUUID()}`;

export const desktopClient = {
  health: () => request<DesktopHealth>("/desktop-api/v1/health"),
  system: () => request<SystemStatus>("/desktop-api/v1/system"),
  accounts: async () =>
    (await request<{ accounts: OwnedAccount[] }>("/desktop-api/v1/accounts")).accounts,
  vaults: async () =>
    (await request<{ vaults: VaultSummary[] }>("/desktop-api/v1/vaults")).vaults,
  vaultHealth: (vaultId: string) =>
    request<VaultHealth>(
      `/desktop-api/v1/vaults/${encodeURIComponent(vaultId)}/health`,
    ),
  createVault: (displayName: string, relativeRoot: string) =>
    request<{ vault_id: string }>("/desktop-api/v1/vaults", {
      method: "POST",
      body: JSON.stringify({
        display_name: displayName,
        relative_root: relativeRoot,
        owned_account_ids: [],
        operation_key: operationKey("vault-create"),
      }),
    }),
  migrateVault: (vaultId: string) =>
    request<{ vault_id: string; migration: string }>(
      `/desktop-api/v1/vaults/${encodeURIComponent(vaultId)}/migrate`,
      {
        method: "POST",
        body: JSON.stringify({ operation_key: operationKey("vault-migrate") }),
      },
    ),
  startVaultIntake: (
    vaultId: string,
    input: {
      sourceKind: "manual_file" | "manual_locator" | "manual_note";
      descriptorClass: "file" | "locator" | "note" | "none";
      displayLabel: string;
      locator?: string;
      platformLabel?: string;
      retentionClassification:
        | "preservation_compatible"
        | "timed_deletion_required"
        | "unknown";
      policyBasisReference: string;
      humanClassificationNote: string;
      expectsBytes: boolean;
      suppliedFilename?: string;
      suppliedMediaType?: string;
      advisoryByteSize?: number;
    },
  ) =>
    request<VaultIntakeStart>(
      `/desktop-api/v1/vaults/${encodeURIComponent(vaultId)}/intake`,
      {
        method: "POST",
        body: JSON.stringify({
          source_kind: input.sourceKind,
          descriptor_class: input.descriptorClass,
          display_label: input.displayLabel,
          locator: input.locator,
          platform_label: input.platformLabel,
          retention_classification: input.retentionClassification,
          policy_basis_reference: input.policyBasisReference,
          human_classification_note: input.humanClassificationNote,
          client_nonce: crypto.randomUUID(),
          operation_key: operationKey("vault-intake"),
          expects_bytes: input.expectsBytes,
          supplied_filename: input.suppliedFilename,
          supplied_media_type: input.suppliedMediaType,
          advisory_byte_size: input.advisoryByteSize,
        }),
      },
    ),
  uploadVaultArtifact: (
    vaultId: string,
    acquisitionId: string,
    uploadAuthorizationId: string,
    file: File,
  ) => {
    const form = new FormData();
    form.set("upload_authorization_id", uploadAuthorizationId);
    form.set("operation_key", operationKey("vault-artifact"));
    form.set("artifact", file);
    return request<VaultArtifactAdmission>(
      `/desktop-api/v1/vaults/${encodeURIComponent(vaultId)}/acquisitions/${encodeURIComponent(acquisitionId)}/artifact`,
      { method: "POST", body: form },
    );
  },
  vaultIntakeRecords: (vaultId: string) =>
    request<VaultIntakeRecords>(
      `/desktop-api/v1/vaults/${encodeURIComponent(vaultId)}/intake`,
    ),
  createVaultBackup: (vaultId: string) =>
    request<VaultBackupResult>(
      `/desktop-api/v1/vaults/${encodeURIComponent(vaultId)}/backups`,
      {
        method: "POST",
        body: JSON.stringify({ operation_key: operationKey("vault-backup") }),
      },
    ),
  verifyVaultBackup: (vaultId: string, generationId: string) =>
    request<VaultBackupVerification>(
      `/desktop-api/v1/vaults/${encodeURIComponent(vaultId)}/backups/${encodeURIComponent(generationId)}/verify`,
      {
        method: "POST",
        body: JSON.stringify({ operation_key: operationKey("vault-backup-verify") }),
      },
    ),
  commandCenter: (accountId: string) =>
    request<CommandCenterResponse>(
      `/desktop-api/v1/command-center?account_id=${encodeURIComponent(accountId)}`,
    ),
  schedule: async (accountId: string) =>
    (
      await request<{ rows: ScheduleRow[] }>(
        `/desktop-api/v1/schedule?account_id=${encodeURIComponent(accountId)}&days=90`,
      )
    ).rows,
  records: async (accountId: string) =>
    (
      await request<{ rows: SourceRow[] }>(
        `/desktop-api/v1/records?account_id=${encodeURIComponent(accountId)}`,
      )
    ).rows,
  metrics: async (accountId: string) =>
    (
      await request<{ rows: MetricRow[] }>(
        `/desktop-api/v1/metrics?account_id=${encodeURIComponent(accountId)}`,
      )
    ).rows,
  workItem: (workItemId: string) =>
    request<Record<string, unknown>>(
      `/desktop-api/v1/work-items/${encodeURIComponent(workItemId)}`,
    ),
  capture: (title: string) =>
    request<{ work_item_id: string }>("/desktop-api/v1/work-items", {
      method: "POST",
      body: JSON.stringify({ title, operation_key: operationKey("capture") }),
    }),
  registerEvidence: (workItemId: string, relativePath: string) =>
    request<{ evidence_id: string; sha256: string }>(
      `/desktop-api/v1/work-items/${encodeURIComponent(workItemId)}/evidence`,
      {
        method: "POST",
        body: JSON.stringify({
          relative_path: relativePath,
          operation_key: operationKey("evidence"),
        }),
      },
    ),
};
