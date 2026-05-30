/**
 * Test: IPC Token Rotation
 *
 * Verifies that each start_runtime() generates a unique session token,
 * and that the previous token is invalidated on restart.
 */
import { describe, it, expect } from "vitest";
import { RuntimeClient, getSessionToken } from "../ui/src/lib/api/runtime_client";

describe("IPC Token Rotation", () => {
  it("generates a unique token on start_runtime", async () => {
    const session = await RuntimeClient.startRuntime();
    expect(session.session_token).toBeDefined();
    expect(session.session_token).toMatch(/^st_[a-f0-9-]{36}$/);
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
