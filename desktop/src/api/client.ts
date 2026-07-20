import { invoke } from "@tauri-apps/api/core";
import type { BackendSession, DesktopHealth } from "./types";

let session: BackendSession | null = null;

async function getSession(): Promise<BackendSession> {
  if (session === null) session = await invoke<BackendSession>("backend_session");
  return session;
}

async function request<T>(path: string): Promise<T> {
  const current = await getSession();
  const response = await fetch(`${current.baseUrl}${path}`, {
    headers: { "x-discrepancy-desk-token": current.launchToken },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ message: "Backend request refused" }));
    throw new Error(payload.message ?? "Backend request refused");
  }
  return response.json() as Promise<T>;
}

export const desktopClient = {
  health: () => request<DesktopHealth>("/desktop-api/v1/health"),
};
