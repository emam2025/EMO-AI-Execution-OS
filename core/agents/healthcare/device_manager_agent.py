from typing import TYPE_CHECKING, Optional, Dict, Any
from core.models.agent import AgentIdentity
from core.models.event import EventTopic, ExecutionEvent, EventMetadata

if TYPE_CHECKING:
    from core.industrial.healthcare_twin import HealthcareTwin
    from core.interfaces.event_bus import IEventBus
    from core.interfaces.governance import IAgentApprovalGate


class DeviceManagerAgent:
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

    def check_device(self, device_id: str) -> Dict[str, Any]:
        if not self._healthcare_twin:
            return {"error": "HealthcareTwin not injected"}
        
        twin_state = self._healthcare_twin.get_twin_state(device_id)
        if not twin_state:
            return {"error": f"Device twin not found: {device_id}"}
        
        measurements = twin_state.state.get("measurements", {})
        status = twin_state.state.get("status", "unknown")
        
        recommendations = []
        
        if status == "running":
            tidal_volume = measurements.get("tidal_volume", 0)
            if tidal_volume < 400 or tidal_volume > 600:
                recommendations.append("RECOMMEND_CALIBRATION")
            
            peak_pressure = measurements.get("peak_pressure", 0)
            if peak_pressure > 30:
                recommendations.append("RECOMMEND_MAINTENANCE")
        
        battery_level = twin_state.state.get("battery_level", 100)
        if battery_level < 20:
            recommendations.append("RECOMMEND_BATTERY_REPLACEMENT")
        
        result = {
            "device_id": device_id,
            "status": status,
            "measurements": measurements,
            "recommendations": recommendations,
            "twin_version": twin_state.version,
        }
        
        if recommendations:
            self._publish_event(
                EventTopic.PREDICTIVE_ALERT,
                {
                    "device_id": device_id,
                    "recommendations": recommendations,
                    "severity": "warning" if "RECOMMEND_CALIBRATION" in recommendations else "info",
                },
                "device_manager_agent",
            )
        
        return result

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