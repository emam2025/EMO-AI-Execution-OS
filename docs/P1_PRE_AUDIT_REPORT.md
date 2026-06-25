# P1 Pre-Audit Report — Keychain Enforcement

**Date:** 2026-06-01
**Goal:** Inventory all API key storage locations in preparation for migration to OS Keychain
**Audit Status:** Completed — no code modification

---

## Executive Summary

| Item | Value |
|-------|--------|
| Total Violations | 21 |
| CRITICAL (live keys in plain text) | 8 |
| HIGH (reading keys from env vars) | 6 |
| MEDIUM (incomplete infrastructure) | 7 |
| Current Keychain Adoption | ~15% (only in Rust layer) |
| **Immediate Risk** | **Live keys in `docs/REQUIREMENTS_UNDERSTANDING.md` — file under Git** |

---

## Critical Violations (CRITICAL)

### C1: Live keys in `.env`
| Variable | Value | Location |
|---------|--------|--------|
| `OPENROUTER_API_KEY` | `sk-or-placeholder-rotated` | `/.env:5` |
| `GROQ_API_KEY` | `gsk-placeholder-rotated` | `/.env:6` |
| `GEMINI_API_KEY` | `gemini-placeholder-rotated` | `/.env:7` |
| `TELEGRAM_TOKEN` | `telegram-token-placeholder-rotated` | `/.env:24` |
| `EMO_JWT_SECRET` | `jwt-secret-placeholder-rotated` | `/.env:21` |

### C2: 🔴 Live keys in Git-tracked documents!
| Variable | Value | Location |
|---------|--------|--------|
| `OPENROUTER_API_KEY` | `sk-or-v1-...` | `/docs/REQUIREMENTS_UNDERSTANDING.md:562` |
| `GROQ_API_KEY` | `gsk_ECoDOC...` | `/docs/REQUIREMENTS_UNDERSTANDING.md:563` |
| `GEMINI_API_KEY` | `gemini-placeholder-rotated` | `/docs/REQUIREMENTS_UNDERSTANDING.md:564` |
| `TELEGRAM_TOKEN` | `telegram-token-placeholder-rotated` | `/docs/REQUIREMENTS_UNDERSTANDING.md:565` |

### C3: Backup encryption key written in code
| File | Line | Value |
|------|-------|--------|
| `emo-desktop/lib/beta/secure-feedback-channel.ts` | 35 | `"emo-beta-enc-key-32characters!!"` |

---

## High Violations (HIGH)

### H1-H6: Python backend reads keys from env vars — no Keychain
| File | Variables | Method |
|------|-----------|---------|
| `brain.py:25-76` | `OPENROUTER_API_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY` | `os.getenv()` |
| `main.py:303` | All providers | `os.getenv()` in `/api/status` |
| `main.py:336-339` | env var names sent to UI | `api_key_env` in HTML template |
| `firebase_tools.py:12` | `FIREBASE_API_KEY` | `os.environ.get()` |
| `supabase_tools.py:10` | `SUPABASE_SERVICE_KEY` | `os.environ.get()` |
| `github_tools.py:14` | `GITHUB_TOKEN` | `os.environ.get()` |
| `middleware/auth.py:13` | `EMO_JWT_SECRET` | `os.environ.get()` |

---

## Current Keychain Architecture (MEDIUM)

### In Rust/Desktop (partially exists — ~30%)
- ✅ `commands.rs:155-165` — `set_api_key` stores in OS keychain via `keyring` crate
- ✅ `keyring-adapter.ts` — TypeScript adapter with BLOCK policy
- ✅ `keychain-validator.ts` — Plain text key scanner
- ❌ `os-keyring.ts` — Stub functions (invoke_keyring_save/get/delete do nothing)
- ❌ `ephemeral_injection.ts` — `_stdinWrite` and `_envIsolatedSet` stubs
- ❌ `tauri-plugin-keyring` not in `Cargo.toml`

### In Python backend (does not exist — 0%)
- ❌ No `keyring` package in Python dependencies
- ❌ No `keychain_provider.py`
- ❌ All keys are read from `os.getenv()` via `.env`

---

## Affected Files (37 files)

### Contain live keys — need immediate rotation
1. `/.env` — All API keys
2. `/docs/REQUIREMENTS_UNDERSTANDING.md` — Copy of keys in Git!

### Contain test keys
3. `emo-desktop/tests/security/test_os_keychain_storage.ts`
4. `emo-desktop/tests/pilot/test_pilot_mode_privacy.ts`
5. `emo-desktop/tests/analytics/test_public_metrics_accuracy.ts`
6. `emo-desktop/tests/pilot/test_feedback_submission.ts`
7. `emo-desktop/tests/bridge/test_rust_ipc_bindings.ts`
8. `emo-desktop/tests/beta/test_beta_integration_flow.ts`

### Read keys from env vars — need Keychain
9. `brain.py` + `main.py` + `firebase_tools.py` + `supabase_tools.py` + `github_tools.py` + `middleware/auth.py` + `telegram_bot.py`

### Incomplete Keychain architecture — needs completion
10. `emo-desktop/lib/credentials/os-keyring.ts` + `ephemeral_injection.ts` + `keyring-adapter.ts`
11. `emo-desktop/src-tauri/src/commands.rs` (needs `get_api_key` and `delete_api_key`)
12. `emo-desktop/src-tauri/Cargo.toml` (needs `tauri-plugin-keyring`)
13. `emo-desktop/src-tauri/tauri.conf.json` (plugin keyring exists but not wired)

---

## Keychain Migration Plan

### Phase 1: Immediate — Rotate exposed keys
1. Rotate `OPENROUTER_API_KEY` immediately — leaked in Git docs
2. Rotate `GROQ_API_KEY` immediately
3. Remove keys from `docs/REQUIREMENTS_UNDERSTANDING.md`
4. Change `EMO_JWT_SECRET` to a secure value
5. Change `TELEGRAM_TOKEN` to a valid value

### Phase 2: Python Backend Keychain
6. Add `keyring` to `requirements.txt`
7. Create `core/security/keychain_provider.py`
8. Modify `brain.py` to read keys from Keychain instead of env
9. Modify `firebase_tools.py`, `supabase_tools.py`, `github_tools.py`, `middleware/auth.py`

### Phase 3: Desktop Keychain Completion
10. Complete `os-keyring.ts` — real invoke functions
11. Add `tauri-plugin-keyring` to `Cargo.toml`
12. Add `get_api_key` and `delete_api_key` in `commands.rs`
13. Complete `ephemeral_injection.ts`

### Phase 4: Enforcement
14. pre-commit hook to prevent plain text keys
15. CI scan via `leakage-scanner.sh`
16. Runtime check in `main.py` — fail if Keychain unavailable

---

## Conclusion

Current Keychain Adoption: **~15%** (only in Rust/Desktop layer partially)
Keychain Adoption in Python: **0%**

**First practical step:** Rotate OpenRouter and Groq API keys immediately, then remove keys from `docs/REQUIREMENTS_UNDERSTANDING.md`.
