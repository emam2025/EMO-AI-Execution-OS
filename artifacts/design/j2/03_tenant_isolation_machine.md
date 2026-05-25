# Phase J2 — Tenant Isolation & Metering State Machine

## Overview

Formal state machine governing tenant request lifecycle through Isolation
Boundary, Quota Enforcement, Usage Metering, and Billing Suspension.
Enforces 5 Leakage Guards (G-L1–G-L5) and 1 Deterministic Audit Guard (G-A1).

Ref: ROADMAP 🔟 FINAL DELIVERY STAGE
Ref: DEVELOPER.md §15.15 (Enterprise & Compliance), §16 (Production Readiness)
Ref: Canon LAW 1, 2, 9, 11, 23-27, RULE 1-5
Ref: artifacts/design/j2/protocols/01_enterprise_protocols.py
Ref: artifacts/design/j2/models/02_tenant_and_billing_models.py

---

## 1. State Transition Map

```
                        ┌──────────────────────────────────────┐
                        │           REQUEST RECEIVED           │
                        │  (F1.submit() or ApiGateway entry)   │
                        └──────────────┬───────────────────────┘
                                       │
                                       ▼
                        ┌──────────────────────────────────────┐
                  ┌────>│         TENANT VALIDATION            │
                  │     │  service: ITenantRouter              │
                  │     │  guard:   G-L1 (scope/isolation)     │
                  │     └──────────────┬───────────────────────┘
                  │                    │
                  │          ┌─────────┴──────────┐
                  │          ▼                    ▼
                  │  ┌──────────────┐   ┌──────────────────┐
                  │  │  ALLOWED    │   │    BLOCKED       │
                  │  │  (valid)    │   │  (invalid scope) │
                  │  └──────┬──────┘   └────────┬─────────┘
                  │         │                   │
                  │         ▼                   ▼
                  │  ┌──────────────┐   ┌──────────────────┐
                  │  │ QUOTA CHECK │   │  ROUTING FAILED   │
                  │  │ guard: G-L2 │   │→ AuditableEvent   │
                  │  └──────┬──────┘   └──────────────────┘
                  │         │
                  │  ┌──────┴──────┐
                  │  ▼             ▼
                  │  ┌──────┐  ┌─────────┐
                  │  │HAVE  │  │EXCEEDED │
                  │  │QUOTA │  │→ Block  │
                  │  └──┬───┘  └────┬────┘
                  │     │           │
                  │     ▼           ▼
                  │  ┌──────────┐  ┌──────────────────┐
                  │  │  ROUTE   │  │ QUOTA_EXCEEDED   │
                  │  │ EXECUTE  │  │→ AuditableEvent  │
                  │  │(F1 layer)│  └──────────────────┘
                  │  └────┬─────┘
                  │       │
                  │       ▼
                  │  ┌──────────────────┐
                  │  │   METER USAGE    │
                  │  │ service: IUsage- │
                  │  │ Meter.record_op  │
                  │  │ guard: G-L3, G-M1│
                  │  └──────┬───────────┘
                  │         │
                  │         ▼
                  │  ┌──────────────────┐
                  │  │  AGGREGATE &     │
                  │  │  FLUSH TO BILLING│
                  │  │  service: IUsage-│
                  │  │  Meter.flush_    │
                  │  │  to_billing      │
                  │  │  guard: G-L4     │
                  │  └──────┬───────────┘
                  │         │
                  │         ▼
                  │  ┌──────────────────┐
                  │  │  AUDIT LOG      │
                  │  │  service: IComp- │
                  │  │  lianceAuditor   │
                  │  │  guard: G-A1     │
                  │  └──────┬───────────┘
                  │         │
                  │         ▼
                  │  ┌──────────────────┐
                  │  │  COMPLETED      │
                  │  │  → Return result │
                  │  └──────────────────┘
                  │
                  │  ┌──────────────────┐
                  └──│   SUSPENDED     │
                     │  (from billing  │
                     │   default)      │
                     │  guard: G-L5    │
                     └──────┬──────────┘
                            │
                            ▼
                     ┌──────────────────┐
                     │  BLOCK ALL       │
                     │  REQUESTS        │
                     │  → until resolved│
                     └──────────────────┘
```

