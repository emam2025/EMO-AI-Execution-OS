import { describe, it, expect } from "vitest";
import { credentialProvider } from "../lib/credentials/os-keyring";
import type { ICredentialProvider } from "../lib/credentials/types";

describe("OS Keychain Storage (P2)", () => {
  it("exposes ICredentialProvider interface (no localStorage/indexedDB in methods)", async () => {
    // Verify the provider methods don't reference browser storage.
    const provider = credentialProvider as ICredentialProvider;
    expect(provider.saveKey).toBeDefined();
    expect(provider.getKey).toBeDefined();
    expect(provider.deleteKey).toBeDefined();
    expect(provider.hasKey).toBeDefined();
    expect(provider.listConfiguredProviders).toBeDefined();
    expect(provider.rotateKey).toBeDefined();
    expect(provider.getStatus).toBeDefined();

    // Check the method source does not contain browser storage APIs.
    const saveSource = provider.saveKey.toString();
    expect(saveSource).not.toContain("localStorage");
    expect(saveSource).not.toContain("sessionStorage");
    expect(saveSource).not.toContain("IndexedDB");
  });

  it("rejects dotenv / config.json / file-system patterns in source", () => {
    const provider = credentialProvider as ICredentialProvider;
    const sources = [
      provider.saveKey.toString(),
      provider.getKey.toString(),
      provider.deleteKey.toString(),
      provider.hasKey.toString(),
    ];
    for (const src of sources) {
      expect(src).not.toContain(".env");
      expect(src).not.toContain("config.json");
      expect(src).not.toContain("writeFile");
      expect(src).not.toContain("readFile");
      expect(src).not.toContain("existsSync");
    }
  });

  it("keychain methods accept ProviderId and return Promise", () => {
    const provider = credentialProvider as ICredentialProvider;
    const saveResult = provider.saveKey("openai", "sk-test");
    expect(saveResult).toBeInstanceOf(Promise);
    const getResult = provider.getKey("openai");
    expect(getResult).toBeInstanceOf(Promise);
    const deleteResult = provider.deleteKey("openai");
    expect(deleteResult).toBeInstanceOf(Promise);
  });

  it("hasKey returns false for unconfigured providers", async () => {
    const result = await credentialProvider.hasKey("openai");
    expect(result).toBe(false);
  });
});
