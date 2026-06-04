import type { Action, PolicyConfig } from "./policy-engine";

export interface RiskProfile {
  riskScore: number;
  impactScore: number;
  confidenceScore: number;
  factors: RiskFactor[];
}

export interface RiskFactor {
  name: string;
  weight: number;
  value: number;
  contribution: number;
}

const CATEGORY_BASE_RISK: Record<string, { risk: number; impact: number }> = {
  read: { risk: 0.1, impact: 0.1 },
  write: { risk: 0.3, impact: 0.3 },
  execute: { risk: 0.5, impact: 0.6 },
  deploy: { risk: 0.7, impact: 0.8 },
  delete: { risk: 0.8, impact: 0.9 },
  config_change: { risk: 0.5, impact: 0.6 },
  network_access: { risk: 0.6, impact: 0.5 },
  privilege_escalation: { risk: 0.9, impact: 0.95 },
  data_export: { risk: 0.6, impact: 0.7 },
  system_shutdown: { risk: 0.95, impact: 0.95 },
};

export function calculateRiskScores(action: Action, config: PolicyConfig): RiskProfile {
  const base = CATEGORY_BASE_RISK[action.category] || { risk: 0.3, impact: 0.3 };

  const levelMultiplier = config.industrialLevel / 4;

  const resourceFactor = {
    name: "resource_utilization",
    weight: 0.15,
    value: Math.min(1, (100 - config.resourceLimits.maxCpuPercent) / 100),
    contribution: 0,
  };
  resourceFactor.contribution = resourceFactor.weight * resourceFactor.value;

  const categoryFactor = {
    name: "category_risk",
    weight: 0.4,
    value: base.risk,
    contribution: 0,
  };
  categoryFactor.contribution = categoryFactor.weight * categoryFactor.value;

  const approvalFactor = {
    name: "approval_coverage",
    weight: 0.15,
    value: config.approvalPolicy.dualApproval ? 0.2 : config.approvalPolicy.singleApproval ? 0.4 : 0.8,
    contribution: 0,
  };
  approvalFactor.contribution = approvalFactor.weight * approvalFactor.value;

  const auditFactor = {
    name: "audit_strength",
    weight: 0.15,
    value: config.auditRequirements.tamperProof ? 0.3 : 0.7,
    contribution: 0,
  };
  auditFactor.contribution = auditFactor.weight * auditFactor.value;

  const levelFactor = {
    name: "industrial_level",
    weight: 0.15,
    value: levelMultiplier,
    contribution: 0,
  };
  levelFactor.contribution = levelFactor.weight * levelFactor.value;

  const factors = [resourceFactor, categoryFactor, approvalFactor, auditFactor, levelFactor];

  const riskScore = Math.min(1, factors.reduce((sum, f) => sum + f.contribution, 0));
  const impactScore = Math.min(1, base.impact * (0.5 + levelMultiplier * 0.5));
  const confidenceScore = Math.max(0, 1 - riskScore * 0.2);

  return { riskScore: round(riskScore), impactScore: round(impactScore), confidenceScore: round(confidenceScore), factors };
}

function round(n: number): number {
  return Math.round(n * 1000) / 1000;
}

export function calculateLatency(): number {
  return 5;
}
