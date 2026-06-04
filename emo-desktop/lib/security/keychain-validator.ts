/**
 * Keychain Validator — OS Keychain enforcement & audit
 *
 * Ensures:
 *   1. No API keys are stored outside the OS keychain (plaintext scan)
 *   2. tauri-plugin-keyring is active in Tauri configuration
 *   3. All key operations are logged to the audit trail
 *
 * BLOCK policy: if any plaintext key pattern is found, the validator
 * rejects the build / startup.
 */
import * as fs from "fs";
import * as path from "path";

const API_KEY_PATTERNS = [
  /sk-[a-zA-Z0-9]{20,}/,          // OpenAI
  /sk-ant-[a-zA-Z0-9]{20,}/,      // Anthropic
  /AIza[0-9A-Za-z_-]{35,}/,       // Google Gemini
  /gsk_[a-zA-Z0-9]{20,}/,         // Groq
  /Bearer\s+[a-zA-Z0-9_-]{20,}/i, // Generic Bearer
  /ghp_[a-zA-Z0-9]{36,}/,         // GitHub PAT
];

const SCAN_EXCLUDE = ["node_modules", ".git", "target", "dist", ".next", "__pycache__"];

export interface KeychainAuditEntry {
  timestamp: number;
  action: "store" | "retrieve" | "delete" | "validate" | "block";
  provider: string;
  result: "success" | "failure" | "blocked";
  detail?: string;
}

const auditLog: KeychainAuditEntry[] = [];

export function getAuditLog(): readonly KeychainAuditEntry[] {
  return auditLog;
}

export function clearAuditLog(): void {
  auditLog.length = 0;
}

function recordAudit(
  action: KeychainAuditEntry["action"],
  provider: string,
  result: KeychainAuditEntry["result"],
  detail?: string,
): void {
  auditLog.push({ timestamp: Date.now(), action, provider, result, detail });
}

/**
 * Scans a directory tree for plaintext API key patterns.
 * Returns an array of findings with file path, line number, and matched pattern.
 */
export function scanForPlaintextKeys(
  rootDir: string,
  exclude: string[] = SCAN_EXCLUDE,
): { file: string; line: number; pattern: string; snippet: string }[] {
  const findings: { file: string; line: number; pattern: string; snippet: string }[] = [];

  function walk(dir: string): void {
    let entries: string[];
    try {
      entries = fs.readdirSync(dir);
    } catch {
      return;
    }
    for (const entry of entries) {
      const fullPath = path.join(dir, entry);
      if (exclude.some((e) => fullPath.includes(e))) continue;
      try {
        const stat = fs.statSync(fullPath);
        if (stat.isDirectory()) {
          walk(fullPath);
        } else if (stat.isFile() && !fullPath.endsWith(".lock")) {
          const ext = path.extname(fullPath);
          if ([".env", ".json", ".toml", ".yaml", ".yml", ".ini", ".conf", ".cfg", ".txt", ".md", ".ts", ".tsx", ".js", ".jsx"].includes(ext) || fullPath.endsWith(".env")) {
            const content = fs.readFileSync(fullPath, "utf-8");
            const lines = content.split("\n");
            for (let i = 0; i < lines.length; i++) {
              for (const pattern of API_KEY_PATTERNS) {
                const match = lines[i].match(pattern);
                if (match) {
                  findings.push({
                    file: fullPath,
                    line: i + 1,
                    pattern: pattern.source.slice(0, 30),
                    snippet: lines[i].trim().slice(0, 80),
                  });
                }
              }
            }
          }
        }
      } catch {
        // Permission errors etc. — skip
      }
    }
  }

  walk(rootDir);
  return findings;
}

/**
 * Verifies tauri-plugin-keyring is active in tauri.conf.json and Cargo.toml.
 */
export function ensureTauriKeyringActive(projectRoot: string): boolean {
  const configPath = path.join(projectRoot, "src-tauri", "tauri.conf.json");
  const cargoPath = path.join(projectRoot, "src-tauri", "Cargo.toml");

  let valid = true;

  // Check tauri.conf.json
  if (fs.existsSync(configPath)) {
    const config = fs.readFileSync(configPath, "utf-8");
    if (!config.includes("keyring")) {
      recordAudit("validate", "system", "failure", "tauri.conf.json missing keyring plugin config");
      valid = false;
    }
  }

  // Check Cargo.toml
  if (fs.existsSync(cargoPath)) {
    const cargo = fs.readFileSync(cargoPath, "utf-8");
    if (!cargo.includes("keyring") && !cargo.includes("tauri-plugin-keyring")) {
      recordAudit("validate", "system", "failure", "Cargo.toml missing keyring dependency");
      valid = false;
    }
  }

  if (valid) {
    recordAudit("validate", "system", "success", "OS Keychain plugin verified");
  }

  return valid;
}

/**
 * Verifies that no API keys are stored outside the OS keychain in the project.
 * Returns true if clean, false if plaintext keys found.
 */
export function verifyKeychainOnly(projectRoot: string): boolean {
  const findings = scanForPlaintextKeys(projectRoot);
  if (findings.length > 0) {
    for (const f of findings) {
      recordAudit("validate", "plaintext-scan", "blocked", `${f.file}:${f.line}`);
    }
    return false;
  }
  recordAudit("validate", "plaintext-scan", "success", "No plaintext keys found");
  return true;
}

/**
 * Records a keychain operation in the audit log.
 */
export function auditKeyStorage(
  action: KeychainAuditEntry["action"],
  provider: string,
  result: KeychainAuditEntry["result"],
  detail?: string,
): void {
  recordAudit(action, provider, result, detail);
}
