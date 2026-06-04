import type { PolicyConfig, IndustrialLevel } from "./policy-engine";
import { applyIndustrialLevel } from "./policy-engine";

export interface ComplianceProfile {
  id: string;
  name: string;
  standard: string;
  version: string;
  industrialLevel: IndustrialLevel;
  overrides: Partial<PolicyConfig>;
  auditRequirements: string[];
  dataRetentionPolicy: { maxDays: number; autoPurge: boolean; encryptAtRest: boolean };
}

const PROFILES_DIR = "../../config/compliance";

const profileCache = new Map<string, ComplianceProfile>();
let activeProfileId: string | null = null;

export function getActiveProfileId(): string | null {
  return activeProfileId;
}

export async function loadComplianceProfile(profileId: string): Promise<ComplianceProfile> {
  if (profileCache.has(profileId)) {
    return profileCache.get(profileId)!;
  }

  const path = `${PROFILES_DIR}/${profileId}.json`;
  try {
    const mod = await import(/* @vite-ignore */ path);
    const profile = mod.default || mod;
    profileCache.set(profileId, profile);
    return profile;
  } catch {
    throw new Error(`Compliance profile "${profileId}" not found at ${path}`);
  }
}

export function applyProfile(profile: ComplianceProfile): PolicyConfig {
  activeProfileId = profile.id;
  const baseConfig = applyIndustrialLevel(profile.industrialLevel);

  const merged: PolicyConfig = {
    ...baseConfig,
    ...profile.overrides,
    resourceLimits: { ...baseConfig.resourceLimits, ...(profile.overrides.resourceLimits || {}) },
    toolPermissions: { ...baseConfig.toolPermissions, ...(profile.overrides.toolPermissions || {}) },
    auditRequirements: { ...baseConfig.auditRequirements, ...(profile.overrides.auditRequirements || {}) },
    approvalPolicy: { ...baseConfig.approvalPolicy, ...(profile.overrides.approvalPolicy || {}) },
    dataRetention: { ...baseConfig.dataRetention, ...(profile.overrides.dataRetention || {}) },
  };

  return merged;
}

export function getLoadedProfileIds(): string[] {
  return Array.from(profileCache.keys());
}

export function clearProfileCache(): void {
  profileCache.clear();
  activeProfileId = null;
}

export function validateProfileCompatibility(profiles: ComplianceProfile[]): { compatible: boolean; conflicts: string[] } {
  const conflicts: string[] = [];
  for (let i = 0; i < profiles.length; i++) {
    for (let j = i + 1; j < profiles.length; j++) {
      if (profiles[i].industrialLevel !== profiles[j].industrialLevel) {
        conflicts.push(`Level mismatch: "${profiles[i].id}" (L${profiles[i].industrialLevel}) vs "${profiles[j].id}" (L${profiles[j].industrialLevel})`);
      }
    }
  }
  return { compatible: conflicts.length === 0, conflicts };
}
