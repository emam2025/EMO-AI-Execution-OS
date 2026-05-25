"""Phase J2 — Enterprise Readiness Layer Protocols.  # LAW-1 LAW-2 LAW-9 LAW-11 LAW-12 LAW-23 LAW-24 LAW-25 LAW-26 LAW-27 RULE-1 RULE-2 RULE-3 RULE-4 RULE-5

Design-only protocol contracts for Multi-Tenant Isolation, Usage Metering &
Billing, and Compliance Audit. All types use typing.Protocol for strict
interface conformance (LAW 1). Every method carries enterprise_trace_id
for end-to-end auditability (LAW 12).

Ref: ROADMAP 🔟 FINAL DELIVERY STAGE
Ref: DEVELOPER.md §15.15 (Enterprise & Compliance), §16 (Production Readiness)
Ref: Canon LAW 1, 2, 9, 11, 12, 23-27
Ref: artifacts/design/j2/models/02_tenant_and_billing_models.py

NON-NEGOTIABLE:
  - LAW 11: No global mutable state — all implementations MUST be instance-scoped.
  - LAW 23-27: Service Ownership — each protocol owns its domain exclusively.
  - RULE 3: Every route/meter/bill/audit operation MUST pass Leakage Guards.
  - RULE 4: Trace propagation across all layers is mandatory.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


# ═══════════════════════════════════════════════════════════════
# Shared Enums (defined here for design self-containment;
# implementations MUST import from the canonical location:
# artifacts/design/j2/models/02_tenant_and_billing_models.py)
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


# ═══════════════════════════════════════════════════════════════
# Protocol 1: ITenantRouter
# ═══════════════════════════════════════════════════════════════

@runtime_checkable
class ITenantRouter(Protocol):  # LAW-1 LAW-9 LAW-11 LAW-23 RULE-3
    """Multi-tenant request router with isolation boundary enforcement.

    Routes incoming requests through Tenant Isolation Boundary:
      1. Validate tenant_id exists and is active.
      2. Check isolation_policy — STRICT tenants NEVER share.
      3. Enforce resource_quota before execution.
      4. Publish routing event for observability.

    LAW 9: Governance is policy-driven, NOT runtime-dependent.
    LAW 11: Router state is instance-scoped (tenant registry).
    LAW 23: Each tenant owns its isolation boundary.
    RULE 3: Cross-tenant access requires shared_resource_flag AND
            scope_verified (Leakage Guard G-L1).
    """

    async def route_request(
        self,
        tenant_id: str,
        request: Dict[str, Any],
        enterprise_trace_id: str,
    ) -> Dict[str, Any]:
        """Route a request through the tenant's isolation boundary.

        Args:
            tenant_id:         Unique tenant identifier.
            request:           The request payload (F1 DAG spec, query, etc.).
            enterprise_trace_id: Correlation trace ID (LAW 12).

        Returns:
            routed:         True if request was routed successfully.
            target_layer:   The resolved target (e.g. 'f1_unified_api').
            isolation_mode: Applied IsolationPolicy value.
            quota_remaining: Dict of remaining resource quotas after routing.
            trace_id:       enterprise_trace_id echoed back.
            blocked_by:     List of guard keys that blocked the route
                            (empty on success).
        """
        ...

    async def validate_tenant_scope(
        self,
        tenant_id: str,
        target_tenant_id: str,
        shared_resource_flag: bool,
        scope_verified: bool,
        enterprise_trace_id: str,
    ) -> Dict[str, Any]:
        """Validate whether tenant_id may access target_tenant_id's scope.

        Leakage Guard G-L1:
          cross_tenant_access_allowed = shared_resource_flag AND
                                        scope_verified AND
                                        target.policy != STRICT

        Returns:
            allowed:        True if cross-tenant access is permitted.
            isolation_mode: IsolationPolicy of the target tenant.
            reason:         Human-readable explanation.
            trace_id:       enterprise_trace_id echoed back.
        """
        ...

    async def enforce_quota(
        self,
        tenant_id: str,
        resource_type: str,
        requested_units: Decimal,
        enterprise_trace_id: str,
    ) -> Dict[str, Any]:
        """Check and deduct from tenant's resource quota.

        Returns:
            allowed:          True if quota remains for requested_units.
            quota_before:     Quota units before deduction.
            quota_after:      Quota units after deduction.
            exceeded:         True if requested_units > available.
            trace_id:         enterprise_trace_id echoed back.
        """
        ...

    async def publish_routing_event(
        self,
        tenant_id: str,
        action: str,
        payload: Dict[str, Any],
        enterprise_trace_id: str,
    ) -> None:
        """Publish a tenant routing event to the event bus.

        Event topic: 'enterprise.routing'
        Payload includes: tenant_id, isolation_policy, quota_state,
                          enterprise_trace_id.
        """
        ...


# ═══════════════════════════════════════════════════════════════
# Protocol 2: IUsageMeter
# ═══════════════════════════════════════════════════════════════

@runtime_checkable
class IUsageMeter(Protocol):  # LAW-1 LAW-11 LAW-23 LAW-24 RULE-1 RULE-4
    """Per-tenant usage metering with anomaly detection.

    Records every billable operation, aggregates daily usage, detects
    anomalous spikes, and flushes aggregated data to the billing engine.

    LAW 11: Meter state is instance-scoped per meter instance.
    LAW 23: Meter data is partitioned by tenant_id.
    LAW 24: cost_units track exactly for correct pricing tier application.
    RULE 1: Same tenant_id + operation_type + cost_units -> same record.
    RULE 4: Every record carries enterprise_trace_id.
    """

    async def record_operation(
        self,
        tenant_id: str,
        operation_type: str,  # OperationType enum value
        cost_units: Decimal,
        enterprise_trace_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Record a single billable operation for a tenant.

        The operation is stored in a tenant-partitioned buffer before
        aggregation. Determinism: same inputs yield identical record hash
        (Deterministic Metering Guard G-M1).

        Returns:
            record_id:  Unique record identifier.
            hash:       SHA-256 integrity hash of the record.
            buffered:   True if queued for batch flush.
            trace_id:   enterprise_trace_id echoed back.
        """
        ...

    async def aggregate_daily_usage(
        self,
        tenant_id: str,
        date: datetime.date,
        enterprise_trace_id: str,
    ) -> Dict[str, Any]:
        """Compute daily usage aggregates from buffered records.

        Returns a snapshot of total cost_units per operation_type for
        the given tenant and date. Aggregation is idempotent (RULE 1).

        Returns:
            tenant_id:    Tenant identifier.
            date:         The date of aggregation.
            totals:       Dict[str, Decimal] of summed cost_units per op type.
            total_units:  Sum of all cost_units for the day.
            record_count: Number of individual records aggregated.
            trace_id:     enterprise_trace_id echoed back.
        """
        ...

    async def detect_anomalies(
        self,
        tenant_id: str,
        usage_snapshot: Dict[str, Any],
        enterprise_trace_id: str,
    ) -> Dict[str, Any]:
        """Detect anomalous usage patterns for a tenant.

        Compares current usage snapshot against historical baselines.
        Flags if: (current - baseline) / baseline > anomaly_threshold.

        Returns:
            anomalous:      True if an anomaly was detected.
            anomaly_score:  Float between 0.0 and 1.0.
            flagged_ops:    List of operation types that triggered.
            detail:         Human-readable explanation.
            trace_id:       enterprise_trace_id echoed back.
        """
        ...

    async def flush_to_billing(
        self,
        tenant_id: str,
        enterprise_trace_id: str,
    ) -> Dict[str, Any]:
        """Flush accumulated usage records to the billing engine.

        After flush, the buffer for this tenant is cleared. The billing
        engine receives an aggregated payload for invoice generation.

        Returns:
            flushed:       Number of records flushed.
            total_cost:    Total Decimal cost_units flushed.
            billing_trace: enterprise_trace_id forwarded to billing.
        """
        ...