### Transitions Table

| ID  | From              | To                | Trigger               | Guard |
|-----|-------------------|-------------------|-----------------------|-------|
| T1  | REQUEST_RECEIVED  | TENANT_VALIDATION | incoming F1 request   | G-L1  |
| T2  | TENANT_VALIDATION | QUOTA_CHECK       | scope_verified==True  | —     |
| T3  | TENANT_VALIDATION | ROUTING_FAILED    | scope_verified==False | G-L1  |
| T4  | QUOTA_CHECK       | ROUTE_EXECUTE     | quota remaining       | G-L2  |
| T5  | QUOTA_CHECK       | QUOTA_EXCEEDED    | quota exhausted       | G-L2  |
| T6  | QUOTA_EXCEEDED    | REQUEST_RECEIVED  | retry/backoff         | —     |
| T7  | ROUTE_EXECUTE     | METER_USAGE       | execution complete    | G-L3  |
| T8  | METER_USAGE       | AGGREGATE_FLUSH   | batch threshold met   | G-L4  |
| T9  | AGGREGATE_FLUSH   | AUDIT_LOG         | post-billing          | G-A1  |
| T10 | AUDIT_LOG         | COMPLETED         | audit entry stored    | —     |
| T11 | ROUTING_FAILED    | COMPLETED         | (error result)        | —     |
| T12 | QUOTA_EXCEEDED    | COMPLETED         | (error result)        | —     |
| T13 | SUSPENDED         | REQUEST_RECEIVED  | tenant reinstated     | G-L5  |

---

## 2. Leakage Guards Matrix (G-L1 through G-L5)

### G-L1: Cross-Tenant Access Isolation

**Condition:**
```
cross_tenant_access_allowed = (
    requesting_tenant != target_tenant
    AND shared_resource_flag == True
    AND scope_verified == True
    AND target.isolation_policy != STRICT
)
```

**If violated:** → `ROUTING_FAILED`, event published to
`enterprise.routing.violation`.

**Canon ref:** LAW 11, 23; RULE 3

### G-L2: Quota Exhaustion Guard

**Condition:**
```
quota_available = (resource_units_allocated - resource_units_consumed)
operation_allowed = (requested_units <= quota_available)
```

**If violated:** → `QUOTA_EXCEEDED`, no deduction made. Event published to
`enterprise.routing.quota_exceeded`.

**Canon ref:** LAW 24; RULE 3

### G-L3: Metering Boundary Guard (Tenant Data Leakage)

**Condition:**
```
metering_allowed = (
    tenant_id == executing_tenant_id
    AND operation_type in tenant.pricing_tier.operation_allowlist
    AND isolation_boundary is not None
)
```

**If violated:** Meter record is discarded, violation audit entry created.

**Canon ref:** LAW 23, 11; RULE 3

### G-L4: Billing Flush Integrity Guard

**Condition:**
```
flush_allowed = (
    record_count > 0
    AND all(r.tenant_id == flushing_tenant for r in records)
    AND sum(r.cost_units) > Decimal('0')
)
```

**If violated:** Flush is aborted, buffer is NOT cleared, error event published.

**Canon ref:** LAW 24, 25; RULE 1, 2

### G-L5: Suspension Guard

**Condition:**
```
suspension_allowed = (
    overdue_invoice_count >= MAX_OVERDUE_THRESHOLD  # e.g. 3
    OR any(invoice.payment_state == FAILED
           for invoice in overdue_invoices)
)
AND tenant.status != SUSPENDED  # idempotent
```

**If violated:** Suspension is NOT applied, warning event published.

**Canon ref:** LAW 25; RULE 3, 5

---

## 3. Deterministic Audit Guard (G-A1)

