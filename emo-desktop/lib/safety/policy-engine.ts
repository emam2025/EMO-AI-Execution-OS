import { calculateRiskScores, type RiskProfile } from "./risk-calculator";

export type PolicyDecision = "ALLOW" | "DENY" | "REQUIRE_APPROVAL" | "EMERGENCY_STOP";

export type IndustrialLevel = 1 | 2 | 3 | 4;

export type ActionCategory =
  | "read"
  | "write"
  | "execute"
  | "deploy"
  | "delete"
  | "config_change"
  | "network_access"
  | "privilege_escalation"
  | "data_export"
  | "system_shutdown";

export interface Action {
  id: string;
  category: ActionCategory;
  description: string;
  target: string;
  initiatedBy: string;
  timestamp: number;
  metadata?: Record<string, unknown>;
}

export interface PolicyContext {
  industrialLevel: IndustrialLevel;
  activeCompliance: string[];
  userRoles: string[];
  approvedBy?: string[];
  emergencyOverride?: boolean;
  auditTrail: AuditEntry[];
}

export interface AuditEntry {
  timestamp: number;
  action: string;
  decision: PolicyDecision;
  reason: string;
  initiatedBy: string;
  approvedBy?: string[];
  riskProfile?: RiskProfile;
}

export interface PolicyConfig {
  industrialLevel: IndustrialLevel;
  resourceLimits: { maxCpuPercent: number; maxMemoryMb: number; maxNetworkRequestsPerMin: number };
  toolPermissions: { denyCategories: ActionCategory[]; requireApprovalCategories: ActionCategory[] };
  auditRequirements: { logAllActions: boolean; retentionDays: number; tamperProof: boolean };
  approvalPolicy: { singleApproval: boolean; dualApproval: boolean; emergencyStop: boolean };
  dataRetention: { maxDays: number; autoPurge: boolean; encryptAtRest: boolean };
}

const LEVEL_CONFIGS: Record<IndustrialLevel, PolicyConfig> = {
  1: {
    industrialLevel: 1,
    resourceLimits: { maxCpuPercent: 90, maxMemoryMb: 8192, maxNetworkRequestsPerMin: 1000 },
    toolPermissions: { denyCategories: ["system_shutdown"], requireApprovalCategories: ["deploy", "delete"] },
    auditRequirements: { logAllActions: true, retentionDays: 90, tamperProof: true },
    approvalPolicy: { singleApproval: true, dualApproval: false, emergencyStop: false },
    dataRetention: { maxDays: 365, autoPurge: false, encryptAtRest: true },
  },
  2: {
    industrialLevel: 2,
    resourceLimits: { maxCpuPercent: 75, maxMemoryMb: 4096, maxNetworkRequestsPerMin: 500 },
    toolPermissions: { denyCategories: ["system_shutdown", "privilege_escalation"], requireApprovalCategories: ["deploy", "delete", "config_change"] },
    auditRequirements: { logAllActions: true, retentionDays: 180, tamperProof: true },
    approvalPolicy: { singleApproval: true, dualApproval: false, emergencyStop: true },
    dataRetention: { maxDays: 730, autoPurge: false, encryptAtRest: true },
  },
  3: {
    industrialLevel: 3,
    resourceLimits: { maxCpuPercent: 50, maxMemoryMb: 2048, maxNetworkRequestsPerMin: 100 },
    toolPermissions: { denyCategories: ["system_shutdown", "privilege_escalation", "network_access"], requireApprovalCategories: ["deploy", "delete", "config_change", "data_export"] },
    auditRequirements: { logAllActions: true, retentionDays: 365, tamperProof: true },
    approvalPolicy: { singleApproval: false, dualApproval: true, emergencyStop: true },
    dataRetention: { maxDays: 1095, autoPurge: false, encryptAtRest: true },
  },
  4: {
    industrialLevel: 4,
    resourceLimits: { maxCpuPercent: 25, maxMemoryMb: 1024, maxNetworkRequestsPerMin: 30 },
    toolPermissions: { denyCategories: ["system_shutdown", "privilege_escalation", "network_access", "delete", "deploy"], requireApprovalCategories: ["write", "config_change", "data_export"] },
    auditRequirements: { logAllActions: true, retentionDays: 730, tamperProof: true },
    approvalPolicy: { singleApproval: false, dualApproval: true, emergencyStop: true },
    dataRetention: { maxDays: 2555, autoPurge: false, encryptAtRest: true },
  },
};

