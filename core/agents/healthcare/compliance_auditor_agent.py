from typing import TYPE_CHECKING, Optional, Dict, Any
from core.models.agent import AgentIdentity
from core.models.event import EventTopic, ExecutionEvent, EventMetadata

if TYPE_CHECKING:
    from core.industrial.healthcare_twin import HealthcareTwin
    from core.interfaces.event_bus import IEventBus
    from core.interfaces.governance import IAgentApprovalGate
    from core.governance.healthcare_policies import evaluate_policy
    from core.models.healthcare import HealthcareActionType


class ComplianceAuditorAgent:
    def __init__(
        self,
        identity: AgentIdentity,
        healthcare_twin: Optional["HealthcareTwin"] = None,
        event_bus: Optional["IEventBus"] = None,
        approval_gate: Optional["IAgentApprovalGate"] = None,
    ):
        self.identity = identity
        self._healthcare_twin = healthcare_twin
        self._event_bus = event_bus
        self._approval_gate = approval_gate

    def audit_data_access(
        self,
        asset_id: str,
        action_type: str,
        trust_level: str = "UNTRUSTED",
        requested_by: str = "unknown",
    ) -> Dict[str, Any]:
        from core.governance.healthcare_policies import evaluate_policy
        from core.models.healthcare import HealthcareActionType as ModelHealthcareActionType
        
        try:
            action = ModelHealthcareActionType(action_type)
        except ValueError:
            action = ModelHealthcareActionType.OBSERVE
        
        decision = evaluate_policy(action, trust_level)
        
        if not decision.allowed:
            self._publish_event(
                EventTopic.COMPLIANCE_VIOLATION,
                {
                    "asset_id": asset_id,
                    "action_type": action_type,
                    "requested_by": requested_by,
                    "trust_level": trust_level,
                    "violation_type": decision.violation_type,
                    "reason": decision.reason,
                },
                "compliance_auditor_agent",
            )
            
            return {
                "allowed": False,
                "violation_type": decision.violation_type,
                "reason": decision.reason,
                "requires_approval": decision.requires_approval,
            }
        
        return {
            "allowed": True,
            "requires_approval": decision.requires_approval,
        }

    def check_compliance(self, asset_id: str) -> Dict[str, Any]:
        if not self._healthcare_twin:
            return {"error": "HealthcareTwin not injected"}
        
        twin_state = self._healthcare_twin.get_twin_state(asset_id)
        if not twin_state:
            return {"error": f"Asset twin not found: {asset_id}"}
        
        audit_trail = twin_state.audit_trail
        violations = [entry for entry in audit_trail if "violation" in str(entry).lower()]
        
        return {
            "asset_id": asset_id,
            "compliant": len(violations) == 0,
            "audit_entries": len(audit_trail),
            "violations_found": len(violations),
            "twin_version": twin_state.version,
        }

    def _publish_event(self, topic: EventTopic, payload: Dict[str, Any], source: str) -> None:
        if not self._event_bus:
            return
        event = ExecutionEvent(
            topic=topic,
            payload=payload,
            trace_id="",
            metadata=EventMetadata(source=source),
        )
        self._event_bus.publish(topic, event)