### Purpose

Prevents Non-Deterministic Audit Drift — the same tenant action with the
same compliance schema MUST produce the identical audit log entry hash.
This guarantees audit trail integrity across replicas and retries.

### Hash Formula

```
G-A1_hash = SHA-256(
    tenant_id
    + ":" + action
    + ":" + actor
    + ":" + target_resource
    + ":" + compliance_framework
    + ":" + retention_policy
)
```

Result: 32-character hex string.

### Verification

```
def audit_verify(entry: AuditLogEntry, schema_version: str) -> bool:
    expected = deterministic_audit_hash(
        entry.tenant_id,
        entry.action,
        entry.actor,
        entry.target_resource,
        entry.compliance_framework,
        entry.retention_policy,
        schema_version,
    )
    return entry.compliance_hash == expected
```

### Non-Determinism Protection

| Scenario | G-A1 Response |
|----------|---------------|
| Same tenant_action + compliance_schema | Always same hash |
| Different tenant | Different hash |
| Different action | Different hash |
| Schema version mismatch | Hash mismatch → violation flag |
| Tampered entry (hash changed) | Verification fails → alert |

### Canon ref

- **RULE 1:** Determinism — same inputs, same audit hash.
- **LAW 27:** Every audit entry is uniquely identifiable and verifiable.
- **LAW 26:** Compliance framework is part of the hash input for
  framework-specific audit chains.

---

## 4. Billing State Machine (PaymentState Transitions)

```
                    ┌──────────┐
                    │  PENDING │
                    └────┬─────┘
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
        ┌─────────┐ ┌─────────┐ ┌──────────┐
        │PROCESSING│ │ FAILED  │ │ DISPUTED │
        └────┬────┘ └────┬────┘ └─────┬────┘
             │           │            │
             ▼           ▼            │
        ┌─────────┐ ┌──────────┐      │
        │  PAID   │ │WRITTEN_OFF│     │
        └─────────┘ └──────────┘      │
                                       │
                              ┌────────┘
                              ▼
                        ┌──────────┐
                        │PROCESSING│
                        └────┬─────┘
                             ▼
                        ┌─────────┐
                        │  PAID   │
                        └─────────┘
```

| From | To | Guard |
|------|----|-------|
| PENDING | PROCESSING | invoice total validated |
| PROCESSING | PAID | payment gateway confirmed |
| PENDING | FAILED | payment gateway rejected |
| FAILED | WRITTEN_OFF | grace period expired |
| PENDING | DISPUTED | tenant filed dispute |
| DISPUTED | PROCESSING | dispute resolved in favor |

---

## 5. Compliance Report State Machine

```
                    ┌──────────┐
                    │   IDLE   │
                    └────┬─────┘
                         │
                         ▼
                    ┌──────────┐
                    │COLLECTING│ ←─ IComplianceAuditor.collect_audit_trail
                    └────┬─────┘
                         │
                         ▼
                    ┌──────────┐
                    │VALIDATING│ ←─ IComplianceAuditor.validate_gdpr_soc2
                    └────┬─────┘
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
        ┌─────────┐ ┌─────────┐ ┌──────────┐
        │  PASS   │ │  FLAG   │ │   FAIL   │
        └─────────┘ └────┬────┘ └──────────┘
                         │
                         ▼
                    ┌──────────┐
                    │ ARCHIVED │ ←─ archive_logs
                    └──────────┘
```

| From | To | Guard | Condition |
|------|----|-------|-----------|
| IDLE | COLLECTING | — | Triggered by audit collection request |
| COLLECTING | VALIDATING | G-A1 | All entries have matching hashes |
| VALIDATING | PASS | — | score == 1.0 |
| VALIDATING | FLAG | RULE 3 | score between 0.7 and 0.99 |
| VALIDATING | FAIL | RULE 3 | score < 0.7 or critical violations |
| PASS/FLAG/FAIL | ARCHIVED | — | retention window met |
