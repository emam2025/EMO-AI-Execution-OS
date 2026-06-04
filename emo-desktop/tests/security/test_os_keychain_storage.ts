/**
 * Security Tests — OS Keychain Storage
 *
 * Tests keyring adapter for secure credential storage.
 * CORE FREEZE: No imports from core/ or releases/
 */
import { describe, it, expect } from "vitest";

// Mock the keyring adapter (avoids tauri IPC dependency in unit tests)
const createMockKeyring = () => {
  const store = new Map<string, string>();
  return {
    async storeKey(providerId: string, key: string) {
      if (!key || key.length < 8) throw new Error("Invalid key length");
      store.set(`provider_${providerId}`, key);
    },
    async getKey(providerId: string) {
      return store.get(`provider_${providerId}`) ?? null;
    },
    async deleteKey(providerId: string) {
      store.delete(`provider_${providerId}`);
    },
    async hasKey(providerId: string) {
      return store.has(`provider_${providerId}`);
    },
    async clearAllKeys() {
      store.clear();
    },
    async listConfiguredProviders() {
      const providers = ["openai", "anthropic", "gemini"];
      return providers.filter((p) => store.has(`provider_${p}`));
    },
  };
};

describe("OS Keychain Storage", () => {
  const keyring = createMockKeyring();

  it("should store a key for a valid provider", async () => {
    await keyring.storeKey("openai", "sk-test12345678");
    const retrieved = await keyring.getKey("openai");
    expect(retrieved).toBe("sk-test12345678");
  });

  it("should reject keys shorter than 8 characters", async () => {
    await expect(keyring.storeKey("openai", "short")).rejects.toThrow("Invalid key length");
  });

  it("should return null for a non-existent key", async () => {
    const result = await keyring.getKey("nonexistent");
    expect(result).toBeNull();
  });

  it("should delete a specific key", async () => {
    await keyring.storeKey("anthropic", "sk-ant-test123456");
    await keyring.deleteKey("anthropic");
    expect(await keyring.getKey("anthropic")).toBeNull();
  });

  it("should report hasKey correctly", async () => {
    await keyring.storeKey("gemini", "geminikey12345678");
    expect(await keyring.hasKey("gemini")).toBe(true);
    expect(await keyring.hasKey("groq")).toBe(false);
  });

  it("should clear all keys", async () => {
    await keyring.storeKey("openai", "key12345678");
    await keyring.storeKey("anthropic", "key12345678");
    await keyring.clearAllKeys();
    expect(await keyring.hasKey("openai")).toBe(false);
    expect(await keyring.hasKey("anthropic")).toBe(false);
  });

  it("should list only configured providers", async () => {
    await keyring.clearAllKeys();
    await keyring.storeKey("openai", "key12345678");
    const providers = await keyring.listConfiguredProviders();
    expect(providers).toContain("openai");
    expect(providers).not.toContain("anthropic");
  });

  it("should store multiple keys independently", async () => {
    await keyring.storeKey("openai", "key-openai-001");
    await keyring.storeKey("anthropic", "key-anthropic-001");
    await keyring.storeKey("gemini", "key-gemini-001");
    expect(await keyring.getKey("openai")).toBe("key-openai-001");
    expect(await keyring.getKey("anthropic")).toBe("key-anthropic-001");
    expect(await keyring.getKey("gemini")).toBe("key-gemini-001");
  });

  it("should return empty list when no keys stored", async () => {
    await keyring.clearAllKeys();
    const providers = await keyring.listConfiguredProviders();
    expect(providers).toHaveLength(0);
  });
});
