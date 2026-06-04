import { describe, it, expect } from "vitest";

interface ChecklistCriterion {
  id: string;
  label: string;
  type: "metric" | "boolean" | "survey";
  target: number | boolean;
  weight: number;
}

interface SectorChecklist {
  sector: string;
  name: string;
  criteria: ChecklistCriterion[];
  successThreshold: number;
}

const CHECKLIST_FILES = [
  "software-house", "factory", "logistics", "consulting", "internal-team",
];

function validateChecklist(cl: SectorChecklist): string[] {
  const errors: string[] = [];
  if (!cl.sector) errors.push("missing sector");
  if (!cl.name) errors.push("missing name");
  if (!cl.criteria || cl.criteria.length === 0) errors.push("no criteria");
  if (cl.successThreshold < 0 || cl.successThreshold > 1) errors.push("invalid success threshold");

  const totalWeight = cl.criteria.reduce((s, c) => s + c.weight, 0);
  if (totalWeight !== 100) errors.push(`total weight ${totalWeight} !== 100`);

  const ids = new Set<string>();
  for (const c of cl.criteria) {
    if (!c.id) errors.push("criteria missing id");
    if (ids.has(c.id)) errors.push(`duplicate id: ${c.id}`);
    ids.add(c.id);
    if (!["metric", "boolean", "survey"].includes(c.type)) errors.push(`invalid type: ${c.type}`);
    if (c.weight <= 0 || c.weight > 100) errors.push(`invalid weight: ${c.weight}`);
  }

  return errors;
}

describe("Sector Checklists — Validation", () => {
  it("should have exactly 5 sector profiles", () => {
    expect(CHECKLIST_FILES.length).toBe(5);
  });

  it("should validate software-house checklist structure", async () => {
    const mod = await import("../../config/sector-checklists/software-house.json");
    const checklist: SectorChecklist = mod.default || mod;
    const errors = validateChecklist(checklist);
    expect(errors).toHaveLength(0);
    expect(checklist.sector).toBe("software-house");
  });

  it("should validate factory checklist", async () => {
    const mod = await import("../../config/sector-checklists/factory.json");
    const checklist: SectorChecklist = mod.default || mod;
    const errors = validateChecklist(checklist);
    expect(errors).toHaveLength(0);
    expect(checklist.sector).toBe("factory");
  });

  it("should validate logistics checklist", async () => {
    const mod = await import("../../config/sector-checklists/logistics.json");
    const checklist: SectorChecklist = mod.default || mod;
    const errors = validateChecklist(checklist);
    expect(errors).toHaveLength(0);
    expect(checklist.sector).toBe("logistics");
  });

  it("should validate consulting checklist", async () => {
    const mod = await import("../../config/sector-checklists/consulting.json");
    const checklist: SectorChecklist = mod.default || mod;
    const errors = validateChecklist(checklist);
    expect(errors).toHaveLength(0);
    expect(checklist.sector).toBe("consulting");
  });

  it("should validate internal-team checklist", async () => {
    const mod = await import("../../config/sector-checklists/internal-team.json");
    const checklist: SectorChecklist = mod.default || mod;
    const errors = validateChecklist(checklist);
    expect(errors).toHaveLength(0);
    expect(checklist.sector).toBe("internal-team");
  });
});
