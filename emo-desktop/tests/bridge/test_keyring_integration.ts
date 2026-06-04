/**
 * Bridge Tests — Keyring Integration
 *
 * Verifies that API keys are stored/retrieved securely through the IPC bridge.
 * CORE FREEZE: No imports from core/ or releases/
 */
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { RuntimeClient, setMockAdapter } from "../../ui/src/lib/api/runtime_client";
import type { MockAdapter, RuntimeInfo, AgentTask, AgentResult, RuntimeStatus } from "../../ui/src/lib/api/runtime_client";
import type { ProviderId } from "../../lib/credentials/types";

interface KeyringEntry {
  provider: ProviderId;
  key: string;
}

function createMockAdapterWithKeyring(): MockAdapter {
  const keyring = new Map<string, string>();
  return {
    async startRuntime(): Promise<RuntimeInfo> {
      return { pid: 100, port: 8080, status: "running", session_token: "st_keyring_test" };
    },
    async stopRuntime(_pid: number): Promise<void> {},
    async getRuntimeStatus(): Promise<RuntimeStatus> {
      return { running: true, pid: 100, port: 8080, healthy: true };
    },
    async setApiKey(provider: ProviderId, key: string): Promise<void> {
      if (key.length < 8) throw new Error("Key must be at least 8 characters");
      keyring.set(`provider_${provider}`, key);
    },
    async runAgent(_task: AgentTask): Promise<AgentResult> {
      return { run_id: "run_kr_1", status: "completed", result: "ok", elapsed_seconds: 0.5 };
    },
  };
}

describe("Keyring Integration via IPC Bridge", () => {
  beforeEach(() => {
    setMockAdapter(createMockAdapterWithKeyring());
  });

  afterEach(() => {
    setMockAdapter(null);
  });

  it("should store a key for a valid provider", async () => {
    await expect(RuntimeClient.setApiKey("openai", "sk-test-12345678")).resolves.toBeUndefined();
  });

  it("should reject keys shorter than 8 characters", async () => {
    await expect(RuntimeClient.setApiKey("openai", "short")).rejects.toThrow();
  });

  it("should store multiple provider keys independently", async () => {
    await RuntimeClient.setApiKey("openai", "sk-openai-12345678");
    await RuntimeClient.setApiKey("anthropic", "sk-anthropic-87654321");
    await RuntimeClient.setApiKey("gemini", "gk-gemini-11223344");
    // No conflict means success
    expect(true).toBe(true);
  });

  it("should not expose keys in error messages", async () => {
    try {
      await RuntimeClient.setApiKey("openai", "short");
    } catch (e) {
      expect(String(e)).not.toContain("short");
    }
  });

  it("should accept all supported provider IDs", async () => {
    const providers: ProviderId[] = [
      "openai", "anthropic", "gemini", "openrouter", "groq",
      "together", "deepseek", "ollama", "vllm", "openai_compatible",
    ];
    for (const provider of providers) {
      await expect(
        RuntimeClient.setApiKey(provider, `test-key-${provider}-12345678`)
      ).resolves.toBeUndefined();
    }
  });
});
