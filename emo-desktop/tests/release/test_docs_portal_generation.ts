import { describe, it, expect } from "vitest";
import * as fs from "fs";
import * as path from "path";

describe("TestDocsPortalConsistency", () => {
  const portalDir = path.resolve(__dirname, "../../docs/portal");
  const guidesDir = path.resolve(__dirname, "../../docs/guides");

  it("should have all required portal files", () => {
    expect(fs.existsSync(path.join(portalDir, "index.html"))).toBe(true);
    expect(fs.existsSync(path.join(portalDir, "search.ts"))).toBe(true);
    expect(fs.existsSync(path.join(portalDir, "export-all.sh"))).toBe(true);
  });

  it("should have all 5 guides present as markdown files", () => {
    const guides = ["user-guide.md", "admin-guide.md", "security-guide.md", "api-guide.md", "deployment-guide.md"];
    for (const guide of guides) {
      expect(fs.existsSync(path.join(guidesDir, guide))).toBe(true);
    }
  });

  it("should reference all 5 guides in index.html", () => {
    const html = fs.readFileSync(path.join(portalDir, "index.html"), "utf8");
    expect(html).toContain("user-guide");
    expect(html).toContain("admin-guide");
    expect(html).toContain("security-guide");
    expect(html).toContain("api-guide");
    expect(html).toContain("deployment-guide");
    expect(html).toContain("v1.0.0");
  });

  it("should have search.ts that indexes all guides", () => {
    const ts = fs.readFileSync(path.join(portalDir, "search.ts"), "utf8");
    expect(ts).toContain("user-guide");
    expect(ts).toContain("admin-guide");
    expect(ts).toContain("security-guide");
    expect(ts).toContain("api-guide");
    expect(ts).toContain("deployment-guide");
    expect(ts).toContain("buildSearchIndex");
  });

  it("should have export-all.sh that references all 5 guides", () => {
    const sh = fs.readFileSync(path.join(portalDir, "export-all.sh"), "utf8");
    expect(sh).toContain("user-guide.md");
    expect(sh).toContain("admin-guide.md");
    expect(sh).toContain("security-guide.md");
    expect(sh).toContain("api-guide.md");
    expect(sh).toContain("deployment-guide.md");
  });
});
