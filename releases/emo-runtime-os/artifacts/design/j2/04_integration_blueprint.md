# Phase J2 — Integration Blueprint: F1 / I1 / F4 / J2

## Overview

Defines the data flow, correlation strategy, event hooks, and acceptance
criteria for integrating the J2 Enterprise Readiness Layer with existing
F1 UnifiedRuntime API, I1 ObjectStorage/Infrastructure, and F4
Observability.

Ref: ROADMAP 🔟 FINAL DELIVERY STAGE
Ref: DEVELOPER.md §15.15 (Enterprise & Compliance), §16 (Production Readiness)
Ref: Canon LAW 1, 2, 9, 11, 12, 23-27, RULE 1-5
Ref: artifacts/design/j2/protocols/01_enterprise_protocols.py
Ref: artifacts/design/j2/models/02_tenant_and_billing_models.py
Ref: artifacts/design/j2/03_tenant_isolation_machine.md

---

## 1. Data Flow Diagram

```
┌──────────────┐     ┌──────────────────┐     ┌─────────────────┐
│              │     │                  │     │                 │
│   Client /   │────>│  F1 Unified     │────>│  J2.TenantRouter│
│   SDK (J1)   │     │  Runtime API     │     │  (route_request)│
│              │     │                  │     │                 │
└──────────────┘     └──────────────────┘     └────────┬────────┘
                                                        │
                                          ┌─────────────┼─────────────┐
                                          ▼             ▼             ▼
                                   ┌──────────┐ ┌──────────┐ ┌──────────────┐
                                   │ TENANT   │ │ QUOTA   │ │ ROUTE        │
                                   │VALIDATION│ │ CHECK   │ │ EXECUTE      │
                                   │ (G-L1)   │ │ (G-L2)  │ │ (F1 engine)  │
                                   └────┬─────┘ └────┬─────┘ └──────┬───────┘
                                        │            │              │
                                        ▼            ▼              ▼
                                   ┌───────────────────────────────────────┐
                                   │         J2.IUsageMeter               │
                                   │  record_operation → aggregate_daily   │
                                   │  → detect_anomalies → flush_to_billing│
                                   └──────────────┬────────────────────────┘
                                                  │
                                                  ▼
                                   ┌───────────────────────────────────────┐
                                   │         J2.IBillingEngine             │
                                   │  apply_pricing_tier → generate_invoice│
                                   │  → process_payment_state              │
                                   │  → suspend_on_default                 │
                                   └──────────────┬────────────────────────┘
                                                  │
                                                  ▼
                                   ┌───────────────────────────────────────┐
                                   │    J2.IComplianceAuditor              │
                                   │  collect_audit_trail → validate →     │
                                   │  generate_report → archive_logs       │
                                   └──────┬────────────────────────────────┘
                                          │
                                          ▼
                                   ┌──────────────────┐
                                   │  I1.ObjectStorage │
                                   │ (invoice PDFs,    │
                                   │  archived logs,   │
                                   │  compliance repos)│
                                   └──────────────────┘
                                          │
                                          ▼
                                   ┌──────────────────┐
                                   │  F4 Observability│
                                   │ (events, metrics, │
                                   │  alerts, traces)  │
                                   └──────────────────┘
```

---

## 2. Correlation ID Strategy: enterprise_trace_id

### Hierarchy

The `enterprise_trace_id` flows through all layers, with each component
extending the trace chain:

```
SDK/CLI (J1)
  │
  ├── enterprise_trace_id = "entr_" + SHA-256(session + ts)[:28]
  │
  ▼
F1 UnifiedRuntime
  │
  ├── Reuses enterprise_trace_id from J1
  │
  ▼
J2.TenantRouter
  │
  ├── Extends: route_trace = enterprise_trace_id + ":route:" + tenant_id
  │
  ▼
J2.IUsageMeter
  │
  ├── Extends: meter_trace = route_trace + ":meter:" + record_id
  │
  ▼
J2.IBillingEngine
  │
  ├── Extends: billing_trace = meter_trace + ":bill:" + invoice_id
  │
  ▼
J2.IComplianceAuditor
  │
  ├── Extends: audit_trace = billing_trace + ":audit:" + entry_id
  │
  ▼
F4 Observability
  │
  └── Full trace chain stored; any segment is back-traceable to root
```

### Propagation Rules (P-R1–P-R6)