const CRITICAL_CATEGORIES: ActionCategory[] = [
  "system_shutdown", "privilege_escalation", "deploy", "delete",
];

const auditLog: AuditEntry[] = [];

export function getAuditLog(): AuditEntry[] {
  return auditLog;
}

export function clearAuditLog(): void {
  auditLog.splice(0, auditLog.length);
}

function recordAudit(action: string, decision: PolicyDecision, reason: string, initiatedBy: string, approvedBy?: string[], riskProfile?: RiskProfile): void {
  auditLog.push({ timestamp: Date.now(), action, decision, reason, initiatedBy, approvedBy, riskProfile });
}

export function applyIndustrialLevel(level: IndustrialLevel): PolicyConfig {
  const config = LEVEL_CONFIGS[level];
  if (!config) {
    throw new Error(`Invalid industrial level: ${level}. Valid levels: 1, 2, 3, 4`);
  }
  return config;
}

export function evaluateAction(action: Action, context: PolicyContext): { decision: PolicyDecision; reason: string; riskProfile?: RiskProfile } {
  const config = applyIndustrialLevel(context.industrialLevel);
  const riskProfile = calculateRiskScores(action, config);

  if (context.emergencyOverride) {
    recordAudit(action.id, "EMERGENCY_STOP", "Emergency override triggered — stopping all actions", action.initiatedBy);
    return { decision: "EMERGENCY_STOP", reason: "Emergency override active — all operations halted", riskProfile };
  }

  const isCritical = CRITICAL_CATEGORIES.includes(action.category) || riskProfile.riskScore >= 0.8;

  if (config.toolPermissions.denyCategories.includes(action.category)) {
    recordAudit(action.id, "DENY", `Category "${action.category}" is denied at level ${context.industrialLevel}`, action.initiatedBy, undefined, riskProfile);
    return { decision: "DENY", reason: `Action "${action.description}" is denied under current policy`, riskProfile };
  }

  if (config.toolPermissions.requireApprovalCategories.includes(action.category) || isCritical) {
    if (config.approvalPolicy.dualApproval) {
      const approvedBy = context.approvedBy || [];
      if (approvedBy.length < 2) {
        recordAudit(action.id, "REQUIRE_APPROVAL", `Dual approval required for "${action.category}" at level ${context.industrialLevel}`, action.initiatedBy, approvedBy, riskProfile);
        return { decision: "REQUIRE_APPROVAL", reason: `Dual approval required: "${action.description}" needs 2 approvals`, riskProfile };
      }
    } else if (config.approvalPolicy.singleApproval) {
      const approvedBy = context.approvedBy || [];
      if (approvedBy.length < 1) {
        recordAudit(action.id, "REQUIRE_APPROVAL", `Single approval required for "${action.category}"`, action.initiatedBy, approvedBy, riskProfile);
        return { decision: "REQUIRE_APPROVAL", reason: `Approval required: "${action.description}" needs 1 approval`, riskProfile };
      }
    }
  }

  recordAudit(action.id, "ALLOW", `Action permitted at level ${context.industrialLevel}`, action.initiatedBy, context.approvedBy, riskProfile);
  return { decision: "ALLOW", reason: `Action "${action.description}" permitted`, riskProfile };
}

export function emergencyStop(context: PolicyContext, triggeredBy: string, reason: string): void {
  recordAudit("EMERGENCY_STOP", "EMERGENCY_STOP", `Emergency stop triggered by ${triggeredBy}: ${reason}`, triggeredBy);
  context.emergencyOverride = true;
}

export function releaseEmergencyStop(context: PolicyContext, triggeredBy: string): void {
  context.emergencyOverride = false;
  recordAudit("EMERGENCY_STOP_RELEASE", "ALLOW", `Emergency stop released by ${triggeredBy}`, triggeredBy);
}
