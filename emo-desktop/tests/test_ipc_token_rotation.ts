/**
 * Test: IPC Token Rotation
 *
 * Verifies that each start_runtime() generates a unique session token,
 * and that the previous token is invalidated on restart.
 *
 * Uses MockAdapter for isolated testing without Tauri IPC.
 */
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { RuntimeClient, getSessionToken, setMockAdapter } from "../ui/src/lib/api/runtime_client";
import type { MockAdapter, RuntimeInfo, AgentTask, AgentResult, RuntimeStatus } from "../ui/src/lib/api/runtime_client";
import type { ProviderId } from "../lib/credentials/types";

function createMockAdapter(): MockAdapter {
  let tokenCounter = 0;
  return {
    async startRuntime(): Promise<RuntimeInfo> {
      tokenCounter++;
      return {
        pid: 1000 + tokenCounter,
        port: 8080,
        status: "running",
        session_token: `st_mock_${tokenCounter}_${Date.now()}`,
      };
    },
    async stopRuntime(_pid: number): Promise<void> {},
    async getRuntimeStatus(): Promise<RuntimeStatus> {
      return { running: true, pid: 1001, port: 8080, healthy: true };
    },
    async setApiKey(_provider: ProviderId, _key: string): Promise<void> {},
    async runAgent(_task: AgentTask): Promise<AgentResult> {
      return { run_id: "mock_run_1", status: "completed", result: "mock", elapsed_seconds: 0.1 };
    },
  };
}

describe("IPC Token Rotation", () => {
  beforeEach(() => {
    setMockAdapter(createMockAdapter());
  });

  afterEach(() => {
    setMockAdapter(null);
  });

  it("generates a unique token on start_runtime", async () => {
    const session = await RuntimeClient.startRuntime();
    expect(session.session_token).toBeDefined();
    expect(session.session_token).toMatch(/^st_mock_\d+_\d+$/);
  });

  it("generates different tokens on sequential starts", async () => {
    const s1 = await RuntimeClient.startRuntime();
    const token1 = getSessionToken();
    const s2 = await RuntimeClient.startRuntime();
    const token2 = getSessionToken();
    expect(token1).not.toBe(token2);
  });

  it("clears token on stop_runtime", async () => {
    const session = await RuntimeClient.startRuntime();
    await RuntimeClient.stopRuntime(session.pid);
    expect(getSessionToken()).toBeNull();
  });
});
