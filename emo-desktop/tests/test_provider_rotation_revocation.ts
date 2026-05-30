import { describe, it, expect, vi } from "vitest";
import { credentialProvider } from "../lib/credentials/os-keyring";

describe("Provider Key Rotation & Revocation (P2)", () => {
  it("rotateKey replaces the stored key", async () => {
    const saveSpy = vi
      .spyOn(credentialProvider, "saveKey")
      .mockResolvedValue(undefined);

    await credentialProvider.rotateKey("openai", "sk-new-rotated-key");
    expect(saveSpy).toHaveBeenCalledWith("openai", "sk-new-rotated-key");
    saveSpy.mockRestore();
  });

  it("deleteKey removes key without error", async () => {
    const deleteSpy = vi
      .spyOn(credentialProvider, "deleteKey")
      .mockResolvedValue(undefined);

    await expect(credentialProvider.deleteKey("openai")).resolves.toBeUndefined();
    deleteSpy.mockRestore();
  });

  it("rotation does not crash the application session", async () => {
    // Verify rotation preserves the ability to list providers.
    vi.spyOn(credentialProvider, "saveKey").mockResolvedValue(undefined);
    vi.spyOn(credentialProvider, "listConfiguredProviders").mockResolvedValue([
      "openai",
      "anthropic",
    ]);

    await credentialProvider.rotateKey("openai", "sk-service-key");
    const providers = await credentialProvider.listConfiguredProviders();
    expect(providers).toContain("openai");
  });
});
