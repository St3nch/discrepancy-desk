import { invoke } from "@tauri-apps/api/core";
import type { BackendSession, CommandCenterResponse, DesktopHealth, OwnedAccount } from "./types";

let session: BackendSession | null = null;
async function getSession(): Promise<BackendSession> { if (session === null) session = await invoke<BackendSession>("backend_session"); return session; }
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const current = await getSession();
  const response = await fetch(`${current.baseUrl}${path}`, { ...init, headers: { "content-type": "application/json", "x-discrepancy-desk-token": current.launchToken, ...(init?.headers ?? {}) } });
  const payload = await response.json().catch(() => ({ message: "Backend request refused" }));
  if (!response.ok) throw new Error(payload.message ?? "Backend request refused");
  return payload as T;
}
export const operationKey = (name: string) => `desktop:${name}:${crypto.randomUUID()}`;
export const desktopClient = {
  health: () => request<DesktopHealth>("/desktop-api/v1/health"),
  accounts: async () => (await request<{ accounts: OwnedAccount[] }>("/desktop-api/v1/accounts")).accounts,
  commandCenter: (accountId: string) => request<CommandCenterResponse>(`/desktop-api/v1/command-center?account_id=${encodeURIComponent(accountId)}`),
  capture: (title: string) => request<{ work_item_id: string }>("/desktop-api/v1/work-items", { method: "POST", body: JSON.stringify({ title, operation_key: operationKey("capture") }) }),
};
