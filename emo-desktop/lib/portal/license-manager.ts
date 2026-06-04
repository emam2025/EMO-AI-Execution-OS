import { createHash } from "crypto";

export interface Company {
  id: string;
  name: string;
  licenseKey: string;
  expiresAt: number;
  features: string[];
  status: "active" | "suspended" | "expired";
  maxAgents: number;
  lastActivity: number | null;
  createdAt: number;
}

export interface LicenseValidation {
  valid: boolean;
  reason?: string;
  remainingSeats?: number;
  expiresAt?: number;
  features?: string[];
}

const companies = new Map<string, Company>();

export function registerCompany(name: string, licenseKey: string, options?: { maxAgents?: number; features?: string[]; durationDays?: number }): { company: Company; created: boolean; reason?: string } {
  if (!name || name.length < 2) {
    return { company: null as unknown as Company, created: false, reason: "company name too short" };
  }
  if (!licenseKey || licenseKey.length < 8) {
    return { company: null as unknown as Company, created: false, reason: "invalid license key" };
  }

  for (const existing of companies.values()) {
    if (existing.name === name) {
      return { company: null as unknown as Company, created: false, reason: "company name already registered" };
    }
  }

  const id = createHash("sha256").update(name + ":" + licenseKey).digest("hex").slice(0, 12);
  const now = Date.now();
  const durationDays = options?.durationDays ?? 90;
  const company: Company = {
    id,
    name,
    licenseKey,
    expiresAt: now + durationDays * 24 * 60 * 60 * 1000,
    features: options?.features ?? ["pilot", "dashboard", "feedback"],
    status: "active",
    maxAgents: options?.maxAgents ?? 10,
    lastActivity: null,
    createdAt: now,
  };

  companies.set(id, company);
  return { company, created: true };
}

export function validateLicense(licenseKey: string): LicenseValidation {
  for (const company of companies.values()) {
    if (company.licenseKey !== licenseKey) continue;

    if (company.status === "suspended") {
      return { valid: false, reason: "license suspended" };
    }
    if (company.status === "expired") {
      return { valid: false, reason: "license expired" };
    }
    if (Date.now() > company.expiresAt) {
      company.status = "expired";
      return { valid: false, reason: "license expired" };
    }

    const activeCount = countActiveAgents(company.id);
    const remainingSeats = Math.max(0, company.maxAgents - activeCount);

    return {
      valid: true,
      remainingSeats,
      expiresAt: company.expiresAt,
      features: [...company.features],
    };
  }

  return { valid: false, reason: "license key not found" };
}

function countActiveAgents(companyId: string): number {
  return 0;
}

export function listActivePilots(): Company[] {
  const now = Date.now();
  const active: Company[] = [];
  for (const company of companies.values()) {
    if (company.status === "active" && now <= company.expiresAt) {
      active.push({ ...company });
    }
  }
  return active.sort((a, b) => b.createdAt - a.createdAt);
}

export function getCompany(companyId: string): Company | undefined {
  return companies.get(companyId);
}

export function getAllCompanies(): Company[] {
  return Array.from(companies.values()).map((c) => ({ ...c }));
}

export function updateCompanyStatus(companyId: string, status: "active" | "suspended" | "expired"): { updated: boolean; reason?: string } {
  const company = companies.get(companyId);
  if (!company) {
    return { updated: false, reason: "company not found" };
  }
  company.status = status;
  return { updated: true };
}

export function recordActivity(companyId: string): void {
  const company = companies.get(companyId);
  if (company) {
    company.lastActivity = Date.now();
  }
}

export function clearAllCompanies(): void {
  companies.clear();
}

export function getCompanyCounts(): { total: number; active: number; suspended: number; expired: number } {
  const now = Date.now();
  let total = 0, active = 0, suspended = 0, expired = 0;
  for (const c of companies.values()) {
    total++;
    if (c.status === "suspended") suspended++;
    else if (c.status === "expired" || now > c.expiresAt) expired++;
    else active++;
  }
  return { total, active, suspended, expired };
}
