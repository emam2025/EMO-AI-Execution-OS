# Product Readiness Audit — EXEC-DIRECTIVE-P0

**Date:** 2026-06-01 (Updated: 2026-06-26)
**Project:** EMO AI
**Objective:** Comprehensive product readiness audit before any new development

> **⚠️ Historical Note (Updated 2026-06-26):** This audit was performed on 2026-06-01.
> Several findings have been resolved since then:
> - `run_agent`: 🔴 MOCKED → ✅ **CONNECTED** (fixed in RC18 via ureq HTTP POST)
> - Default auth: OFF → **ENFORCED** (P0-04)
> - Audit trail: not initialized → **EMO_AUDIT_SIGNING_KEY** enforced (P0-03)
> - EmoRuntime: not wired → **CompositionRoot** in main.py (P0-01)
> - `core/interfaces/runtime/`: 6 broken re-export shims **deleted** (P0-05)
> - `capabilities/default.json`: **created** (Tauri v2 IPC requirement)
> - Icons: PNG only → **ICNS + ICO + multi-res PNG** added
>
> This document retains the original findings for historical reference.
> For current status, see `CHANGELOG.md` and the P0 commit log.

---

## Executive Summary

| Area | Actual Maturity | Risk |
|------|-----------------|------|
| Rust Bridge (IPC) | 80% — 5/5 Commands connected. run_agent fixed in RC18 | 🟡 Medium |
| Packaging Pipeline | 40% — Scripts exist but outside CI and no signing certificates | 🔴 BLOCKER |
| Security Deployment | 42/100 — No binary signing, XOR "encryption", unencrypted DB | 🟡 High |
| Industrial Readiness | 25% — Audit READY, rest FOUNDATION/PARTIAL | 🟡 Medium |

> **Update (2026-06-26):** `run_agent` was **fixed in RC18** (post-audit).
> The current code sends a real HTTP POST to `/api/ai/run` via `ureq` with 300s timeout,
> error handling, and response parsing. See `emo-desktop/src-tauri/src/commands.rs`.

---

## 1. Rust Bridge Audit

### Current Structure
```
emo-desktop/src-tauri/
├── src/
│   ├── main.rs          (calls emo_desktop::run())
│   ├── lib.rs           (Builder + 5 Commands)
│   └── commands.rs      (All Commands)
├── tauri.conf.json
├── Cargo.toml
└── icons/
```

### Registered Rust Commands

| Command | Status | What it does |
|---------|--------|--------------|
| `start_runtime` | ✅ CONNECTED | Runs Python binary (Nuitka/PyInstaller) as child process on port 8080 |
| `stop_runtime` | ✅ CONNECTED | Kills child process by PID |
| `get_runtime_status` | ✅ CONNECTED | Checks child process health via `try_wait()` |
| `set_api_key` | ✅ CONNECTED | Stores API key in OS keychain via `keyring` crate |
| `run_agent` | ✅ **CONNECTED** (Fixed RC18) | HTTP POST to `/api/ai/run` via `ureq` (300s timeout, error handling, response parsing) |

### Frontend invoke() Calls

| Function | Command | Status |
|----------|---------|--------|
| `RuntimeClient.startRuntime()` | `invoke("start_runtime")` | ✅ Matching |
| `RuntimeClient.stopRuntime(pid)` | `invoke("stop_runtime", { pid })` | ✅ Matching |
| `RuntimeClient.getRuntimeStatus()` | `invoke("get_runtime_status")` | ✅ Matching |
| `RuntimeClient.setApiKey(provider, key)` | `invoke("set_api_key", { provider, key })` | ✅ Matching |
| `RuntimeClient.runAgent(task)` | `invoke("run_agent", { task })` | ⚠️ Matching but Placeholder |
| `invokeKeyringSave()` | `invoke("plugin:keyring|set_password")` | ❌ **MISSING** — No Rust handler |
| `invokeKeyringGet()` | `invoke("plugin:keyring|get_password")` | ❌ **MISSING** |
| `invokeKeyringDelete()` | `invoke("plugin:keyring|delete_password")` | ❌ **MISSING** |

### RUB_BRIDGE_STATUS

| Category | Count |
|----------|-------|
| **CONNECTED** (real command → core) | **4** |
| **MOCKED** (command exists but does nothing) | **1** (run_agent) |
| **MISSING** (frontend call without Rust handler) | **3** (plugin:keyring) |
| **ORPHAN** (old code in emo-desktop/tauri/) | **7** (stream_events, get_trace, ...) |

### Rust Bridge Issues

