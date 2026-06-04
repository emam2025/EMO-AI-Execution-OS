import { describe, it, expect, beforeEach } from "vitest";
import {
  setChannel,
  gradualRollout,
  instantRollback,
  assignUserToChannel,
  getUserChannel,
  getChannelConfig,
  listActiveChannels,
  clearAllChannels,
} from "../../lib/distribution/release-channels";

describe("TestChannelIntegrity", () => {
  beforeEach(() => {
    clearAllChannels();
  });

  it("should initialize channel with valid version and increment build number", () => {
    const config = setChannel("beta", "1.1.0-beta");
    expect(config.name).toBe("beta");
    expect(config.version).toBe("1.1.0-beta");
    expect(config.buildNumber).toBe(1);
    expect(config.active).toBe(true);
    const config2 = setChannel("beta", "1.2.0-beta");
    expect(config2.buildNumber).toBe(2);
  });

  it("should assign users to channels based on rollout percentage", () => {
    setChannel("stable", "1.0.0");
    gradualRollout("stable", 50);
    setChannel("beta", "1.1.0-beta");
    gradualRollout("beta", 0);
    const user1 = assignUserToChannel("user-001");
    expect(user1).toBe("stable");
    gradualRollout("beta", 50);
    const betaCount = Array.from({ length: 100 }, (_, i) => assignUserToChannel(`user-${i}`)).filter((c) => c === "beta").length;
    expect(betaCount).toBeGreaterThan(0);
  });

  it("should rollback to previous version and revert user assignments", () => {
    setChannel("beta", "1.0.0-beta");
    setChannel("beta", "1.1.0-beta");
    gradualRollout("beta", 100);
    assignUserToChannel("rollback-user");
    expect(getUserChannel("rollback-user")).toBe("beta");
    const rollback = instantRollback("beta");
    expect(rollback.success).toBe(true);
    expect(rollback.previousVersion).toBe("1.0.0-beta");
    const config = getChannelConfig("beta");
    expect(config!.version).toBe("1.0.0-beta");
    expect(config!.active).toBe(false);
  });

  it("should reject invalid version format", () => {
    expect(() => setChannel("stable", "invalid-version")).toThrow("Invalid version format");
  });

  it("should list only active channels", () => {
    setChannel("stable", "1.0.0");
    setChannel("beta", "1.1.0-beta");
    gradualRollout("beta", 50);
    const active = listActiveChannels();
    expect(active.length).toBeGreaterThanOrEqual(2);
    expect(active.some((c) => c.name === "stable")).toBe(true);
  });
});
