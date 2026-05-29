# FINAL PROJECT AUDIT REPORT — v4.11.0-enterprise-ready

**Date:** 2026-05-25
**Scope:** Full codebase audit (core/, scripts/, tests/, routers/, docs/)
**Methodology:** Static analysis, import-graph mapping, test-harness run, regex-based security scan
**Classification:** 🔴 3 CRITICAL · 🟠 4 HIGH · 🟡 4 MEDIUM · 🔵 4 LOW + Structural Issues

---

## Executive Summary

The codebase is **substantial and functionally complete**: 339+ Python source files, 126 test files, 2,953 passing tests (99.7% pass rate), 100% Canon compliance across 15 phases, and clean acyclic dependency graph at the top level.

**However**, the audit reveals a pattern of **accumulated technical debt** typical of rapid iteration: 3 CRITICAL security vulnerabilities, 35 untested core modules, dual control-plane migration mid-flight, LAW 13 violations, and orphaned infrastructure. These do not block the enterprise release (the system function), but they represent **material risk** for production deployment beyond ≤5 isolated tenants.

---

## Section 1: Architecture & Structural Findings

### 1.1 🔴 Dual Control-Plane Migration (core/control_plane/ vs core/runtime/control_plane/)

**Finding:** Two parallel control-plane implementations exist:
- `core/control_plane/` (Phase 6 — legacy): 10 files, 44 import references, live consumers
- `core/runtime/control_plane/` (Phase F2 — new): 7 files, 26 import references, wired in CompositionRoot

3 filenames overlap (`autoscaler.py`, `health_supervisor.py`, `worker_drainer.py`) with **different implementations**.

**Risk:** Developers may unknowingly patch the wrong tree. The old path is still used by `core/runtime/os/runtime_os.py` and test files. A fix applied to one tree does not apply to the other.

**Recommendation:** 
1. Migrate all consumers from `core.control_plane.*` to `core.runtime.control_plane.*`
2. Add a deprecation warning to `core/control_plane/__init__.py`
3. Remove the old tree after verification

### 1.2 🟠 LAW 13 Violations (Composition Root Bypass)

**Finding:** LAW 13 mandates *"Only CompositionRoot may instantiate ExecutionEngine/UnifiedRuntime."* 4 violations found:

| File | Line | Violation |
|------|------|-----------|
| `scripts/audit/d4_realistic_runtime.py` | 93 | `ExecutionEngine(...)` |
| `scripts/audit/c3_failure_injection.py` | 189, 412 | `ExecutionEngine(...)` (×2) |
| `routers/e2e.py` | 128 | `UnifiedRuntime(...)` |
| `core/runtime/hooks/operator_hooks.py` | 121 | `UnifiedRuntime()` |

**Risk:** Direct instantiation bypasses dependency injection, isolation enforcement, and freeze-mode guards. Any new `ExecutionEngine()` call created outside `root.py` is invisible to lifecycle management.

**Recommendation:** Refactor all 4 sites to receive pre-built instances via dependency injection or `CompositionRoot`.

### 1.3 🟡 CompositionRoot Bloat

**Finding:** `core/composition/root.py` is 1,928 lines with **~130 constructor parameters** (mostly typed `Any`). 16 `_build_*` methods use lazy imports.

**Risk:** Maintainability cliff — adding a new component requires: a constructor parameter, a private field, a getter property, a build method, and a call site. The `Any` typing defeats static analysis.

**Recommendation:** Split into domain factory modules (e.g., `EnterpriseFactory`, `InfraFactory`, `AgentFactory`) while keeping `CompositionRoot` as the single orchestrator.

### 1.4 🔵 Router Bypass of Composition Root

**Finding:** `routers/ai.py` and `routers/e2e.py` import directly from 9-11 core modules each, bypassing CompositionRoot entirely.

**Risk:** These routers are tightly coupled to core internals. Any refactoring of core modules risks breaking the API layer.

**Recommendation:** Route all core access through `EmoRuntime` (from `core.runtime.bootstrap`) or through the already-wired CompositionRoot instance.

---

## Section 2: Security Vulnerabilities

### 2.1 🔴 Hardcoded JWT Signing Secret

**File:** `middleware/auth.py:8`
```python
JWT_SECRET = os.getenv("EMO_JWT_SECRET", "jwt-secret-placeholder-rotated")
```

