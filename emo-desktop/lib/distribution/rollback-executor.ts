import { instantRollback, setChannel, gradualRollout, clearAllChannels, getChannelConfig } from "./release-channels";
import type { ChannelName } from "./release-channels";
import { logAuditEvent } from "../security/audit-logger";
import { evaluateMetric } from "../monitoring/production-alerts";

export interface RollbackPlan {
  id: string;
  triggerChannels: ChannelName[];
  failureThresholds: Array<{ metric: string; threshold: number; operator: "gt" | "lt" }>;
  autoExecute: boolean;
  estimatedDurationMs: number;
  notificationChannels: string[];
}

export interface RollbackExecution {
  planId: string;
  startedAt: number;
  completedAt: number;
  durationMs: number;
  channelsReverted: ChannelName[];
  versionsBefore: Record<string, string>;
  versionsAfter: Record<string, string>;
  usersAffected: number;
  success: boolean;
  reason?: string;
}

const MAX_ROLLBACK_DURATION_MS = 5 * 60 * 1000;

const defaultPlan: RollbackPlan = {
  id: "emergency-rollback-v1",
  triggerChannels: ["stable", "beta"],
  failureThresholds: [
    { metric: "crash_rate", threshold: 0.01, operator: "gt" },
    { metric: "avg_latency_ms", threshold: 2000, operator: "gt" },
    { metric: "error_rate", threshold: 0.05, operator: "gt" },
  ],
  autoExecute: true,
  estimatedDurationMs: 120000,
  notificationChannels: ["email", "pagerduty"],
};

let activePlan: RollbackPlan = { ...defaultPlan };

export function configureRollbackPlan(plan: Partial<RollbackPlan>): RollbackPlan {
  activePlan = { ...activePlan, ...plan };
  return { ...activePlan };
}

export function getRollbackPlan(): RollbackPlan {
  return { ...activePlan };
}

export function checkFailureThresholds(metrics: Array<{ metric: string; value: number }>): { shouldRollback: boolean; triggered: string[] } {
  const triggered: string[] = [];
  for (const { metric, value } of metrics) {
    for (const threshold of activePlan.failureThresholds) {
      if (threshold.metric !== metric) continue;
      let failed = false;
      switch (threshold.operator) {
        case "gt": failed = value > threshold.threshold; break;
        case "lt": failed = value < threshold.threshold; break;
      }
      if (failed) {
        triggered.push(`${metric}=${value} exceeds ${threshold.operator} ${threshold.threshold}`);
      }
    }
  }
  return { shouldRollback: triggered.length > 0, triggered };
}

export function executeRollback(channels?: ChannelName[]): RollbackExecution {
  const startTime = Date.now();
  const targets = channels ?? activePlan.triggerChannels;
  const versionsBefore: Record<string, string> = {};
  const versionsAfter: Record<string, string> = {};
  const reverted: ChannelName[] = [];
  for (const ch of targets) {
    const config = getChannelConfig(ch);
    if (config) {
      versionsBefore[ch] = config.version;
    }
  }
  for (const ch of targets) {
    const result = instantRollback(ch);
    if (result.success) {
      reverted.push(ch);
      versionsAfter[ch] = result.previousVersion ?? "none";
    }
  }
  const elapsed = Date.now() - startTime;
  const success = reverted.length > 0 && elapsed < MAX_ROLLBACK_DURATION_MS;
  const exec: RollbackExecution = {
    planId: activePlan.id,
    startedAt: startTime,
    completedAt: Date.now(),
    durationMs: elapsed,
    channelsReverted: reverted,
    versionsBefore,
    versionsAfter,
    usersAffected: 0,
    success,
    reason: success ? undefined : "rollback exceeded max duration or no channels reverted",
  };
  logAuditEvent({
    type: "permission_violation",
    severity: "critical",
    source: "rollback-executor",
    detail: `Rollback executed: ${reverted.join(", ")} in ${elapsed}ms`,
    metadata: { planId: activePlan.id, durationMs: elapsed, channelsReverted: reverted, success },
  });
  return exec;
}

export function simulateRollback(channels?: ChannelName[]): RollbackExecution {
  const exec = executeRollback(channels);
  const rollforwardChannels = exec.channelsReverted;
  for (const ch of rollforwardChannels) {
    const before = exec.versionsBefore[ch];
    if (before) {
      setChannel(ch, before);
      gradualRollout(ch, 100);
    }
  }
  return exec;
}

export function resetRollbackState(): void {
  activePlan = { ...defaultPlan };
}
