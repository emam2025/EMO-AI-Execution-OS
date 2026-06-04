/**
 * Bridge Tests — Runtime Lifecycle
 *
 * Verifies start/stop/restart lifecycle management through the IPC bridge.
 * CORE FREEZE: No imports from core/ or releases/
 */
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { RuntimeClient, getSessionToken, setMockAdapter } from "../../ui/src/lib/api/runtime_client";
import type { MockAdapter, RuntimeInfo, AgentTask, AgentResult, RuntimeStatus } from "../../ui/src/lib/api/runtime_client";
import type { ProviderId } from "../../lib/credentials/types";

function createLifecycleMock(): MockAdapter {
  let running = false;
  let currentPid = 0;
  return {
    async startRuntime(): Promise<RuntimeInfo> {
      running = true;
      currentPid = 5000 + Math.floor(Math.random() * 1000);
      return { pid: currentPid, port: 8080, status: "running", session_token: `st_lifecycle_${currentPid}` };
    },
    async stopRuntime(_pid: number): Promise<void> {
      running = false;
    },
    async getRuntimeStatus(): Promise<RuntimeStatus> {
      return { running, pid: currentPid || null, port: running ? 8080 : null, healthy: running };
    },
    async setApiKey(_provider: ProviderId, _key: string): Promise<void> {},
    async runAgent(_task: AgentTask): Promise<AgentResult> {
      return { run_id: "run_lc_1", status: "completed", result: "lifecycle ok", elapsed_seconds: 0.3 };
    },
  };
}

describe("Runtime Lifecycle via IPC Bridge", () => {
  beforeEach(() => {
    setMockAdapter(createLifecycleMock());
  });

  afterEach(() => {
    setMockAdapter(null);
  });

  it("should start the runtime and return a session", async () => {
    const session = await RuntimeClient.startRuntime();
    expect(session.pid).toBeGreaterThan(0);
    expect(session.session_token).toBeDefined();
    expect(session.status).toBe("running");
  });

  it("should return runtime status after start", async () => {
    await RuntimeClient.startRuntime();
    const status = await RuntimeClient.getRuntimeStatus();
    expect(status).toBeDefined();
  });

  it("should stop the runtime", async () => {
    const session = await RuntimeClient.startRuntime();
    const result = await RuntimeClient.stopRuntime(session.pid);
    expect(result.terminated).toBe(true);
  });

  it("should clear session token after stop", async () => {
    const session = await RuntimeClient.startRuntime();
    expect(getSessionToken()).not.toBeNull();
    await RuntimeClient.stopRuntime(session.pid);
    expect(getSessionToken()).toBeNull();
  });

  it("should support multiple start/stop cycles", async () => {
    for (let i = 0; i < 3; i++) {
      const session = await RuntimeClient.startRuntime();
      expect(session.pid).toBeGreaterThan(0);
      await RuntimeClient.stopRuntime(session.pid);
      expect(getSessionToken()).toBeNull();
    }
  });
});