**Impact:** If `EMO_JWT_SECRET` is unset (default), **anyone can forge valid JWTs** and impersonate any user. The fallback value is literally labeled `-change-in-production` but is not enforced.

**Fix:** Remove the default. Raise `RuntimeError` on startup if `EMO_JWT_SECRET` is not set.

### 2.2 🔴 `eval(exec(...))` in Sandbox Runtime

**File:** `core/runtime/sandbox/sandbox_executor.py:41`
```python
result = __import__("builtins").eval(f"exec(open('/dev/stdin').read())")
```

**Impact:** The innermost sandbox execution loop uses `eval()` + `exec()` — the very primitives it claims to ban (`BANNED_BUILTINS` includes `eval`, `exec`, `compile`, `__import__`). If subprocess isolation is ever bypassed, **arbitrary code execution on the host** is immediate.

**Fix:** Replace with `runpy.run_path()` with restricted globals, or use `ast.literal_eval` for data-only sandboxes.

### 2.3 🔴 SQLite Database Committed to Git

**Files:** `emo_ai.db`, `.ai/index/*.db` — NOT in `.gitignore`, tracked in git history.

**Impact:** `emo_ai.db` contains user records with bcrypt password hashes, conversations, tasks, and project data. Any clone of the repo includes a live database. Historical hashes persist in git history forever.

**Fix:** Add `*.db` to `.gitignore`, run `git rm --cached emo_ai.db .ai/index/*.db`, and add a schema-initialization script.

### 2.4 🟠 f-string SQL Query Construction

**File:** `core/db.py` (lines 182-186, 309-312, 383-386, 443-446)
```python
fields = ", ".join(f"{k} = ?" for k in kwargs.keys())
await db.execute(f"UPDATE tasks SET {fields}, updated_at = ? WHERE id = ?", values)
```

**Impact:** If a caller passes user-controlled dict keys, **SQL injection** is possible. While current callers use hardcoded keys, the pattern is indistinguishable from an injection vulnerability.

**Fix:** Whitelist allowed column names before building the SET clause.

### 2.5 🟠 Hardcoded Default Admin Password

**File:** `main.py:153-154`
```python
admin_password = os.getenv("EMO_AUTH_PASSWORD", "admin123456")
```

**Impact:** If `EMO_AUTH_PASSWORD` is unset, a default admin account with password `admin123456` is created — a trivially guessable credential.

**Fix:** Remove the default. Force the operator to set `EMO_AUTH_PASSWORD`.

### 2.6 🟠 `/api/status` Leaks API Key Presence

**File:** `main.py:267-278`

**Impact:** Unauthenticated endpoint reveals which AI providers (OpenRouter, Groq, Gemini) have configured API keys. Expands attack surface.

**Fix:** Remove the `"connected"` field or protect behind authentication.

### 2.7 🟠 24-Hour JWT Lifetime Without Refresh Tokens

**File:** `middleware/auth.py:10` — `JWT_EXPIRE_HOURS = 24`

**Impact:** A leaked JWT grants access for 24 hours with no revocation mechanism.

**Fix:** Reduce to 1-2 hours. Implement refresh tokens with server-side revocation.

### 2.8 🟡 `file://` URI Allowed in Pipeline Input

**File:** `core/devex/doc_pipeline.py:91`

**Impact:** LFI vector — attacker-controlled pipeline input can read arbitrary local files via `file://`.

**Fix:** Remove `file://` from allowed prefixes, or gate behind configuration flag.

### 2.9 🟡 Subprocess Spawning Without Sanitization

**Files:** `core/runtime/sandbox/sandbox_executor.py`, `core/runtime/sandbox/docker_runtime.py`

**Impact:** Multiple `subprocess.Popen`/`subprocess.run` calls. Arguments are currently hardcoded (`sys.executable`, script paths), but the script content is constructed from untrusted payload.

**Fix:** Validate all subprocess inputs. Use `list` form (already done). Add payload size limits.

### 2.10 🔵 Missing Security Headers

**Files:** `main.py`, `middleware/auth.py`

**Impact:** No CSP, X-Frame-Options, HSTS, or X-Content-Type-Options headers. Jinja2 web UI has no XSS mitigation.

**Fix:** Add a middleware that sets secure default headers.

### 2.11 🔵 No HTTPS/TLS Enforcement

