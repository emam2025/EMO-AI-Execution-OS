"""EnterpriseFactory — Pure wiring for J2 enterprise components.

Contains ZERO business logic, ZERO policy evaluation.  All policy
(TIERS, GRACE_PERIOD, MAX_VIOLATIONS) lives in the component modules,
not in this factory.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("emo_ai.factory.enterprise")


def build_enterprise_components(
    event_bus: Any = None,
    strict_enterprise_mode: bool = False,
) -> dict:
    """Construct all 5 Phase J2 enterprise components and return them as a dict.

    Returns:
        dict with keys: tenant_router, usage_meter, billing_engine,
                        compliance_auditor, enterprise_trace_correlator
    """
    from core.enterprise.tenant_router import TenantRouter
    from core.enterprise.usage_meter import UsageMeter
    from core.enterprise.billing_engine import BillingEngine
    from core.enterprise.compliance_auditor import ComplianceAuditor
    from core.enterprise.trace_correlator import EnterpriseTraceCorrelator

    trace_correlator = EnterpriseTraceCorrelator()

    return {
        "tenant_router": TenantRouter(
            event_bus=event_bus,
            strict_enterprise_mode=strict_enterprise_mode,
        ),
        "usage_meter": UsageMeter(event_bus=event_bus),
        "billing_engine": BillingEngine(
            event_bus=event_bus,
            trace_correlator=trace_correlator,
            strict_enterprise_mode=strict_enterprise_mode,
        ),
        "compliance_auditor": ComplianceAuditor(
            event_bus=event_bus,
            trace_correlator=trace_correlator,
            strict_enterprise_mode=strict_enterprise_mode,
        ),
        "enterprise_trace_correlator": trace_correlator,
    }