| ID | Rule | Enforced By |
|----|------|-------------|
| P-R1 | Every J2 protocol method MUST accept `enterprise_trace_id: str` as parameter | Protocol signature |
| P-R2 | Every J2 method return MUST include `trace_id` in its result dict | Protocol return spec |
| P-R3 | When calling another J2 component, forward the full `enterprise_trace_id` chain | Integration code |
| P-R4 | When calling I1 or F4, include `enterprise_trace_id` in payload metadata | Integration code |
| P-R5 | enterprise_trace_id MUST be non-empty (min 8 chars) — validated at entry point | RULE 2 |
| P-R6 | enterprise_trace_id MUST be logged in every audit entry | IComplianceAuditor |

---

## 3. Event Hooks (H1–H10)

### Published Event Topics

| ID | Topic | Publisher | Payload | Trigger |
|----|-------|-----------|---------|---------|
| H1 | `enterprise.routing.request` | ITenantRouter | tenant_id, isolation_policy, action, trace_id | On route_request() |
| H2 | `enterprise.routing.violation` | ITenantRouter | tenant_id, blocked_by, reason, trace_id | G-L1 violation |
| H3 | `enterprise.routing.quota_exceeded` | ITenantRouter | tenant_id, resource_type, requested, available, trace_id | G-L2 violation |
| H4 | `enterprise.metering.recorded` | IUsageMeter | tenant_id, operation_type, cost_units, record_hash, trace_id | After record_operation() |
| H5 | `enterprise.metering.anomaly` | IUsageMeter | tenant_id, anomaly_score, flagged_ops, trace_id | detect_anomalies() triggered |
| H6 | `enterprise.billing.invoice_generated` | IBillingEngine | invoice_id, tenant_id, total_amount, due_date, trace_id | After generate_invoice() |
| H7 | `enterprise.billing.suspended` | IBillingEngine | tenant_id, invoices_overdue, suspended_at_ns, trace_id | suspend_on_default() |
| H8 | `enterprise.billing.payment_transition` | IBillingEngine | invoice_id, from_state, to_state, reason, trace_id | process_payment_state() |
| H9 | `enterprise.audit.compliance_violation` | IComplianceAuditor | tenant_id, framework, violation_count, trace_id | validate_gdpr_soc2() found violations |
| H10 | `enterprise.audit.logs_archived` | IComplianceAuditor | tenant_id, archived_count, retention_days, archive_ref, trace_id | archive_logs() completed |

### Event Bus Integration

All hooks publish to F4 event bus. The event format follows `ExecutionEvent`
from `core.models.events`:

```python
ExecutionEvent(
    event_id=f"entr_{int(time.time() * 1000000)}",
    event_type="STATE_TRANSITION",
    timestamp=time.time(),
    source="J2Enterprise",
    payload={
        "action": "TenantRequestRouted",
        "topic": "enterprise.routing.request",
        "tenant_id": "...",
        "enterprise_trace_id": "...",
        # additional context
    },
)
```

---

## 4. I1 ObjectStorage Integration

### Stored Artifacts

| Artifact | Storage Path Pattern | I1 Service | Retention |
|----------|---------------------|------------|-----------|
| Invoice PDF | `invoices/{tenant_id}/{invoice_id}.pdf` | ObjectStorage | 7 years |
| Compliance report | `compliance/{tenant_id}/{framework}/{report_id}.json` | ObjectStorage | Per AuditRetentionPolicy |
| Archived audit logs | `audit_archive/{tenant_id}/{year}/{month}/` | ObjectStorage + TTL | Per retention policy |
| Usage snapshots | `usage/{tenant_id}/{date}/snapshot.json` | ObjectStorage | 90 days |

### Data Flow

```
J2.IBillingEngine.generate_invoice()
  → 1. Generate invoice data
  → 2. Store invoice PDF in I1.ObjectStorage
  → 3. Record storage reference in invoice metadata
  → 4. Publish H6 event

J2.IComplianceAuditor.archive_logs()
  → 1. Query active audit log entries older than retention window
  → 2. Batch-move to I1.ObjectStorage with TTL
  → 3. Remove archived entries from active log
  → 4. Publish H10 event
```

---

## 5. F4 Observability Integration

### Metrics

| Metric Name | Type | Source | Labels |
|-------------|------|--------|--------|
| `enterprise.routing.total` | Counter | ITenantRouter | tenant_id, isolation_policy, status |
| `enterprise.routing.blocked` | Counter | ITenantRouter | tenant_id, blocked_by |
| `enterprise.quota.remaining` | Gauge | ITenantRouter | tenant_id, resource_type |
| `enterprise.metering.operations` | Counter | IUsageMeter | tenant_id, operation_type |
| `enterprise.metering.anomaly_score` | Gauge | IUsageMeter | tenant_id |
| `enterprise.billing.invoice_total` | Counter | IBillingEngine | tenant_id, currency |
| `enterprise.billing.suspensions` | Counter | IBillingEngine | tenant_id, reason |
| `enterprise.audit.entries` | Counter | IComplianceAuditor | tenant_id, framework |
| `enterprise.audit.violations` | Counter | IComplianceAuditor | tenant_id, framework |

