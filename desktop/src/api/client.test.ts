import { afterEach, describe, expect, it, vi } from "vitest";

const { invokeMock } = vi.hoisted(() => ({ invokeMock: vi.fn() }));

vi.mock("@tauri-apps/api/core", () => ({ invoke: invokeMock }));

import { desktopClient } from "./client";

describe("desktop Vault API contract", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("creates a Vault through the token-gated loopback API without actor authority", async () => {
    invokeMock.mockResolvedValue({
      baseUrl: "http://127.0.0.1:43123",
      launchToken: "launch-token",
    });
    vi.stubGlobal("crypto", { randomUUID: () => "operation-uuid" });

    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ vault_id: "vault-1" }), {
        status: 201,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(desktopClient.createVault("Desk Vault", "desk-vault")).resolves.toEqual({
      vault_id: "vault-1",
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://127.0.0.1:43123/desktop-api/v1/vaults");
    expect(init.method).toBe("POST");
    expect(init.headers).toMatchObject({
      "content-type": "application/json",
      "x-discrepancy-desk-token": "launch-token",
    });

    const body = JSON.parse(String(init.body)) as Record<string, unknown>;
    expect(body).toEqual({
      display_name: "Desk Vault",
      relative_root: "desk-vault",
      owned_account_ids: [],
      operation_key: "desktop:vault-create:operation-uuid",
    });
    expect(body).not.toHaveProperty("actor_id");
    expect(body).not.toHaveProperty("database_path");
  });
});
