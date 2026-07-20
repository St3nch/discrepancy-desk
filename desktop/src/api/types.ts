export interface DesktopHealth { api_version: string; service: string; status: "healthy" | "unhealthy"; sqlite_integrity: string; migration: string; }
export interface BackendSession { baseUrl: string; launchToken: string; apiVersion: string; }
