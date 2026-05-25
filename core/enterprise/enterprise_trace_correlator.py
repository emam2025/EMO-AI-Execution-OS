"""Phase J2 — Enterprise Trace Correlator (re-export).  # LAW-5 LAW-12 LAW-23 RULE-4

Re-exports EnterpriseTraceCorrelator from trace_correlator.py for explicit
import by file path convention matching the directive's file tree.

LAW 5: Every enterprise operation is observable via trace chain.
LAW 12: Full back-traceability from F4 to originating call.
LAW 23: Trace partitioning by tenant_id — no cross-tenant trace leakage.
RULE 4: All trace propagation MUST preserve the full chain.

Ref: EXEC-DIRECTIVE-ENT-001
"""

from core.enterprise.trace_correlator import EnterpriseTraceCorrelator

__all__ = ["EnterpriseTraceCorrelator"]