| # | Risk | Description |
|---|------|-------------|
| 🟢 C1 | **RESOLVED (RC18)** | `run_agent` now sends HTTP POST to `/api/ai/run` via `ureq` with 300s timeout. Fixed between audit date (2026-06-01) and RC18 (2026-06-21) |
| 🔴 C2 | **CRITICAL** | keyring has two conflicting implementations: `commands.rs` uses `keyring` crate directly, and `keyring-adapter.ts` calls non-existent `plugin:keyring` |
| 🔴 C3 | **CRITICAL** | `capabilities.json` is empty — Tauri v2 may block all custom commands |
| 🟡 H1 | Port 8080 Hardcoded | No dynamic port assignment |
| 🟡 H2 | WebSocket URL Hardcoded | `ws://localhost:8080` not bound to actual session |
| 🟡 H3 | session_token unused | Generated in `start_runtime` but never verified |
| 🟡 M1 | tokio unused | Present in Cargo.toml but no async commands |
| 🟡 M2 | Runtime death without recovery | No auto-restart, no user notification |
| 🟡 M3 | CSP blocks WebSocket | `default-src 'self'` blocks `ws://localhost:8080` |

---

## 2. Packaging Audit

### PACKAGING_READINESS

| Platform | Maturity | Details |
|----------|----------|---------|
| **macOS (DMG)** | **55%** | Scripts exist but signingIdentity = null, no entitlements, no notarization |
| **Windows (MSI/EXE)** | **65%** | WiX + NSIS configured, service registration exists, but no PFX certificate |
| **Linux (AppImage)** | **50%** | Script exists but depends on `appimagetool` not guaranteed in CI |
| **CI/CD Pipeline** | **40%** | Scripts well-crafted but outside CI — no automatic Build for any platform |

### What Actually Exists
- ✅ Complete Tauri v2 scaffold with 5 IPC commands
- ✅ Build scripts for 3 platforms: `build-installers.sh`, `secure-build.sh`
- ✅ Signing scripts for 3 platforms: codesign, signtool, gpg
- ✅ Auto-updater configured with endpoint + pubkey slot + manifest generator
- ✅ `verify-signatures.sh` with fail-on-mismatch
- ✅ Leakage scanner (`leakage-scanner.sh`) to prevent API key leaks
- ✅ Complete release system: `release_state_machine.py`, `release_validator.py`, `certificate_engine.py`
- ✅ 51 distribution tests across 7 files

### Critical Gaps

| # | Risk | Description |
|---|------|-------------|
| 🔴 P0-1 | No CI workflow for Desktop builds | No installer will be produced automatically |
| 🔴 P0-2 | macOS signingIdentity = null | Un-signed DMG → Gatekeeper blocks installation |
| 🔴 P0-3 | No icon.icns nor icon.ico | DMG/EXE without icons |
| 🔴 P0-4 | ed25519 pubkey Placeholder | Auto-updater signature not real — updates can be forged |
| 🔴 P0-5 | No Release Workflow | No `on: release` trigger |
| 🔴 P0-6 | Signing workflow outside `.github/workflows/` | Will never execute |
| 🟡 P1-1 | No macOS entitlements | Hardened runtime does not work correctly |
| 🟡 P1-2 | No notarization credentials | App will show "Unidentified Developer" |
| 🟡 P1-3 | SHA-256 placeholders | `SHA256_PLACEHOLDER` in manifests |
| 🟡 P1-4 | build-installers.sh produces silent placeholders | May produce non-functional installers without warning |
| 🟡 P1-5 | deb without dependencies | Incomplete integration |
| 🟡 P1-6 | Duplicate tauri.conf.json | `emo-desktop/tauri/` vs `emo-desktop/src-tauri/` |
| 🟢 P2-1 | No ARM64 | Only x86_64 configured |
| 🟢 P2-2 | Update server not deployed | `releases.emo-ai.dev` does not exist |

---

## 3. Security Deployment Audit

### DEPLOYMENT_SECURITY_SCORE: **42/100**

| Category | Weight | Score |
|----------|--------|-------|
| Keychain/Credential Storage | 25% | 18/25 — vault exists but XOR "encryption" |
| Update Signing | 20% | 8/20 — no binary signing at all |
| Binary Protection | 20% | 5/20 — exposed Python script, no obfuscation |
| Secrets Handling | 20% | 8/20 — `.env` exposed, SQLite unencrypted |
| Runtime Security | 15% | 13/20 — Excellent sandbox but no OS-level seccomp |

### Critical Security Gaps

| # | Risk | Details |
|---|------|---------|
| 🔴 S1 | **HIGH** — Python vault uses XOR "encryption" | `core/runtime/secrets/vault.py` uses XOR obfuscation documented as "NOT production-grade" |
| 🔴 S2 | **HIGH** — No binary signing | macOS codesign, Windows authenticode, GPG signing all missing |
| 🔴 S3 | **HIGH** — SQLite not encrypted | `emo_ai.db` without encryption — contains audit logs and sensitive data |
| 🟡 S4 | **MEDIUM** — `.env` in working directory | API keys for 6 services + JWT secret exposed |
| 🟡 S5 | **MEDIUM** — No OS sandbox | No seccomp, AppArmor, SELinux — only software sandbox |
| 🟡 S6 | **MEDIUM** — No HSM/TPM | Secrets in Python memory extractable |

---

## 4. Industrial Readiness Audit