# ═══════════════════════════════════════════════════════════════
# Protocol 3: IBillingEngine
# ═══════════════════════════════════════════════════════════════

@runtime_checkable
class IBillingEngine(Protocol):  # LAW-1 LAW-9 LAW-11 LAW-24 LAW-25 RULE-2 RULE-5
    """Billing engine for invoice generation and payment lifecycle.

    Applies pricing tier rules, generates invoices from usage data,
    processes payment state transitions, and suspends tenants on
    payment default. Does NOT directly process financial transactions
    — it manages the billing state machine (LAW 9).

    LAW 9: Governance (billing policy) is NOT coupled to payment execution.
    LAW 11: All billing state is instance-scoped.
    LAW 24: Pricing tier determines rate per operation type.
    LAW 25: PaymentState transitions are deterministic and auditable.
    RULE 2: Invoice amounts are validated before generation.
    RULE 5: Rollback restores exact previous billing state.
    """

    async def apply_pricing_tier(
        self,
        tenant_id: str,
        tier: str,  # PricingTier enum value
        usage_aggregate: Dict[str, Decimal],
        enterprise_trace_id: str,
    ) -> Dict[str, Any]:
        """Apply pricing rules to usage data and compute charges.

        Args:
            tenant_id:           Tenant identifier.
            tier:                The PricingTier to apply.
            usage_aggregate:     Dict mapping operation type -> total cost_units.
            enterprise_trace_id: Trace ID.

        Returns:
            line_items:  List of {operation_type, units, rate, subtotal}.
            total:       Sum of all subtotals as Decimal.
            currency:    ISO 4217 currency code (e.g. 'USD').
            trace_id:    enterprise_trace_id echoed back.
        """
        ...

    async def generate_invoice(
        self,
        tenant_id: str,
        period_start: datetime.date,
        period_end: datetime.date,
        line_items: List[Dict[str, Any]],
        total_amount: Decimal,
        enterprise_trace_id: str,
    ) -> Dict[str, Any]:
        """Generate an invoice from computed line items.

        Returns:
            invoice_id:      Unique invoice identifier.
            invoice_pdf_ref: Reference to the generated invoice artifact.
            payment_state:   Initial PaymentState (PENDING).
            due_date:        ISO date string for payment due.
            trace_id:        enterprise_trace_id echoed back.
        """
        ...

    async def process_payment_state(
        self,
        invoice_id: str,
        tenant_id: str,
        new_state: str,  # PaymentState enum value
        enterprise_trace_id: str,
        reason: str = "",
    ) -> Dict[str, Any]:
        """Transition the payment state of an invoice.

        Valid transitions (Billing State Machine, LAW 25):
          PENDING -> PROCESSING -> PAID
          PENDING -> FAILED -> WRITTEN_OFF
          PENDING -> DISPUTED -> PROCESSING

        Returns:
            invoice_id:    Invoice identifier.
            from_state:    Previous PaymentState.
            to_state:      New PaymentState.
            allowed:       True if transition was valid.
            trace_id:      enterprise_trace_id echoed back.
        """
        ...

    async def suspend_on_default(
        self,
        tenant_id: str,
        overdue_invoices: List[str],
        enterprise_trace_id: str,
    ) -> Dict[str, Any]:
        """Suspend tenant services due to payment default.

        Triggered when overdue_invoices count exceeds threshold or
        payment is FAILED beyond grace period. Suspension revokes
        tenant's routing access until resolved.

        Returns:
            suspended:     True if suspension was applied.
            invoices_overdue: List of invoice IDs that triggered suspension.
            suspended_at_ns: Timestamp of suspension.
            trace_id:      enterprise_trace_id echoed back.
        """
        ...


