# Debt Resolution Plan — Pre-existing Test Failures

## Summary
- **Total quarantined tests:** ~100
- **Test files affected:** 18
- **Categories:** 5 (env_missing, legacy_billing, jwt_migration, async_fixture, other_legacy)
- **Estimated total effort:** 14-21 hours

---

## Category 1: env_missing — Missing Dependencies

| Test File | Tests | Root Cause | Fix |
|---|---|---|---|
| `test_bootstrap.py` | ~1 (collection error) | `aiosqlite` not installed | `pip install aiosqlite` |
| `test_composition_root_isolation.py` | ~1 (collection error) | `aiosqlite` not installed | `pip install aiosqlite` |
| `test_pilot_safety.py` | ~1 (collection error) | `aiosqlite` not installed | `pip install aiosqlite` |
| `test_sql_injection_prevention.py` | ~1 (collection error) | `aiosqlite` not installed | `pip install aiosqlite` |

**Effort:** 0.5h (install dep)
**Priority:** High (blocks test discovery for 4 files)

---

## Category 2: legacy_billing — Billing/Enterprise Integration

| Test File | Tests | Root Cause | Fix |
|---|---|---|---|
| `test_billing_determinism_and_rollback.py` | 12 | Billing engine requires full enterprise env | Provision enterprise services |
| `test_ent_enterprise_integration.py` | 19 | Enterprise wiring not in composition root | Wire enterprise services |
| `test_enterprise_pilot_operational.py` | 20 | Enterprise pilot not deployed | Deploy ENT-PILOT-001 |

**Effort:** 5-8h
**Priority:** Medium (requires enterprise infrastructure)

---

## Category 3: jwt_migration — JWT Security Migration

| Test File | Tests | Root Cause | Fix |
|---|---|---|---|
| `test_jwt_lifecycle_security.py` | 12 | JWT secret/env changes | Update test assertions |
| `test_status_endpoint_auth_protection.py` | 3 | Status endpoint auth decorator | Align test with current middleware |
| `test_high_priority_remediation.py` | 4 | Security logging/remediation | Update test expectations |

**Effort:** 2-3h
**Priority:** High (security-critical)

---

## Category 4: async_fixture — Async Fixture Incompatibility

| Test File | Tests | Root Cause | Fix |
|---|---|---|---|
| `test_async_task_manager.py` | 1 | Sync assertion on async result | Convert to async test |
| `test_recovery_coordinator.py` | 3 | Async fixture collection error | Fix async/sync pattern |

**Effort:** 1-2h
**Priority:** Medium

---

## Category 5: other_legacy — Other Legacy Integration

| Test File | Tests | Root Cause | Fix |
|---|---|---|---|
| `test_compliance_audit_immutability.py` | 8 | Compliance auditor not wired | Wire in composition root |
| `test_chaos_post_refactor_integration.py` | 1 | Runtime import path | Fix import |
| `test_contracts.py` | 1 | Tool registration contract | Fix contract test |
| `test_d9_feedback_loop_e2e.py` | 2 | Feedback loop not wired | Wire feedback loop |
| `test_f1_unified_api_e2e.py` | 3 | Unified API not wired | Wire services |
| `test_f2_control_plane_integration.py` | 1 | Control plane not wired | Wire services |
| `test_f3_resource_scheduler_integration.py` | 1 | Resource scheduler not wired | Wire services |
| `test_f4_observability_integration.py` | 1 | Observability not wired | Wire services |
| `test_final_freeze_certification.py` | 3 | Freeze mechanism not active | Activate freeze |
| `test_final_release_certification.py` | 3 | Release certification not available | Deploy release pipeline |
| `test_k2_state_corruption_safety.py` | 1 | Corruption safety not wired | Wire safety layer |
| `test_phase5_distributed.py` | 1 | Distributed transport not available | Deploy transport |

**Effort:** 4-6h
**Priority:** Low (legacy integration tests)

---

## Resolution Workflow

```
1. Install aiosqlite → fix 4 env_missing collection errors     [0.5h]
2. Update JWT assertions → fix 19 jwt_migration tests           [2-3h]
3. Fix async fixture patterns → fix 4 async_fixture tests       [1-2h]
4. Wire legacy services → fix remaining legacy tests            [4-6h]
5. Deploy enterprise infrastructure → fix billing tests         [5-8h]
```

## Acceptance Criteria
- [ ] `pip install aiosqlite` resolves env_missing category
- [ ] `pytest -m "not quarantined"` returns 0 failures
- [ ] Each resolved category is removed from `tests/quarantine/`
- [ ] Final delivery threshold: 3076+ PASS, 0 FAIL (actual), 0 quarantined