| Area | Status | Details |
|------|--------|---------|
| **Permission Profiles** | 🟠 **FOUNDATION** | RBAC + 4 Industrial Levels exist, but no HIPAA/FedRAMP/FERPA profiles |
| **Risk Policies** | 🟡 **PARTIAL** | Risk engine in TS and Python but no formal risk matrix, no unified model |
| **Human Approval Gates** | 🟡 **PARTIAL** | Single/dual approval + emergency stop, but no UI nor escalation matrix |
| **Audit Trails** | 🟢 **READY** | Chain-linked, HMAC-SHA256 signed, tamper-evident — strongest area |
| **Recovery Procedures** | 🟡 **PARTIAL** | DR framework + failover + rollback exist, but no operational DR plan |

### Industrial Gaps

| # | Gap | Impact |
|---|-----|--------|
| 1 | No Sector-Specific Profiles | HIPAA/FedRAMP/PCI-DSS/FERPA missing |
| 2 | Separate audit logs | Python backend and TS frontend not linked |
| 3 | No UI for approvals | Approval Gates exist only in CLI/Code |
| 4 | No Risk Register | No risk acceptance/tracking/visualization |
| 5 | No DR Operational Plan | No RPO/RTO/Backup Schedule |
| 6 | In-memory state | RBAC + audit trail lost on restart |
| 7 | Duplicate risk engine | Two different algorithms in Python and TS |

---

## 5. Final Maturity Assessment (Corrected)

| Area | Previous Estimate | Actual Estimate | Difference |
|------|-------------------|-----------------|------------|
| Runtime | 90-95% | 90-95% | ✅ Correct |
| Memory | 85-90% | 85-90% | ✅ Correct |
| Skills | 80-90% | 80-90% | ✅ Correct |
| Cognitive | 80-90% | 80-90% | ✅ Correct |
| Governance | 75-85% | 75-85% | ✅ Correct |
| Security | 85-90% | **42/100** (Deployment) | ❌ Was core-only estimate |
| Desktop UX | 75-85% | **70%** | ⚠️ Close but run_agent broken |
| Packaging | 40-60% | **40%** | ✅ Matching |
| Industrial Readiness | 30-50% | **25%** | ❌ Lower than estimate |
| Public Release Readiness | 60-75% | **35%** | ❌ Much lower — run_agent breaks product |

---

## 6. Recommendations — New Priority Order

### Priority #1: Fix Rust Bridge (Blocks Launch)
| Task | Effort | Risk if not done |
|------|--------|------------------|
| 1.1 Implement real `run_agent` — HTTP POST to core | 2-3 days | Product does not work |
| 1.2 Install `tauri-plugin-keyring` + wire it | 1 day | API key storage silently fails |
| 1.3 Create correct `capabilities.json` | 0.5 day | Tauri may block all Commands |
| 1.4 Remove/unify duplicate `emo-desktop/tauri/` | 0.5 day | Confusing maintenance |

### Priority #2: Packaging Pipeline (For Beta Launch)
| Task | Effort | Risk if not done |
|------|--------|------------------|
| 2.1 CI workflow for Desktop builds | 2-3 days | No automatic installers |
| 2.2 Create icon.icns + icon.ico | 0.5 day | App without icons |
| 2.3 Move signing workflow to `.github/` | 0.5 day | Nothing will be signed |
| 2.4 Real ed25519 key pair | 0.5 day | Fake auto-updater signing |
| 2.5 macOS entitlements | 0.5 day | Gatekeeper blocks |
| 2.6 First Actual Release Build | 1 day | Verify full workflow |

### Priority #3: Industrial Hardening (For Final Product)
| Task | Effort |
|------|--------|
| 3.1 Switch XOR → AES-GCM in vault | 1 day |
| 3.2 Encrypt SQLite at rest | 2 days |
| 3.3 Sector Profiles (HIPAA, FedRAMP, FERPA, PCI-DSS, SOX) | 3-5 days |
| 3.4 Unify Risk Engines (Python + TS) | 2 days |
| 3.5 Approval Workflow UI | 3-5 days |
| 3.6 Centralized Audit Aggregation | 2 days |
| 3.7 DR Operational Plan + Backup Scheduling | 2 days |

### Priority #4: Pilot Program
| Task | Effort |
|------|--------|
| 4.1 Set up staging environment | 1 day |
| 4.2 Crash Report Pipeline | 2 days |
| 4.3 UX Friction Tracking | 1 day |
| 4.4 Invite 10-20 users | 1 week |

---

## Summary

```
Verdict: Project cannot be launched for pilot testing currently
═════════════════════════════════════════

Direct cause: run_agent does not work
Systemic cause: No automatic build pipeline
Security cause: No binary signing and no real encryption

Minimum requirements for Pilot:
1. ✅ run_agent works → sends HTTP to actual core
2. ✅ Desktop Build in CI → produces signed DMG
3. ✅ keychain stores API keys correctly
4. ✅ Tauri capabilities.json not empty

After these 4, Pilot can start with 10 users.
Industrial Hardening and Sector Profiles come after Pilot.
```

---

*End of Report — EXEC-DIRECTIVE-P0-PRODUCT-READINESS-AUDIT*
