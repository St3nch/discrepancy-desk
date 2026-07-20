export interface DesktopHealth { api_version: string; service: string; status: "healthy" | "unhealthy"; sqlite_integrity: string; migration: string; }
export interface BackendSession { baseUrl: string; launchToken: string; apiVersion: string; }
export interface OwnedAccount { id: string; platform: string; external_account_id: string; username: string | null; }
export interface CommandCenterResponse { api_version: string; account_id: string; data: Record<string, Array<Record<string, unknown>>>; }