### Alerts

| Condition | Severity | Alert Name |
|-----------|----------|------------|
| Routing block rate > 5% in 5min | warning | `EnterpriseHighRoutingBlockRate` |
| Quota exceeded > 3 times/hour for tenant | warning | `EnterpriseFrequentQuotaExceeded` |
| Anomaly score > 0.8 | critical | `EnterpriseUsageAnomalyDetected` |
| Invoice unpaid > 30 days | warning | `EnterpriseOverdueInvoice` |
| Tenant suspended | critical | `EnterpriseTenantSuspended` |
| Compliance violation detected | critical | `EnterpriseComplianceViolation` |

---

## 6. Acceptance Criteria

### Latency Budgets

| Operation | Budget | Measured At |
|-----------|--------|-------------|
| tenant route + validate scope | ≤ 15ms | ITenantRouter.route_request |
| quota check + enforcement | ≤ 5ms | ITenantRouter.enforce_quota |
| record operation (meter) | ≤ 10ms | IUsageMeter.record_operation |
| daily aggregate | ≤ 100ms | IUsageMeter.aggregate_daily_usage |
| invoice generation | ≤ 200ms | IBillingEngine.generate_invoice |
| compliance validation (1000 entries) | ≤ 500ms | IComplianceAuditor.validate_gdpr_soc2 |
| archive logs (10k entries) | ≤ 2s | IComplianceAuditor.archive_logs |

### Idempotency Guarantees

| Operation | Idempotency Key | Behavior on Retry |
|-----------|----------------|-------------------|
| route_request | (tenant_id, request_hash, trace_id) | Same route result |
| record_operation | (tenant_id, record_hash, trace_id) | Dedup: record_hash matched |
| aggregate_daily_usage | (tenant_id, date, trace_id) | Same aggregate result |
| flush_to_billing | (tenant_id, trace_id) | No-op if already flushed |
| generate_invoice | (invoice_id, trace_id) | Returns existing invoice |
| process_payment_state | (invoice_id, new_state, trace_id) | No-op if already in new_state |
| collect_audit_trail | (entry_hash, trace_id) | Dedup: entry_hash matched |

### Determinism Thresholds

| Check | Threshold | Guard |
|-------|-----------|-------|
| Audit entry hash reproducibility | 100% match | G-A1 |
| Meter record hash reproducibility | 100% match | G-M1 |
| Invoice total recalculation | ± Decimal('0.01') | RULE 2 |
| Compliance score variance | ± 0.0 (deterministic) | RULE 1 |

### Rollback on Failure

| Failure Point | Rollback Action | RULE |
|---------------|-----------------|------|
| Quota enforcement fails mid-operation | Reverse quota deduction | RULE 5 |
| Meter record fails to buffer | Discard record, no billing impact | RULE 5 |
| Invoice generation fails after storage | Delete stored invoice artifact | RULE 5 |
| Compliance validation fails | Reject audit entries, flag for review | RULE 3 |
| Payment state transition invalid | Revert to previous state | RULE 5 |

---

## 7. CompositionRoot Wiring Specification

The J2 components will be wired in CompositionRoot (during Phase J2
implementation) following the same pattern as J1:

```python
# (Design-only sketch — not production code)

# Constructor params:
#   tenant_router: Any = None,
#   usage_meter: Any = None,
#   billing_engine: Any = None,
#   compliance_auditor: Any = None,
#   strict_enterprise_mode: bool = False,

# Properties:

# @property
# def tenant_router(self) -> Any:
#     ...

# @property
# def usage_meter(self) -> Any:
#     ...

# @property
# def billing_engine(self) -> Any:
#     ...

# @property
# def compliance_auditor(self) -> Any:
#     ...

# Builder methods:
#   _build_tenant_router() -> TenantRouter
#   _build_usage_meter() -> UsageMeter
#   _build_billing_engine() -> BillingEngine
#   _build_compliance_auditor() -> ComplianceAuditor
```

Total J2 components: 4 protocols × 1 implementation = 4 production modules
+ 1 state machine module + 1 `__init__.py` = 6 files in `core/enterprise/`.
