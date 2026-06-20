from typing import Dict, Any, TYPE_CHECKING
from core.industrial.healthcare_twin import HealthcareTwin, HealthcareTwinAssetType
from core.interfaces.event_bus import IEventBus
from core.models.event import EventTopic, ExecutionEvent, EventMetadata

if TYPE_CHECKING:
    from core.governance.healthcare_policies import evaluate_policy


class HealthcareDataPipeline:
    def __init__(
        self,
        event_bus: IEventBus,
        healthcare_twin: HealthcareTwin,
    ):
        self._event_bus = event_bus
        self._healthcare_twin = healthcare_twin

    def _publish_safety_violation(self, connector_id: str, action_type: str, 
                                   reason: str, trust_level: str) -> None:
        event = ExecutionEvent(
            topic=EventTopic.SAFETY_VIOLATION,
            payload={
                "connector_id": connector_id,
                "action_type": action_type,
                "reason": reason,
                "trust_level": trust_level,
            },
            trace_id="",
            metadata=EventMetadata(source="healthcare_data_pipeline"),
        )
        self._event_bus.publish(EventTopic.SAFETY_VIOLATION, event)

    def ingest_healthcare_data(
        self,
        connector_id: str,
        data: Dict[str, Any],
        trust_level: str = "UNTRUSTED",
    ) -> Dict[str, Any]:
        from core.governance.healthcare_policies import evaluate_policy, HealthcareActionType
        from core.models.healthcare import HealthcareActionType as ModelHealthcareActionType
        
        action_type_str = data.get("action_type", "OBSERVE")
        try:
            action_type = ModelHealthcareActionType(action_type_str)
        except ValueError:
            action_type = ModelHealthcareActionType.OBSERVE
        
        decision = evaluate_policy(action_type, trust_level)
        
        if not decision.allowed:
            self._publish_safety_violation(connector_id, action_type_str, 
                                           decision.reason, trust_level)
            return {
                "status": "blocked",
                "reason": decision.reason,
                "violation_type": decision.violation_type,
                "connector_id": connector_id,
            }
        
        asset_id = data.get("asset_id", connector_id)
        asset_type_str = data.get("asset_type", "patient_record")
        
        try:
            asset_type = HealthcareTwinAssetType(asset_type_str)
        except ValueError:
            asset_type = HealthcareTwinAssetType.PATIENT_RECORD
        
        state_update = data.get("state_update", {})
        
        twin_state = self._healthcare_twin.update_twin_state(
            asset_id=asset_id,
            asset_type=asset_type,
            new_state=state_update,
            action=f"ingest:{action_type_str}",
        )
        
        return {
            "status": "success",
            "asset_id": asset_id,
            "asset_type": asset_type_str,
            "twin_version": twin_state.version,
            "connector_id": connector_id,
        }