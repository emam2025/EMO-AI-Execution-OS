from typing import Dict, Any, Optional
from core.interfaces.event_bus import IEventBus
from core.models.event import EventTopic, ExecutionEvent, EventMetadata
from core.connectors.manufacturing.connector_error import ConnectorError


class FHIRConnector:
    def __init__(self, event_bus: IEventBus, base_url: str = "https://fhir.example.com"):
        self._event_bus = event_bus
        self._base_url = base_url
        self._mock_resources = {
            "Patient/pat-001": {
                "resourceType": "Patient",
                "id": "pat-001",
                "identifier": [{"value": "MRN-001"}],
                "name": [{"family": "Smith", "given": ["John"]}],
                "gender": "male",
                "birthDate": "1980-01-15",
            },
            "Observation/obs-001": {
                "resourceType": "Observation",
                "id": "obs-001",
                "status": "final",
                "code": {"coding": [{"system": "http://loinc.org", "code": "8480-6", "display": "Systolic blood pressure"}]},
                "subject": {"reference": "Patient/pat-001"},
                "valueQuantity": {"value": 120, "unit": "mmHg"},
                "effectiveDateTime": "2024-01-15T10:30:00Z",
            },
            "Device/dev-001": {
                "resourceType": "Device",
                "id": "dev-001",
                "identifier": [{"value": "VENT-001"}],
                "type": {"coding": [{"system": "http://snomed.info/sct", "code": "46578000", "display": "Ventilator"}]},
                "deviceName": [{"name": "ICU Ventilator Model X", "type": "user-friendly-name"}],
                "status": "active",
            },
        }

    def _publish_event(self, topic: EventTopic, payload: Dict[str, Any], source: str) -> None:
        event = ExecutionEvent(
            topic=topic,
            payload=payload,
            trace_id="",
            metadata=EventMetadata(source=source),
        )
        self._event_bus.publish(topic, event)

    def get(self, resource_path: str) -> Dict[str, Any]:
        if resource_path not in self._mock_resources:
            self._publish_event(
                EventTopic.CONNECTOR_READ_FAILURE,
                {"resource_path": resource_path, "error": "Resource not found"},
                "fhir_connector",
            )
            raise ConnectorError(f"FHIR resource not found: {resource_path}", connector_type="fhir", node_id=resource_path)
        
        resource = self._mock_resources[resource_path]
        self._publish_event(
            EventTopic.CONNECTOR_READ_SUCCESS,
            {"resource_path": resource_path, "resource_type": resource.get("resourceType")},
            "fhir_connector",
        )
        return resource

    def read_patient(self, patient_id: str) -> Dict[str, Any]:
        return self.get(f"Patient/{patient_id}")

    def read_observation(self, observation_id: str) -> Dict[str, Any]:
        return self.get(f"Observation/{observation_id}")

    def read_device(self, device_id: str) -> Dict[str, Any]:
        return self.get(f"Device/{device_id}")

    def list_resources(self, resource_type: str) -> Dict[str, Any]:
        results = [
            path for path in self._mock_resources.keys() 
            if path.startswith(f"{resource_type}/")
        ]
        return {"resource_type": resource_type, "count": len(results), "resources": results}