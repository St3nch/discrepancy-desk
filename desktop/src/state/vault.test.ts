import { describe, expect, it } from "vitest";

import { initialAccountSelection } from "./account";
import { initialVaultSelection } from "./vault";


describe("Vault selection authority", () => {
  it("remains independent from platform-account selection", () => {
    const accountSelection = { ...initialAccountSelection, accountId: "acct-x" };
    const vaultSelection = { ...initialVaultSelection, vaultId: "vault-brand" };

    expect(accountSelection.accountId).toBe("acct-x");
    expect(vaultSelection.vaultId).toBe("vault-brand");
    expect(Object.hasOwn(accountSelection, "vaultId")).toBe(false);
    expect(Object.hasOwn(vaultSelection, "accountId")).toBe(false);
  });
});
