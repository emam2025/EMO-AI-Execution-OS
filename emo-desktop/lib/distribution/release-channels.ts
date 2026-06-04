import { createHash } from "crypto";

export type ChannelName = "stable" | "beta" | "rc";

export interface ChannelConfig {
  name: ChannelName;
  version: string;
  buildNumber: number;
  rolloutPercentage: number;
  previousVersion: string | null;
  releasedAt: number;
  active: boolean;
  metadata: Record<string, unknown>;
}

export interface RolloutStatus {
  channel: ChannelName;
  percentage: number;
  active: boolean;
  totalUsers: number;
  rolledOutUsers: number;
  rollbackAvailable: boolean;
}

export interface RollbackResult {
  success: boolean;
  previousVersion: string | null;
  revertedUsers: number;
  reason?: string;
}

const channels = new Map<ChannelName, ChannelConfig>();
const userAssignments = new Map<string, ChannelName>();
const VERSION_REGEX = /^\d+\.\d+\.\d+(-[a-zA-Z0-9]+)?$/;

const CHANNEL_DEFAULTS: Record<ChannelName, { version: string; rolloutPercentage: number }> = {
  stable: { version: "1.0.0", rolloutPercentage: 100 },
  beta: { version: "1.1.0-beta", rolloutPercentage: 25 },
  rc: { version: "1.1.0-rc", rolloutPercentage: 10 },
};

function hashUserId(userId: string): number {
  const hash = createHash("sha256").update(userId).digest("hex");
  return parseInt(hash.slice(0, 8), 16);
}

export function setChannel(channel: ChannelName, version?: string): ChannelConfig {
  const def = CHANNEL_DEFAULTS[channel];
  const finalVersion = version || def.version;
  if (!VERSION_REGEX.test(finalVersion)) {
    throw new Error(`Invalid version format: ${finalVersion}. Expected semver (e.g., 1.0.0)`);
  }
  const existing = channels.get(channel);
  const config: ChannelConfig = {
    name: channel,
    version: finalVersion,
    buildNumber: (existing?.buildNumber ?? 0) + 1,
    rolloutPercentage: existing?.rolloutPercentage ?? def.rolloutPercentage,
    previousVersion: existing?.version ?? null,
    releasedAt: Date.now(),
    active: true,
    metadata: {},
  };
  channels.set(channel, config);
  return { ...config };
}

export function gradualRollout(channel: ChannelName, percentage: number): RolloutStatus {
  if (percentage < 0 || percentage > 100) {
    throw new Error("Rollout percentage must be between 0 and 100");
  }
  const config = channels.get(channel);
  if (!config) {
    throw new Error(`Channel ${channel} not initialized. Call setChannel first.`);
  }
  config.rolloutPercentage = percentage;
  const totalUsers = userAssignments.size || 100;
  const rolledOutUsers = Math.floor(totalUsers * (percentage / 100));
  return {
    channel,
    percentage,
    active: percentage > 0,
    totalUsers,
    rolledOutUsers,
    rollbackAvailable: config.previousVersion !== null,
  };
}

export function assignUserToChannel(userId: string): ChannelName {
  const hash = hashUserId(userId);
  const sortedChannels: ChannelName[] = ["rc", "beta", "stable"];
  const hashFraction = hash / 0xffffffff;
  let cumulative = 0;
  let assigned: ChannelName = "stable";
  for (const ch of sortedChannels) {
    const config = channels.get(ch);
    if (!config || !config.active) continue;
    cumulative += config.rolloutPercentage / 100;
    if (hashFraction <= cumulative) {
      assigned = ch;
      break;
    }
  }
  userAssignments.set(userId, assigned);
  return assigned;
}

export function getUserChannel(userId: string): ChannelName | null {
  return userAssignments.get(userId) ?? null;
}

export function instantRollback(channel: ChannelName): RollbackResult {
  const config = channels.get(channel);
  if (!config) {
    return { success: false, previousVersion: null, revertedUsers: 0, reason: "channel not found" };
  }
  if (!config.previousVersion) {
    return { success: false, previousVersion: null, revertedUsers: 0, reason: "no previous version to rollback to" };
  }
  const prevVersion = config.previousVersion;
  const reverted: string[] = [];
  for (const [userId, userChannel] of userAssignments) {
    if (userChannel === channel) {
      userAssignments.set(userId, "stable");
      reverted.push(userId);
    }
  }
  config.version = prevVersion;
  config.previousVersion = null;
  config.rolloutPercentage = 0;
  config.active = false;
  return {
    success: true,
    previousVersion: prevVersion,
    revertedUsers: reverted.length,
  };
}

export function getChannelConfig(channel: ChannelName): ChannelConfig | undefined {
  return channels.get(channel);
}

export function listActiveChannels(): ChannelConfig[] {
  return Array.from(channels.values()).filter((c) => c.active);
}

export function clearAllChannels(): void {
  channels.clear();
  userAssignments.clear();
}
