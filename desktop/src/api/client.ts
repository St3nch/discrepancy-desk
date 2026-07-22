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
  VaultHealth,
  VaultSummary,
} from "./types";

let session: BackendSession | null = null;

async function getSession(): Promise<BackendSession> {
  if (session === null) session = await invoke<BackendSession>("backend_session");
  return session;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const current = await getSession();
  const response = await fetch(`${current.baseUrl}${path}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      "x-discrepancy-desk-token": current.launchToken,
      ...(init?.headers ?? {}),
    },
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