# ═══════════════════════════════════════════════════════════════
# Protocol 4: IComplianceAuditor
# ═══════════════════════════════════════════════════════════════

@runtime_checkable
class IComplianceAuditor(Protocol):  # LAW-1 LAW-9 LAW-11 LAW-26 LAW-27 RULE-1 RULE-3 RULE-4
    """Compliance auditor for GDPR/SOC2/HIPAA audit trails.

    Collects audit log entries across all tenants, validates against
    compliance frameworks, generates structured compliance reports,
    and archives logs according to retention policies.

    LAW 9: Compliance governance is policy-driven, not runtime-dependent.
    LAW 11: Auditor state is instance-scoped.
    LAW 26: Multiple compliance frameworks supported simultaneously.
    LAW 27: Every audit entry is uniquely identifiable and verifiable.
    RULE 1: Same tenant_action + compliance_schema -> same audit hash
            (Deterministic Audit Guard G-A1).
    RULE 3: Audit validation guards block on compliance violations.
    RULE 4: All audit operations carry enterprise_trace_id.
    """

    async def collect_audit_trail(
        self,
        tenant_id: str,
        action: str,  # AuditAction enum value
        actor: str,
        target_resource: str,
        enterprise_trace_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Collect and store an audit log entry.

        Every entry is hashed with SHA-256 of
        (tenant_id + action + actor + target_resource + compliance_schema)
        for Deterministic Audit Guard (G-A1).

        Returns:
            entry_id:       Unique audit entry identifier.
            hash:           SHA-256 integrity hash (G-A1).
            compliance_hash: Hash for framework-specific validation.
            trace_id:       enterprise_trace_id echoed back.
        """
        ...

    async def validate_gdpr_soc2_compliance(
        self,
        tenant_id: str,
        framework: str,  # ComplianceFramework enum value
        audit_entries: List[Dict[str, Any]],
        enterprise_trace_id: str,
    ) -> Dict[str, Any]:
        """Validate a set of audit entries against a compliance framework.

        Checks:
          - Every entry has non-empty enterprise_trace_id.
          - Actor identity is resolvable.
          - target_resource is within tenant's isolation boundary.
          - Retention policy is satisfied per framework rules.

        Returns:
            compliant:     True if all checks pass.
            violations:    List of violation descriptions.
            framework:     The ComplianceFramework checked.
            score:         Compliance score 0.0-1.0.
            trace_id:      enterprise_trace_id echoed back.
        """
        ...

    async def generate_compliance_report(
        self,
        tenant_id: str,
        framework: str,  # ComplianceFramework enum value
        report_period_start: datetime.date,
        report_period_end: datetime.date,
        enterprise_trace_id: str,
    ) -> Dict[str, Any]:
        """Generate a structured compliance report for audit.

        Returns:
            report_id:     Unique report identifier.
            framework:     ComplianceFramework evaluated.
            status:        'PASS' | 'FAIL' | 'FLAG'.
            entry_count:   Number of audit entries in period.
            violations:    List of violations found.
            report_hash:   SHA-256 hash of the full report for integrity.
            trace_id:      enterprise_trace_id echoed back.
        """
        ...

    async def archive_logs(
        self,
        tenant_id: str,
        retention_policy: str,
        enterprise_trace_id: str,
    ) -> Dict[str, Any]:
        """Archive audit logs according to retention policy.

        Logs older than the retention window are moved to cold storage
        and removed from the active audit log. The retention_policy
        format is ISO 8601 duration (e.g. 'P90D' for 90 days).

        Returns:
            archived:       Number of entries archived.
            retention_days: Number of days retained.
            archive_ref:    Reference to cold storage location.
            trace_id:       enterprise_trace_id echoed back.
        """
        ...