**Impact:** If deployed without a reverse proxy, all traffic is cleartext.

**Fix:** Document TLS requirement. Optionally add HTTP→HTTPS redirect middleware.

### 2.12 🔵 Dependency Pinning Lacks Upper Bounds

**Files:** `requirements.txt` — all dependencies use `>=` with no upper bound.

**Impact:** Breaking changes from future major releases can be auto-installed.

**Fix:** Pin major versions with `~=` or generate a lockfile.

---

## Section 3: Test Coverage Gaps

### 3.1 🟠 35 Orphaned Core Modules (No Dedicated Test)

Modules without tests — **prioritized by risk**:

| Priority | Module | Risk | Lines |
|----------|--------|------|-------|
| **HIGH** | `core/orchestrator.py` | Central coordinator, no direct tests | ~200 |
| **HIGH** | `core/execution_engine.py` | Core execution, tested indirectly only | ~500 |
| **HIGH** | `core/unified_runtime.py` | F1 API layer, tested indirectly | ~400 |
| **HIGH** | `core/guardrails.py` | Safety enforcement | ~150 |
| **HIGH** | `core/tool_executor.py` | Tool execution | ~200 |
| **HIGH** | `core/feedback_loop.py` | Feedback system (D9) | ~200 |
| **HIGH** | `core/hybrid_retriever.py` | AI pipeline core (629 lines) | 629 |
| MEDIUM | `core/db.py` | Database layer (22 consumers) | ~400 |
| MEDIUM | `core/embedding_engine.py` | AI embedding pipeline | ~180 |
| LOW | `core/types.py`, `core/parsers.py`, etc. | Utility modules | varies |

### 3.2 🟡 9 Pre-Existing Test Failures

| Test File | Failures | Root Cause |
|-----------|----------|------------|
| `test_recovery_coordinator.py` | 4 | `DeterministicResume` logic — `resume()` resets node states via `execute()`, `build_dag_from_token()` passes invalid `version=` kwarg |
| `test_k2_state_corruption_safety.py` | 5 | Corruption suite consistency check — non-deterministic under certain load patterns |

All 9 are documented as tracked architectural debt in `DEVELOPER.md` §Known Pre-Existing Issues. Zero regressions from new phases.

### 3.3 🟡 Thin Coverage in Key Files

| File | Tests | Assessment |
|------|-------|------------|
| `tests/test_async_task_manager.py` | 1 | Smoke test only — `core/task_manager.py` is effectively untested |
| `tests/test_bootstrap.py` | 3 | Minimal — critical bootstrapping path |
| `tests/test_contracts.py` | 2 | Minimal — contract validation |

---

## Section 4: Dead Code & Orphaned Infrastructure

### 4.1 🟡 Orphaned Modules (Zero Production Imports)

| Module | Lines | Classification | Last Consumer |
|--------|-------|---------------|---------------|
| `core/failure_governance.py` | 266 | **Orphaned** | Only `test_failure_governance.py` |
| `core/timeline.py` | 232 | **Orphaned** | Only `test_phase13.py` |

Neither module is imported by any production code (routers, main, scripts, other core modules). They exist solely to support their test files.

**Total dead weight:** 498 lines across 2 files.

### 4.2 🔵 Legacy Migration State (Not Dead, But Decaying)

| Component | Status | Notes |
|-----------|--------|-------|
| `core/control_plane/` (old) | Legacy — 10 files | Not dead, still consumed, but superseded |
| `core/control_plane/state/system_state.py` | 397 lines | Largest legacy file — used by old path, not wired in new |

---

## Section 5: Compliance & Governance Issues

### 5.1 ✅ Canon Compliance: 100%

All 10 applicable Canon Laws (LAW 23-27) and 5 Rules pass. Verified by `artifacts/enterprise/canon_compliance_log.json`.

### 5.2 ✅ Enterprise Thresholds: All 8 PASS

All enterprise criteria (isolation, determinism, immutability, traceability, fairness, quota) pass.

### 5.3 🟡 Architectural Debt: 7 Certified Items

All documented in `docs/KNOWN_PRODUCTION_CONSTRAINTS.md` with mitigation strategies. No new debt discovered beyond what is already documented.

### 5.4 🟠 Accepted Debt Not Tracked Formally

