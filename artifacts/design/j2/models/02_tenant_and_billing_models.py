"""Phase J2 — Tenant, Billing & Audit Data Models.  # LAW-1 LAW-11 LAW-12 LAW-23 LAW-24 LAW-25 LAW-26 LAW-27 RULE-1 RULE-2 RULE-3 RULE-4 RULE-5

Design-only dataclass and enum definitions for the Enterprise Readiness
Layer. Every model carries enterprise_trace_id for end-to-end traceability
(LAW 12). No global state — all instances are per-tenant scoped (LAW 11).

Ref: ROADMAP 🔟 FINAL DELIVERY STAGE
Ref: DEVELOPER.md §15.15 (Enterprise & Compliance)
Ref: artifacts/design/j2/protocols/01_enterprise_protocols.py
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional


# ═══════════════════════════════════════════════════════════════
# Enums (canonical source — protocols/01_enterprise_protocols.py
# duplicates these for design self-containment)
# ═══════════════════════════════════════════════════════════════

class TenantIsolationPolicy(str, Enum):  # LAW-11 LAW-23
    STRICT = "strict"
    SHARED = "shared"
    ISOLATED = "isolated"


class PricingTier(str, Enum):  # LAW-24
    FREE = "free"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"
    CUSTOM = "custom"


class PaymentState(str, Enum):  # LAW-25
    PENDING = "pending"
    PROCESSING = "processing"
    PAID = "paid"
    FAILED = "failed"
    DISPUTED = "disputed"
    WRITTEN_OFF = "written_off"


class OperationType(str, Enum):  # LAW-23
    DAG_SUBMIT = "dag_submit"
    DAG_EXECUTION = "dag_execution"
    STORAGE_BYTE = "storage_byte"
    API_CALL = "api_call"
    MODEL_INFERENCE = "model_inference"
    DATA_EXPORT = "data_export"
    AUDIT_LOG = "audit_log"


class ComplianceFramework(str, Enum):  # LAW-26
    GDPR = "gdpr"
    SOC2 = "soc2"
    HIPAA = "hipaa"
    PCI_DSS = "pci_dss"
    ISO_27001 = "iso_27001"


class AuditAction(str, Enum):  # LAW-27
    TENANT_CREATED = "tenant_created"
    TENANT_CONFIGURED = "tenant_configured"
    RESOURCE_ACCESSED = "resource_accessed"
    QUOTA_EXCEEDED = "quota_exceeded"
    BILLING_TRIGGERED = "billing_triggered"
    SUSPENSION_ACTIVATED = "suspension_activated"
    COMPLIANCE_CHECK = "compliance_check"
    DATA_EXPORTED = "data_exported"
    ROLLBACK_EXECUTED = "rollback_executed"


class TenantStatus(str, Enum):  # LAW-23
    ACTIVE = "active"
    SUSPENDED = "suspended"
    PENDING_ACTIVATION = "pending_activation"
    DEPROVISIONED = "deprovisioned"


class ResourceType(str, Enum):  # LAW-24
    DAG_EXECUTION = "dag_execution"
    API_THROUGHPUT = "api_throughput"
    STORAGE_GB = "storage_gb"
    MODEL_INFERENCE = "model_inference"
    CONCURRENT_WORKERS = "concurrent_workers"


class AuditRetentionPolicy(str, Enum):  # LAW-26 LAW-27
    DAYS_30 = "P30D"
    DAYS_90 = "P90D"
    DAYS_365 = "P365D"
    INDEFINITE = "P99999D"


SuspensionReason = str  # 'payment_default' | 'quota_exhausted' | 'compliance_violation' | 'admin_disabled'


# ═══════════════════════════════════════════════════════════════
# Model 1: TenantContext
# ═══════════════════════════════════════════════════════════════

@dataclass
class TenantContext:  # LAW-11 LAW-23 RULE-3
    """Encapsulates all tenant-specific configuration and state.

    Every tenant has an isolation boundary defined by isolation_policy
    and resource quotas. The enterprise_trace_id_seed generates all
    trace IDs for operations within this tenant scope.

    LAW 11: Each TenantContext is an independent instance — no global
            tenant registry dependency in the model itself.
    LAW 23: All tenant properties are owned by this tenant exclusively.
    RULE 3: isolation_policy MUST be checked before any cross-tenant
            operation (Leakage Guard G-L1 enforces this).
    """
    tenant_id: str
    name: str
    isolation_policy: TenantIsolationPolicy
    status: TenantStatus
    pricing_tier: PricingTier
    resource_quota: Dict[ResourceType, Decimal]
    compliance_flags: List[ComplianceFramework]
    audit_retention: AuditRetentionPolicy
    enterprise_trace_id_seed: str  # LAW-12 seed for trace ID generation
    created_at_ns: int = field(default_factory=lambda: __import__("time").time_ns())
    metadata: Dict[str, Any] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════
# Model 2: UsageRecord
# ═══════════════════════════════════════════════════════════════

@dataclass
class UsageRecord:  # LAW-12 LAW-23 LAW-24 RULE-1 RULE-4
    """A single billable operation record.

    RULE 1: Same tenant_id + operation_type + cost_units -> same
            deterministic hash (record_hash).
    RULE 4: enterprise_trace_id provides full back-traceability.
    """
    record_id: str
    tenant_id: str
    operation_type: OperationType
    cost_units: Decimal
    enterprise_trace_id: str  # LAW-12
    timestamp_ns: int = field(default_factory=lambda: __import__("time").time_ns())
    metadata: Dict[str, Any] = field(default_factory=dict)
    record_hash: str = ""

    def __post_init__(self) -> None:
        if not self.record_hash:
            import hashlib
            raw = f"{self.tenant_id}:{self.operation_type.value}:{self.cost_units}:{self.enterprise_trace_id}"
            self.record_hash = hashlib.sha256(raw.encode()).hexdigest()[:32]


# ═══════════════════════════════════════════════════════════════
# Model 3: BillingInvoice
# ═══════════════════════════════════════════════════════════════

@dataclass
class BillingInvoice:  # LAW-24 LAW-25 RULE-2 RULE-5
    """Invoice generated by IBillingEngine from aggregated usage.

    LAW 24: line_items contain per-operation-type pricing breakdown.
    LAW 25: payment_state follows a deterministic state machine.
    RULE 2: total_amount is validated before generation.
    RULE 5: Rollback restores exact previous invoice state.
    """
    invoice_id: str
    tenant_id: str
    period_start: datetime.date
    period_end: datetime.date
    line_items: List[Dict[str, Any]]  # [{operation_type, units, rate, subtotal}]
    total_amount: Decimal
    currency: str = "USD"
    payment_state: PaymentState = PaymentState.PENDING
    enterprise_trace_id: str = ""  # LAW-12
    created_at_ns: int = field(default_factory=lambda: __import__("time").time_ns())
    due_date: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.due_date is None:
            due = datetime.datetime.now() + datetime.timedelta(days=30)
            self.due_date = due.strftime("%Y-%m-%d")


# ═══════════════════════════════════════════════════════════════
# Model 4: AuditLogEntry
# ═══════════════════════════════════════════════════════════════

@dataclass
class AuditLogEntry:  # LAW-12 LAW-26 LAW-27 RULE-1 RULE-3 RULE-4
    """A single compliance audit log entry.

    LAW 12: enterprise_trace_id chains to the originating operation.
    LAW 26: compliance_framework specifies which framework this entry
            contributes to.
    LAW 27: entry_id and compliance_hash make the entry uniquely
            identifiable and verifiable.
    RULE 1: Same tenant_id + action + actor + target_resource + schema
            -> same compliance_hash (Deterministic Audit Guard G-A1).
    RULE 3: Validation guards block on missing or malformed entries.
    RULE 4: enterprise_trace_id propagates through audit pipeline.
    """
    entry_id: str
    actor: str
    action: AuditAction
    target_resource: str
    tenant_id: str
    compliance_hash: str
    enterprise_trace_id: str  # LAW-12
    retention_policy: AuditRetentionPolicy
    timestamp_ns: int = field(default_factory=lambda: __import__("time").time_ns())
    compliance_framework: ComplianceFramework = ComplianceFramework.GDPR
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.compliance_hash or self.compliance_hash == "":
            import hashlib
            raw = (
                f"{self.tenant_id}:{self.action.value}:{self.actor}:"
                f"{self.target_resource}:{self.compliance_framework.value}:"
                f"{self.retention_policy.value}"
            )
            self.compliance_hash = hashlib.sha256(raw.encode()).hexdigest()[:32]


# ═══════════════════════════════════════════════════════════════
# Model 5: QuotaSnapshot
# ═══════════════════════════════════════════════════════════════

@dataclass
class QuotaSnapshot:  # LAW-23 LAW-24 RULE-3
    """Point-in-time snapshot of a tenant's resource quota state.

    Used by ITenantRouter.enforce_quota to report quota before/after
    a routing decision. Stored in the routing event for audit.
    """
    tenant_id: str
    quotas: Dict[ResourceType, Decimal]
    consumed: Dict[ResourceType, Decimal]
    remaining: Dict[ResourceType, Decimal]
    enterprise_trace_id: str  # LAW-12
    captured_at_ns: int = field(default_factory=lambda: __import__("time").time_ns())


# ═══════════════════════════════════════════════════════════════
# Model 6: ComplianceReport
# ═══════════════════════════════════════════════════════════════

@dataclass
class ComplianceReport:  # LAW-26 LAW-27 RULE-1 RULE-3
    """Structured compliance report generated by IComplianceAuditor.

    RULE 1: Same audit entries + framework -> same report_hash.
    RULE 3: status is FAIL if any violation is critical.
    """
    report_id: str
    tenant_id: str
    framework: ComplianceFramework
    status: str  # 'PASS' | 'FAIL' | 'FLAG'
    period_start: datetime.date
    period_end: datetime.date
    entry_count: int
    violations: List[str]
    report_hash: str
    enterprise_trace_id: str  # LAW-12
    generated_at_ns: int = field(default_factory=lambda: __import__("time").time_ns())
