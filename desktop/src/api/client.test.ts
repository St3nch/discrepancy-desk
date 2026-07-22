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
    const headers = new Headers(init.headers);
    expect(headers.get("content-type")).toBe("application/json");
    expect(headers.get("x-discrepancy-desk-token")).toBe("launch-token");

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

  it("admits Vault intake metadata before bytes without caller-selected authority", async () => {
    vi.stubGlobal("crypto", { randomUUID: () => "operation-uuid" });
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          status: "ready_for_upload",
          acquisition_id: "acq-1",
          upload_authorization_id: "upload-1",
          result_id: "acq-1",
          reason_code: null,
        }),
        { status: 201, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await desktopClient.startVaultIntake("vault-1", {
      sourceKind: "manual_file",
      descriptorClass: "file",
      displayLabel: "Local document",
      retentionClassification: "preservation_compatible",
      policyBasisReference: "owner-authorized local preservation",
      humanClassificationNote: "Keep for research",
      expectsBytes: true,
      suppliedFilename: "document.txt",
      suppliedMediaType: "text/plain",
      advisoryByteSize: 12,
    });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(String(init.body)) as Record<string, unknown>;
    expect(body.retention_classification).toBe("preservation_compatible");
    expect(body.expects_bytes).toBe(true);
    expect(body).not.toHaveProperty("actor_id");
    expect(body).not.toHaveProperty("vault_path");
    expect(body).not.toHaveProperty("canonical_path");
    expect(body).not.toHaveProperty("sha256");
  });

  it("uploads bytes as multipart without forcing a JSON content type", async () => {
    vi.stubGlobal("crypto", { randomUUID: () => "operation-uuid" });
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          acquisition_id: "acq-1",
          artifact_id: "artifact-1",
          sha256: "a".repeat(64),
          byte_size: 5,
          storage_relative_path: `objects/sha256/aa/aa/${"a".repeat(64)}`,
          reused_existing: false,
        }),
        { status: 201, headers: { "content-type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const file = new File(["hello"], "hello.txt", { type: "text/plain" });

    await desktopClient.uploadVaultArtifact("vault-1", "acq-1", "upload-1", file);

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.body).toBeInstanceOf(FormData);
    const headers = new Headers(init.headers);
    expect(headers.get("content-type")).toBeNull();
    expect(headers.get("x-discrepancy-desk-token")).toBe("launch-token");
  });
});
