from typing import TYPE_CHECKING, Optional, Dict, Any
from core.models.agent import AgentIdentity
from core.models.event import EventTopic, ExecutionEvent, EventMetadata

if TYPE_CHECKING:
    from core.industrial.healthcare_twin import HealthcareTwin
    from core.interfaces.event_bus import IEventBus
    from core.interfaces.governance import IAgentApprovalGate


class PatientMonitorAgent:
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

    def monitor_patient(self, patient_id: str) -> Dict[str, Any]:
        if not self._healthcare_twin:
            return {"error": "HealthcareTwin not injected"}
        
        twin_state = self._healthcare_twin.get_twin_state(patient_id)
        if not twin_state:
            return {"error": f"Patient twin not found: {patient_id}"}
        
        vitals = twin_state.state.get("vitals", {})
        heart_rate = vitals.get("heart_rate", 0)
        spo2 = vitals.get("spo2", 0)
        
        anomaly_detected = False
        anomaly_details = []
        
        if heart_rate > 100 or heart_rate < 50:
            anomaly_detected = True
            anomaly_details.append(f"Abnormal heart rate: {heart_rate}")
        
        if spo2 < 95:
            anomaly_detected = True
            anomaly_details.append(f"Low SpO2: {spo2}")
        
        if anomaly_detected:
            self._publish_event(
                EventTopic.ANOMALY_DETECTED,
                {
                    "patient_id": patient_id,
                    "anomalies": anomaly_details,
                    "vitals": vitals,
                    "twin_version": twin_state.version,
                },
                "patient_monitor_agent",
            )
        
        self._publish_event(
            EventTopic.PATIENT_VITALS_UPDATED,
            {
                "patient_id": patient_id,
                "vitals": vitals,
                "status": "anomaly" if anomaly_detected else "normal",
            },
            "patient_monitor_agent",
        )
        
        return {
            "patient_id": patient_id,
            "vitals": vitals,
            "anomaly_detected": anomaly_detected,
            "anomaly_details": anomaly_details,
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