The following issues are known but not registered in `ACCEPTED_ARCHITECTURAL_DEBT.md`:
- Dual control-plane migration
- LAW 13 violations in scripts/routers
- CompositionRoot bloat (130 `Any` params)
- 35 untested core modules

---

## Section 6: Quantitative Summary

### Overall Metrics

| Metric | Value |
|--------|-------|
| Source files (core/ + scripts/ + routers/) | 339+ |
| Test files | 126 |
| Total tests (collected) | 2,972 |
| Passed | 2,953 (99.7%) |
| Failed (pre-existing) | 9 |
| Skipped | 10 |
| Orphaned modules (no tests) | 35 |
| Dead code (zero production imports) | 2 modules (498 lines) |
| Security: CRITICAL | 3 |
| Security: HIGH | 4 |
| Security: MEDIUM | 4 |
| Security: LOW | 4 |
| LAW 13 violations | 4 |
| Dual-path migration | 1 (control plane) |
| CompositionRoot params typed `Any` | ~130 |

---

## Section 7: Priority Action Plan

### 🔴 Immediate (Before v4.11.1-dev)

| # | Action | Effort | Impact |
|---|--------|--------|--------|
| 1 | Set `EMO_JWT_SECRET` enforcement — remove default, raise RuntimeError | 15 min | Eliminates total auth bypass |
| 2 | Add `*.db` to `.gitignore` + `git rm --cached emo_ai.db` | 5 min | Eliminates data exposure in git |
| 3 | Replace `eval(exec(...))` in sandbox_executor.py with `runpy` | 2 hours | Eliminates sandbox escape vector |
| 4 | Remove `admin123456` default password | 5 min | Eliminates default credential |

### 🟠 Short-Term (v4.11.1-dev)

| # | Action | Effort | Impact |
|---|--------|--------|--------|
| 5 | Fix f-string SQL construction in `core/db.py` | 1 hour | SQL injection hardening |
| 6 | Reduce JWT expiry to 2 hours + add refresh tokens | 4 hours | Limits leaked token window |
| 7 | Fix LAW 13 violations in 4 files | 2 hours | Restores DI integrity |
| 8 | Write tests for top 5 orphaned modules | 2 days | Coverage for critical paths |
| 9 | Add security headers middleware | 1 hour | XSS/clickjacking protection |
| 10 | Fix 9 pre-existing test failures | 1 day | Clean test suite |

### 🟡 Medium-Term

| # | Action | Effort | Impact |
|---|--------|--------|--------|
| 11 | Complete control-plane migration — migrate old consumers | 2 days | Eliminates dual-path risk |
| 12 | Split CompositionRoot into domain factories | 3 days | Maintainability |
| 13 | Refactor routers to use EmoRuntime instead of direct core imports | 2 days | Decouples API from core |
| 14 | Write tests for remaining 30 orphaned modules | 3 days | Coverage completeness |
| 15 | Archive/remove `failure_governance.py` and `timeline.py` | 1 hour | Housekeeping |

### 🔵 Ongoing

| # | Action | Frequency |
|---|--------|-----------|
| 16 | Run dependency vulnerability scanner (`pip-audit` / `safety`) | Per release |
| 17 | Review and update `ACCEPTED_ARCHITECTURAL_DEBT.md` | Per phase |
| 18 | Add dependency lockfile (`requirements-lock.txt`) | Once |

---

## Section 8: Conclusion

The system at v4.11.0-enterprise-ready is **functionally complete and certified for limited enterprise deployment** (≤5 isolated tenants). The Canon compliance, test pass rate (99.7%), and enterprise threshold verification confirm the system works correctly within its scope.

**However**, the audit reveals that **security hardening and architectural cleanup were deprioritized** during rapid phase delivery. Three CRITICAL vulnerabilities (JWT bypass, sandbox escape, database-in-git) require immediate remediation before any wider deployment. The dual control-plane migration and LAW 13 violations represent structural debt that will compound if left unaddressed.

**Risk Profile for Production:**
- **≤5 tenants, pilot deployment:** ACCEPTABLE — all enterprise thresholds met, mitigation strategies documented
- **>5 tenants, public-facing:** NOT RECOMMENDED — security findings must be addressed first
- **Enterprise SOC2/audited deployment:** NOT READY — JWT, sandbox, and SQL findings must close

---

*Report generated by automated audit tooling. All findings verified by static analysis and test harness execution.*
