from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from core.interfaces.event_bus import IEventBus
from core.models.event import EventTopic, ExecutionEvent, EventMetadata


class HealthcareTwinAssetType(Enum):
    PATIENT_RECORD = "patient_record"
    MEDICAL_DEVICE = "medical_device"
    CLINIC = "clinic"


@dataclass(frozen=True)
class HealthcareTwinState:
    asset_id: str
    asset_type: HealthcareTwinAssetType
    state: Dict[str, Any]
    version: int
    last_updated: datetime
    audit_trail: List[Dict[str, Any]] = field(default_factory=list)


class HealthcareTwin:
    def __init__(self, event_bus: IEventBus):
        self._event_bus = event_bus
        self._twins: Dict[str, HealthcareTwinState] = {}

    def _publish_twin_updated(self, asset_id: str, asset_type: HealthcareTwinAssetType, 
                               old_version: int, new_version: int, action: str) -> None:
        event = ExecutionEvent(
            topic=EventTopic.TWIN_STATE_UPDATED,
            payload={
                "asset_id": asset_id,
                "asset_type": asset_type.value,
                "old_version": old_version,
                "new_version": new_version,
                "action": action,
            },
            trace_id="",
            metadata=EventMetadata(source="healthcare_twin"),
        )
        self._event_bus.publish(EventTopic.TWIN_STATE_UPDATED, event)

    def get_twin_state(self, asset_id: str) -> Optional[HealthcareTwinState]:
        return self._twins.get(asset_id)

    def update_twin_state(self, asset_id: str, asset_type: HealthcareTwinAssetType, 
                          new_state: Dict[str, Any], action: str = "update") -> HealthcareTwinState:
        current = self._twins.get(asset_id)
        new_version = (current.version + 1) if current else 1
        
        audit_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "version": new_version,
            "state_snapshot": new_state,
        }
        
        audit_trail = (current.audit_trail + [audit_entry]) if current else [audit_entry]
        
        twin_state = HealthcareTwinState(
            asset_id=asset_id,
            asset_type=asset_type,
            state=new_state,
            version=new_version,
            last_updated=datetime.now(timezone.utc),
            audit_trail=audit_trail,
        )
        
        self._twins[asset_id] = twin_state
        
        self._publish_twin_updated(asset_id, asset_type, 
                                   current.version if current else 0, new_version, action)
        
        return twin_state

    def simulate(self, asset_id: str, scenario: Dict[str, Any]) -> Dict[str, Any]:
        current = self._twins.get(asset_id)
        if not current:
            return {"error": "Twin not found", "asset_id": asset_id}
        
        return {
            "asset_id": asset_id,
            "current_state": current.state,
            "scenario": scenario,
            "predicted_state": {"simulated": True, **current.state, **scenario.get("projected_changes", {})},
        }

    def predict(self, asset_id: str, horizon_minutes: int = 60) -> Dict[str, Any]:
        current = self._twins.get(asset_id)
        if not current:
            return {"error": "Twin not found", "asset_id": asset_id}
        
        return {
            "asset_id": asset_id,
            "horizon_minutes": horizon_minutes,
            "current_version": current.version,
            "prediction": {"trend": "stable", "confidence": 0.85},
        }

    def record_event(self, asset_id: str, event_type: str, details: Dict[str, Any]) -> bool:
        current = self._twins.get(asset_id)
        if not current:
            return False
        
        audit_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": f"event:{event_type}",
            "version": current.version,
            "state_snapshot": {**current.state, "event": event_type, "details": details},
        }
        
        updated_trail = current.audit_trail + [audit_entry]
        updated_twin = HealthcareTwinState(
            asset_id=current.asset_id,
            asset_type=current.asset_type,
            state=current.state,
            version=current.version,
            last_updated=datetime.now(timezone.utc),
            audit_trail=updated_trail,
        )
        
        self._twins[asset_id] = updated_twin
        
        self._publish_twin_updated(asset_id, current.asset_type, current.version, current.version, f"event:{event_type}")
        
        return True

    def get_audit_trail(self, asset_id: str) -> List[Dict[str, Any]]:
        current = self._twins.get(asset_id)
        return current.audit_trail if current else []

    def list_all_twins(self) -> Dict[str, HealthcareTwinState]:
        return dict(self._twins)