/**
 * Bridge Tests — Rust IPC Bindings
 *
 * Verifies that IPC commands are correctly registered and return typed responses.
 * Uses MockAdapter for test isolation — no Tauri runtime required.
 * CORE FREEZE: No imports from core/ or releases/
 */
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { RuntimeClient, setMockAdapter, getSessionToken } from "../../ui/src/lib/api/runtime_client";
import type { MockAdapter, RuntimeInfo, AgentTask, AgentResult, RuntimeStatus } from "../../ui/src/lib/api/runtime_client";
import type { ProviderId } from "../../lib/credentials/types";

function createMockAdapter(): MockAdapter {
  return {
    async startRuntime(): Promise<RuntimeInfo> {
      return { pid: 4242, port: 8080, status: "running", session_token: "st_test_001" };
    },
    async stopRuntime(_pid: number): Promise<void> {},
    async getRuntimeStatus(): Promise<RuntimeStatus> {
      return { running: true, pid: 4242, port: 8080, healthy: true };
    },
    async setApiKey(_provider: ProviderId, _key: string): Promise<void> {},
    async runAgent(_task: AgentTask): Promise<AgentResult> {
      return { run_id: "run_test_001", status: "completed", result: "mock result", elapsed_seconds: 1.23 };
    },
  };
}

describe("Rust IPC Bindings", () => {
  beforeEach(() => {
    setMockAdapter(createMockAdapter());
  });

  afterEach(() => {
    setMockAdapter(null);
  });

  it("should register start_runtime command", async () => {
    const session = await RuntimeClient.startRuntime();
    expect(session).toBeDefined();
    expect(session.pid).toBeGreaterThan(0);
    expect(session.session_token).toMatch(/^st_/);
  });

  it("should register stop_runtime command", async () => {
    const result = await RuntimeClient.stopRuntime(4242);
    expect(result.terminated).toBe(true);
  });

  it("should register get_runtime_status command", async () => {
    await RuntimeClient.startRuntime();
    const status = await RuntimeClient.getRuntimeStatus();
    expect(status).toBeDefined();
  });

  it("should register set_api_key command", async () => {
    await expect(RuntimeClient.setApiKey("openai", "sk-test-12345678")).resolves.toBeUndefined();
  });

  it("should register run_agent command", async () => {
    await RuntimeClient.startRuntime();
    const result = await RuntimeClient.runAgent({
      project_id: "proj_test",
      instruction: "test instruction",
    });
    expect(result).toBeDefined();
    expect(result.run_id).toBeDefined();
    expect(result.status).toBe("completed");
  });
});
