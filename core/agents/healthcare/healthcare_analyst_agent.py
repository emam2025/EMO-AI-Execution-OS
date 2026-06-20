from typing import TYPE_CHECKING, Optional, Dict, Any
from core.models.agent import AgentIdentity
from core.models.event import EventTopic, ExecutionEvent, EventMetadata

if TYPE_CHECKING:
    from core.industrial.healthcare_twin import HealthcareTwin
    from core.interfaces.event_bus import IEventBus
    from core.interfaces.governance import IAgentApprovalGate


class HealthcareAnalystAgent:
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

    def analyze_trends(self, asset_id: str, horizon_minutes: int = 60) -> Dict[str, Any]:
        if not self._healthcare_twin:
            return {"error": "HealthcareTwin not injected"}
        
        twin_state = self._healthcare_twin.get_twin_state(asset_id)
        if not twin_state:
            return {"error": f"Asset twin not found: {asset_id}"}
        
        prediction = self._healthcare_twin.predict(asset_id, horizon_minutes)
        
        report = {
            "asset_id": asset_id,
            "asset_type": twin_state.asset_type.value,
            "current_version": twin_state.version,
            "horizon_minutes": horizon_minutes,
            "prediction": prediction.get("prediction", {}),
            "confidence": prediction.get("confidence", 0.0),
            "recommendations": self._generate_recommendations(twin_state, prediction),
        }
        
        self._publish_event(
            EventTopic.TREND_ANALYSIS_REPORT,
            report,
            "healthcare_analyst_agent",
        )
        
        return report

    def simulate_scenario(self, asset_id: str, scenario: Dict[str, Any]) -> Dict[str, Any]:
        if not self._healthcare_twin:
            return {"error": "HealthcareTwin not injected"}
        
        twin_state = self._healthcare_twin.get_twin_state(asset_id)
        if not twin_state:
            return {"error": f"Asset twin not found: {asset_id}"}
        
        simulation = self._healthcare_twin.simulate(asset_id, scenario)
        
        return {
            "asset_id": asset_id,
            "scenario": scenario,
            "simulation_result": simulation.get("predicted_state", {}),
            "current_version": twin_state.version,
        }

    def _generate_recommendations(self, twin_state, prediction: Dict[str, Any]) -> list:
        recommendations = []
        pred = prediction.get("prediction", {})
        
        if pred.get("trend") == "degrading":
            recommendations.append("INCREASE_MONITORING_FREQUENCY")
        
        if pred.get("confidence", 1.0) < 0.7:
            recommendations.append("REQUIRE_MANUAL_REVIEW")
        
        return recommendations

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